"""Orchestration du système de prévision à court/moyen terme : récupère l'OHLCV (comme
`ohlc.py` et `quote.py`, à la demande, rien n'est stocké), calcule les indicateurs techniques,
ajuste un GARCH(1,1) pour la volatilité, entraîne un XGBoost validé en walk-forward (horizon
~1 semaine ou ~1 mois, voir `horizon`), détecte le régime de marché courant via un HMM
(`regime.py`), et analyse le carnet d'options le plus proche (PCR, Max Pain, skew d'IV —
`options.py`). Chaque bloc échoue indépendamment des autres (un échec sur les options, par
exemple si le titre n'a pas d'options cotées, n'empêche pas le reste de s'afficher).

À horizon 1 mois (`horizon="1m"`), le modèle XGBoost reçoit en plus le **contexte macro** du
pays de l'indicateur (`macro_context.py`) : taux directeur, rendement souverain, inflation —
les séries DÉJÀ COLLECTÉES par le pipeline principal (lues en base, aucun appel réseau pour cette
partie), alignées sans biais de look-ahead via `resample.align_panel`. C'est la différence
structurelle entre les deux horizons, pas seulement un changement de fenêtre : à 1 semaine, le
contexte macro ne change essentiellement pas d'un jour à l'autre et n'apporterait rien ; à
1 mois, il devient pertinent. Aucune série macro n'est disponible pour certains pays (GBR, KOR,
CAN, POL, MEX...) — dans ce cas le modèle à 1 mois se rabat silencieusement sur les seuls
indicateurs techniques, comme à 1 semaine (`macro_codes_used` sera vide, à vérifier côté
affichage plutôt que supposé).

⚠️ Ceci est un outil de RECHERCHE, pas un signal de trading. La prévision du rendement d'une
action, même à un mois, reste difficile — un léger avantage statistique mesuré en backtest ne
garantit rien pour l'avenir. `ml_backtest` sert précisément à juger honnêtement si le modèle fait
mieux que le hasard SUR CET HISTORIQUE PRÉCIS avant de faire la moindre confiance à `ml_forecast`.

Le volet « flux d'ordres » et « actualités / sentiment » (FinBERT, Reddit) n'est volontairement
pas dans ce module : le flux d'ordres n'a pas de source dans ce projet,
et le sentiment est prévu pour un lot séparé.

En complément du GARCH, cinq modèles classiques « court terme » NON liés à une IA
(`app/forecast/short_term/` : HAR-RV, ARIMA, filtre de Kalman, Ornstein-Uhlenbeck, retournement)
sont ajustés sur le même `horizon_days` que GARCH/XGBoost, via l'interface commune
`HorizonModel`/`PredictionResult` (`model_base.py`). Comme pour les autres blocs, chacun échoue
indépendamment des autres (`short_term_models`/`short_term_errors` dans le résultat).

À horizon « 1 mois » uniquement (ces modèles n'ont pas de sens sur 5 jours de bourse), six
modèles « moyen terme » NON liés à une IA (`app/forecast/medium_term/` : Momentum 12-1,
time-series momentum, Markov switching, Fama-French 5 + momentum, post-earnings drift, VAR
titre/marché) viennent s'ajouter, exposés sous `medium_term_models`/`medium_term_errors`. Les
trois premiers (own-series, pas d'appel réseau) tournent dans `_compute` comme les modèles court
terme ; les trois derniers ont besoin d'un appel réseau (ETF proxys, dates de résultats, indice
de marché) et tournent en tâches asyncio parallèles, comme `options_task`/`kronos_task`.

Toujours à horizon « 1 mois » uniquement, six modèles « long terme » (1-10 ans) NON liés à une IA
(`app/forecast/long_term/` : CAPE de Shiller, régression dividend yield, Gordon/DDM, prime de
risque implicite, facteurs value/profitabilité, cointégration/VECM) viennent s'ajouter, exposés
sous `long_term_models`/`long_term_errors`. Les six ont tous besoin d'un appel réseau
(fondamentaux du titre, ETF proxys, taux sans risque) : comme les modèles moyen terme réseau, ce
sont des tâches asyncio parallèles — il n'y a pas de volet « own-series » pour le long terme.
"""
from __future__ import annotations

import asyncio

from ..connectors.yfin import _fetch_history_sync
from ..marketdata import get_daily_bars_frame
from ..security import redact_text
from .features import FEATURE_COLUMNS, build_feature_frame
from .garch import fit_garch_forecast
from .kronos_client import KronosUnavailable, kronos_forecast
from .long_term import (
    fetch_cape_forecast,
    fetch_cointegration_vecm_forecast,
    fetch_dividend_yield_forecast,
    fetch_gordon_ddm_forecast,
    fetch_implied_erp_forecast,
    fetch_value_profitability_forecast,
)
from .macro_context import build_macro_features
from .medium_term import SYNC_MODELS as MEDIUM_TERM_SYNC_MODELS
from .medium_term import fetch_ff5_momentum_forecast, fetch_pead_forecast, fetch_var_market_forecast
from .model import HORIZON_MONTH_DAYS, HORIZON_WEEK_DAYS, build_dataset, fit_final_and_predict, walk_forward_backtest
from .options import analyze_options
from .regime import fit_regimes
from .short_term import MODELS as SHORT_TERM_MODELS

HORIZON_DAYS_BY_KEY = {"1w": HORIZON_WEEK_DAYS, "1m": HORIZON_MONTH_DAYS}


class NoMarketData(ValueError):
    """Aucune barre OHLCV exploitable pour ce ticker (ticker inconnu, ou Yahoo injoignable)."""


def _err(exc: Exception) -> str:
    """Message d'erreur d'un bloc, renvoyé au tableau de bord : type + texte, secrets masqués."""
    return redact_text(f"{type(exc).__name__}: {exc}")[:300]


def _compute(bars, horizon: str, horizon_days: int, country: str | None, store) -> dict:
    """Partie CPU (indicateurs, GARCH, 6 ajustements XGBoost, HMM) — exécutée dans un thread par
    `run_forecast` : auparavant elle tournait directement dans la boucle asyncio de l'API et
    bloquait TOUTES les autres requêtes (tableau de bord compris) pendant plusieurs secondes."""
    feat = build_feature_frame(bars)
    dataset = build_dataset(feat, horizon_days=horizon_days)

    feature_columns = list(FEATURE_COLUMNS)
    macro_codes_used: list[str] = []
    if horizon == "1m" and country and store is not None:
        macro_df, macro_codes_used = build_macro_features(store, country, dataset.index)
        if not macro_df.empty:
            dataset = dataset.join(macro_df)
            feature_columns += list(macro_df.columns)

    garch_result, garch_error = None, None
    try:
        garch_result = fit_garch_forecast(feat["log_ret_1d"], horizon=horizon_days)
    except Exception as exc:
        garch_error = _err(exc)

    backtest, forecast, ml_error = None, None, None
    try:
        backtest = walk_forward_backtest(dataset, horizon_days=horizon_days, feature_columns=feature_columns)
        forecast = fit_final_and_predict(dataset, horizon_days=horizon_days, feature_columns=feature_columns)
    except Exception as exc:
        ml_error = _err(exc)

    regime_result, regime_error = None, None
    try:
        regime_result = fit_regimes(feat["log_ret_1d"], n_states=3)
    except Exception as exc:
        regime_error = _err(exc)

    short_term_models: dict = {}
    short_term_errors: dict = {}
    for model_cls in SHORT_TERM_MODELS:
        model = model_cls()
        try:
            result = model.predict(bars, horizon_days=horizon_days)
            short_term_models[model.name] = {
                "mu_pct": result.mu_pct,
                "sigma_pct": result.sigma_pct,
                "quantiles_pct": result.quantiles_pct,
                "diagnostics": result.diagnostics,
            }
        except Exception as exc:
            short_term_errors[model.name] = _err(exc)

    # Modèles moyen terme « own-series » (pas d'appel réseau) : voir la docstring du module —
    # seulement à horizon 1 mois, les trois autres (réseau) sont ajoutés dans `run_forecast`.
    medium_term_models: dict = {}
    medium_term_errors: dict = {}
    if horizon == "1m":
        for model_cls in MEDIUM_TERM_SYNC_MODELS:
            model = model_cls()
            try:
                result = model.predict(bars, horizon_days=horizon_days)
                medium_term_models[model.name] = {
                    "mu_pct": result.mu_pct,
                    "sigma_pct": result.sigma_pct,
                    "quantiles_pct": result.quantiles_pct,
                    "diagnostics": result.diagnostics,
                }
            except Exception as exc:
                medium_term_errors[model.name] = _err(exc)

    return {
        "garch": garch_result, "garch_error": garch_error,
        "ml_forecast": forecast, "ml_backtest": backtest, "ml_error": ml_error,
        "macro_codes_used": macro_codes_used,
        "regime": regime_result, "regime_error": regime_error,
        "short_term_models": short_term_models, "short_term_errors": short_term_errors,
        "medium_term_models": medium_term_models, "medium_term_errors": medium_term_errors,
        # Les modèles long terme n'ont pas de volet "own-series" : tout se fait en tâches réseau
        # dans `run_forecast`, ces dicts ne sont donc remplis que là-bas (voir docstring du module).
        "long_term_models": {}, "long_term_errors": {},
    }


async def run_forecast(
    symbol: str, period: str = "5y", horizon: str = "1w",
    country: str | None = None, store=None,
    use_kronos: bool = False, settings=None,
    ohlcv_cache=None,
) -> dict:
    if horizon not in HORIZON_DAYS_BY_KEY:
        raise ValueError(f"horizon invalide : {horizon!r} (attendu : '1w' ou '1m')")
    horizon_days = HORIZON_DAYS_BY_KEY[horizon]

    # Historique, carnet d'options et prévision Kronos sont des appels réseau indépendants :
    # lancés en parallèle (avant l'ajout de Kronos : seul l'historique bloquait, les options
    # tournaient déjà en parallèle du calcul CPU plus bas).
    options_task = asyncio.create_task(analyze_options(symbol))
    try:
        # `ohlcv_cache` (fourni par l'API, voir api.py) sert l'historique depuis le cache local
        # mis à jour de façon incrémentale (app/marketdata.py) — un même titre redemandé pour
        # plusieurs horizons/pays dans la même journée ne refait aucun appel réseau. Sans cache
        # fourni (ex. appel direct depuis les tests), comportement inchangé : appel direct à
        # Yahoo Finance pour la fenêtre demandée.
        if ohlcv_cache is not None:
            bars = await get_daily_bars_frame(symbol, period, ohlcv_cache)
        else:
            bars = await asyncio.to_thread(_fetch_history_sync, symbol, period)
    except BaseException:
        options_task.cancel()
        raise
    if bars is None or bars.empty:
        options_task.cancel()
        raise NoMarketData(f"aucune donnée OHLCV renvoyée pour {symbol}")
    bars = bars.dropna(subset=["Open", "High", "Low", "Close"])
    if bars.empty:
        options_task.cancel()
        raise NoMarketData(f"aucune barre exploitable pour {symbol} après filtrage des valeurs manquantes")

    kronos_task = asyncio.create_task(kronos_forecast(bars, settings)) if (use_kronos and settings is not None) else None

    # Les 3 modèles moyen terme qui ont besoin d'un appel réseau (ETF proxys, dates de résultats,
    # indice de marché) tournent en tâches parallèles, comme options_task/kronos_task — jamais
    # dans le thread CPU de `_compute`. Seulement à horizon 1 mois (voir docstring du module).
    # Idem pour les 6 modèles long terme (tous en réseau, voir docstring du module).
    medium_term_network_tasks: dict[str, asyncio.Task] = {}
    long_term_network_tasks: dict[str, asyncio.Task] = {}
    if horizon == "1m":
        medium_term_network_tasks = {
            "ff5_momentum": asyncio.create_task(
                fetch_ff5_momentum_forecast(bars["Close"], horizon_days, period=period, ohlcv_cache=ohlcv_cache)
            ),
            "pead": asyncio.create_task(fetch_pead_forecast(symbol, bars["Close"], horizon_days)),
            "var_market": asyncio.create_task(
                fetch_var_market_forecast(bars["Close"], horizon_days, period=period, ohlcv_cache=ohlcv_cache)
            ),
        }
        long_term_network_tasks = {
            "cape": asyncio.create_task(fetch_cape_forecast(symbol, horizon_days)),
            "dividend_yield": asyncio.create_task(fetch_dividend_yield_forecast(symbol, bars["Close"], horizon_days)),
            "gordon_ddm": asyncio.create_task(fetch_gordon_ddm_forecast(symbol, bars["Close"], horizon_days)),
            "implied_erp": asyncio.create_task(
                fetch_implied_erp_forecast(bars["Close"], horizon_days, period=period, ohlcv_cache=ohlcv_cache)
            ),
            "value_profitability": asyncio.create_task(
                fetch_value_profitability_forecast(bars["Close"], horizon_days, period=period, ohlcv_cache=ohlcv_cache)
            ),
            "cointegration_vecm": asyncio.create_task(
                fetch_cointegration_vecm_forecast(bars["Close"], horizon_days, period=period, ohlcv_cache=ohlcv_cache)
            ),
        }

    computed = await asyncio.to_thread(_compute, bars, horizon, horizon_days, country, store)

    for dest_key, err_key, tasks in (
        ("medium_term_models", "medium_term_errors", medium_term_network_tasks),
        ("long_term_models", "long_term_errors", long_term_network_tasks),
    ):
        for name, task in tasks.items():
            try:
                result = await task
                computed[dest_key][name] = {
                    "mu_pct": result.mu_pct,
                    "sigma_pct": result.sigma_pct,
                    "quantiles_pct": result.quantiles_pct,
                    "diagnostics": result.diagnostics,
                }
            except Exception as exc:
                computed[err_key][name] = _err(exc)

    options_result, options_error = None, None
    try:
        options_result = await options_task
    except Exception as exc:
        options_error = _err(exc)

    kronos_result, kronos_error = None, None
    if kronos_task is not None:
        try:
            kronos_result = await kronos_task
        except KronosUnavailable as exc:
            kronos_error = _err(exc)
        except Exception as exc:  # noqa: BLE001 - ne doit jamais faire échouer le reste du calcul
            kronos_error = _err(exc)

    return {
        "symbol": symbol,
        "horizon": horizon,
        "n_bars": int(len(bars)),
        "history_start": str(bars.index[0].date()),
        "history_end": str(bars.index[-1].date()),
        "garch": computed["garch"],
        "garch_error": computed["garch_error"],
        "ml_forecast": computed["ml_forecast"],
        "ml_backtest": computed["ml_backtest"],
        "ml_error": computed["ml_error"],
        "macro_codes_used": computed["macro_codes_used"],
        "regime": computed["regime"],
        "regime_error": computed["regime_error"],
        "short_term_models": computed["short_term_models"],
        "short_term_errors": computed["short_term_errors"],
        "medium_term_models": computed["medium_term_models"],
        "medium_term_errors": computed["medium_term_errors"],
        "long_term_models": computed["long_term_models"],
        "long_term_errors": computed["long_term_errors"],
        "options": options_result,
        "options_error": options_error,
        "kronos": kronos_result,
        "kronos_error": kronos_error,
    }
