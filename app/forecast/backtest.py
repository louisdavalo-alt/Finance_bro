"""Backtest walk-forward (étape 2 de l'architecture, « Backtesting walk-forward (CPU) : fenêtres
glissantes, frais/slippage, IC, hit ratio, CRPS, Sharpe déflaté (vectorbt), toujours hors
échantillon »), appliqué aux 9 modèles qui peuvent tourner sur UN ticker sans appel réseau répété
une fois le feature store point-in-time construit (étape 1, `feature_store.py`/`predict.py`) :
les 8 modèles point-in-time (`predict.ALL_SYNC_MODELS`, 5 court terme + 3 moyen terme
« own-series ») + GARCH (`garch.py`), qui n'avait pas encore de validation hors échantillon,
contrairement à XGBoost (`model.walk_forward_backtest`, antérieur à ce module).

⚠️ Hors du champ de ce module : les 9 modèles réseau (FF5+momentum/PEAD/VAR, les 6 modèles long
terme) coûteraient un appel réseau par (ticker, point de test) — beaucoup trop lent pour une
grille de dizaines de points — et XGBoost, qui a déjà sa propre validation walk-forward séparée
dans `model.py`, pas réconciliée ici.

Garde-fous repris du document d'architecture :

- **Fenêtre EXPANSIVE, toujours hors échantillon** : à chaque point de test `as_of`, un modèle ne
  voit que `full_bars` jusqu'à `as_of` (jamais après) — exactement la même contrainte
  anti-look-ahead que le feature store (`feature_store.read_point_in_time_bars`), mais appliquée
  ici en mémoire par simple troncature de la série déjà récupérée UNE FOIS (`full_bars`), pour ne
  faire ni réseau ni lecture DuckDB répétée à chaque point testé.
- **Baseline naïve** : prévision toujours nulle (`mu_pct=0`), avec pour écart-type la volatilité
  historique réalisée jusque-là (mise à l'échelle de l'horizon) — pas une baseline à variance
  nulle qui perdrait trivialement sur CRPS/Sharpe, mais une vraie marche aléatoire sans dérive.
  Chaque modèle doit la battre pour être considéré utile (guard-rail explicite de l'architecture).
- **Pas entre deux points de test = `horizon_days`** (jamais un pas fixe de ~5 jours
  indépendamment de l'horizon) : les fenêtres de réalisation ne se chevauchent JAMAIS, ce qui est
  nécessaire pour que Sharpe/Sharpe déflaté (qui supposent des rendements de période
  indépendants) ne soient pas artificiellement gonflés par l'autocorrélation de fenêtres
  partiellement communes. Un pas plus fin aurait donné plus de points pour IC/hit ratio/CRPS
  (qui n'ont pas besoin d'indépendance stricte) mais aurait invalidé les deux métriques de P&L.
- **GARCH est volontairement non directionnel** : `mu_pct=0` toujours (comme la baseline), avec
  SA PROPRE prévision de risque (`sigma_pct` = `weekly_vol_forecast_pct`) — documente
  explicitement que GARCH n'apporte ici aucun avantage directionnel (son hit ratio est `None`,
  « non applicable », jamais compté comme un échec), seulement une lecture du risque à comparer
  via CRPS/Sharpe.

Métriques, par modèle, sur l'ensemble des points de test réussis :
- **IC** (Information Coefficient) : corrélation de rang (Spearman) entre les prévisions
  successives `mu_pct` d'UN modèle sur UN ticker et leurs réalisations — une version « dans le
  temps », pas cross-sectionnelle (ce projet n'a pas de score comparant plusieurs titres à la
  même date, donc pas de vrai IC cross-sectionnel à calculer).
- **hit_ratio** : % de points où `sign(mu_pct) == sign(réalisé)`, seulement parmi les points où
  le modèle a pris position (`mu_pct != 0`) — `None` si le modèle n'en a jamais pris (GARCH,
  baseline dégénérée).
- **mae_pct** : erreur absolue moyenne entre `mu_pct` et le rendement réalisé.
- **crps_pct** : Continuous Ranked Probability Score (forme fermée pour une loi normale
  `N(mu_pct, sigma_pct)` — Gneiting & Raftery, 2007), qui note la prévision ENTIÈRE (position ET
  dispersion), pas seulement `mu_pct` — la seule métrique ici qui pénalise un `sigma_pct` mal
  calibré (trop étroit ou trop large), donc la plus pertinente pour GARCH.
- **sharpe** / **deflated_sharpe** : sur le P&L d'une stratégie qui suit le signe de `mu_pct`
  (`sign(mu_pct) * réalisé`, frais+slippage déduits à chaque position prise — voir `TRADING_COST_PCT`),
  calculés par `vectorbt` (`vbt.returns(...).sharpe_ratio()` / `.deflated_sharpe_ratio()`) sur
  TOUS les modèles (+ baseline) À LA FOIS, pour que `nb_trials` (le nombre d'essais dont le Sharpe
  déflaté doit se méfier) soit le nombre réel de modèles comparés sur ce ticker, pas une valeur
  arbitraire.
"""
from __future__ import annotations

import asyncio
import datetime as dt

import numpy as np
import pandas as pd
import vectorbt as vbt
from scipy.stats import norm, spearmanr

from ..ohlcv_cache import OhlcvCache
from .feature_store import read_point_in_time_bars
from .garch import fit_garch_forecast
from .model import HORIZON_MONTH_DAYS, HORIZON_WEEK_DAYS
from .predict import ALL_SYNC_MODELS

HORIZON_DAYS_BY_KEY = {"1w": HORIZON_WEEK_DAYS, "1m": HORIZON_MONTH_DAYS}
BASELINE_NAME = "baseline_naif"
GARCH_NAME = "garch"
TRADING_COST_PCT = 0.15  # frais + slippage aller-retour, en %, déduits à chaque position prise — ⚠️ hypothèse générique, pas calibrée sur un courtier précis.
MIN_TRAIN_DAYS = 420  # couvre le plus exigeant des 8 modèles (momentum_12_1, MIN_OBS=400) avec une marge.


def _crps_normal(mu_pct: float, sigma_pct: float, realized_pct: float) -> float:
    """CRPS en forme fermée pour une prévision normale `N(mu_pct, sigma_pct)` notée contre le
    rendement réalisé (Gneiting & Raftery, 2007, éq. 4) : plus bas = meilleur, 0 = parfait."""
    if sigma_pct <= 0:
        return abs(realized_pct - mu_pct)  # pas d'incertitude déclarée : CRPS dégénère en erreur absolue
    z = (realized_pct - mu_pct) / sigma_pct
    return sigma_pct * (z * (2 * norm.cdf(z) - 1) + 2 * norm.pdf(z) - 1 / np.sqrt(np.pi))


def _realized_vol_pct(log_returns: pd.Series, horizon_days: int) -> float:
    """Volatilité historique réalisée jusque-là, mise à l'échelle de l'horizon (racine du temps,
    même convention que `*/forecast/*/_common.py`) — l'écart-type de la baseline naïve."""
    daily_sigma = float(log_returns.std()) * 100
    return daily_sigma * np.sqrt(horizon_days)


def _evaluate_model_at_point(mu_pct: float, sigma_pct: float, realized_pct: float) -> dict:
    cost = TRADING_COST_PCT if mu_pct != 0 else 0.0
    signal_return_pct = np.sign(mu_pct) * realized_pct - cost
    return {
        "mu_pct": mu_pct,
        "realized_pct": realized_pct,
        "abs_error_pct": abs(mu_pct - realized_pct),
        "crps_pct": _crps_normal(mu_pct, sigma_pct, realized_pct),
        "hit": (np.sign(mu_pct) == np.sign(realized_pct)) if mu_pct != 0 else None,
        "signal_return_pct": signal_return_pct,
    }


async def run_walk_forward_backtest(
    ticker: str, horizon: str, cache: OhlcvCache, min_train_days: int = MIN_TRAIN_DAYS,
) -> dict:
    """Backtest walk-forward hors échantillon de `ticker` sur les 8 modèles point-in-time +
    GARCH + la baseline naïve, à l'horizon demandé (`"1w"` ou `"1m"`). Renvoie, par modèle :
    `n_points` (points de test réussis), `ic`, `hit_ratio` (`None` si non applicable), `mae_pct`,
    `crps_pct` (moyennes), `sharpe`, `deflated_sharpe` — et les erreurs rencontrées
    (`errors: dict[str, str]`, modèle -> dernière erreur, jamais bloquant pour les autres)."""
    if horizon not in HORIZON_DAYS_BY_KEY:
        raise ValueError(f"horizon invalide : {horizon!r} (attendu : '1w' ou '1m')")
    horizon_days = HORIZON_DAYS_BY_KEY[horizon]

    full_bars = await read_point_in_time_bars(ticker, dt.date.today(), cache)
    if full_bars.empty:
        raise ValueError(f"aucune barre disponible pour {ticker}")

    n = len(full_bars)
    test_idx = list(range(min_train_days, n - horizon_days, horizon_days))
    if len(test_idx) < 5:
        raise ValueError(
            f"historique insuffisant pour backtester {ticker} à l'horizon {horizon!r} : "
            f"{n} barres, {len(test_idx)} point(s) de test possible(s) (5 minimum)."
        )

    # Boucle CPU (dizaines de secondes sur ~1200 barres : 9 ajustements de modèles par point
    # de test) : dans un thread, sinon elle bloquerait TOUTE la boucle asyncio de l'API — même
    # raison que `pipeline._compute` (voir son docstring).
    return await asyncio.to_thread(_backtest_cpu, full_bars, test_idx, horizon_days)


def _backtest_cpu(full_bars: pd.DataFrame, test_idx: list[int], horizon_days: int) -> dict:
    close = full_bars["Close"]
    log_returns_full = np.log(close).diff()

    model_names = [m().name for m in ALL_SYNC_MODELS] + [GARCH_NAME, BASELINE_NAME]
    # Indexé par POSITION dans `test_idx` (0..len(test_idx)-1), pas juste une liste qu'on
    # remplit au fil des succès : un point manqué par un modèle laisse un trou identifiable à sa
    # position, nécessaire pour réaligner les séries CRPS (voir `weighting.py`, qui en a besoin
    # pour Hedge) sans supposer que tous les modèles ont réussi aux mêmes points.
    per_point: dict[str, dict[int, dict]] = {name: {} for name in model_names}
    last_errors: dict[str, str] = {}
    dates: list[dt.date] = []

    for pos, i in enumerate(test_idx):
        train_bars = full_bars.iloc[: i + 1]
        realized_pct = float(np.log(close.iloc[i + horizon_days] / close.iloc[i]) * 100)
        dates.append(full_bars.index[i].date())

        for model_cls in ALL_SYNC_MODELS:
            model = model_cls()
            try:
                result = model.predict(train_bars, horizon_days=horizon_days)
                per_point[model.name][pos] = _evaluate_model_at_point(result.mu_pct, result.sigma_pct, realized_pct)
            except Exception as exc:  # noqa: BLE001 - un échec à un point ne bloque jamais les autres
                last_errors[model.name] = f"{type(exc).__name__}: {exc}"

        try:
            garch_res = fit_garch_forecast(log_returns_full.iloc[: i + 1].dropna(), horizon=horizon_days)
            per_point[GARCH_NAME][pos] = _evaluate_model_at_point(0.0, garch_res["weekly_vol_forecast_pct"], realized_pct)
        except Exception as exc:
            last_errors[GARCH_NAME] = f"{type(exc).__name__}: {exc}"

        baseline_sigma = _realized_vol_pct(log_returns_full.iloc[: i + 1].dropna(), horizon_days)
        per_point[BASELINE_NAME][pos] = _evaluate_model_at_point(0.0, baseline_sigma, realized_pct)

    return _summarize(per_point, dates, last_errors, horizon_days)


def _summarize(per_point: dict[str, dict[int, dict]], dates: list[dt.date], errors: dict[str, str], horizon_days: int) -> dict:
    """Agrège les points de test réussis de chaque modèle en métriques (voir le docstring du
    module). Un modèle qui a échoué à certains points (jamais tous, sinon il n'a pas d'entrée
    dans `per_point`) n'est jugé que sur ses points réussis — ni réaligné sur les dates des
    autres modèles ni pénalisé pour les points manqués au-delà de son `n_points` réduit. Expose
    en plus `crps_series`, aligné par POSITION (`None` aux points manqués par ce modèle) : c'est
    la forme dont `weighting.hedge_weights` a besoin pour comparer les modèles point par point."""
    metrics: dict[str, dict] = {}
    returns_cols: dict[str, pd.Series] = {}
    crps_series: dict[str, list[float | None]] = {}
    n_points = len(dates)

    for name, points_by_pos in per_point.items():
        crps_series[name] = [points_by_pos[pos]["crps_pct"] if pos in points_by_pos else None for pos in range(n_points)]
        points = list(points_by_pos.values())
        if not points:
            continue
        hits = [p["hit"] for p in points if p["hit"] is not None]
        metrics[name] = {
            "n_points": len(points),
            "mae_pct": float(np.mean([p["abs_error_pct"] for p in points])),
            "crps_pct": float(np.mean([p["crps_pct"] for p in points])),
            "hit_ratio": (float(np.mean(hits)) if hits else None),
            "n_bets": len(hits),
            "ic": None,
            "sharpe": None,
            "deflated_sharpe": None,
        }
        if len(points) >= 5:
            mu = np.array([p["mu_pct"] for p in points])
            realized = np.array([p["realized_pct"] for p in points])
            if np.ptp(mu) > 0:  # un modèle non directionnel (mu_pct constant à 0) n'a pas d'IC
                rho, _ = spearmanr(mu, realized)
                metrics[name]["ic"] = float(rho) if np.isfinite(rho) else None
        returns_cols[name] = pd.Series([p["signal_return_pct"] / 100 for p in points], index=range(len(points)))

    # Sharpe / Sharpe déflaté : TOUS les modèles ensemble, pour que `nb_trials` (nombre
    # d'essais dont le Sharpe déflaté doit se méfier) reflète le nombre réel de modèles comparés
    # sur ce ticker, pas une valeur arbitraire (voir `vectorbt`'s `deflated_sharpe_ratio`).
    if returns_cols:
        returns_df = pd.DataFrame(returns_cols).dropna(how="all")
        # Un modèle qui ne prend jamais position (HAR-RV, GARCH, la baseline naïve) a un P&L de
        # signal constamment nul : son Sharpe est mathématiquement indéfini (division par un
        # écart-type nul), `None` — et INCLURE sa colonne dans `deflated_sharpe_ratio` ferait
        # remonter un NaN dans `var_sharpe` (calculé sur TOUTES les colonnes à la fois), ce qui
        # casse le Sharpe déflaté de TOUS les modèles, directionnels ou pas. On ne garde donc,
        # pour ce calcul collectif, que les colonnes à variance non nulle — `nb_trials` reflète
        # alors le nombre de stratégies RÉELLEMENT comparées, pas le nombre total de modèles.
        directional = [c for c in returns_df.columns if returns_df[c].std(ddof=0) > 0]
        if len(returns_df) >= 5 and len(directional) >= 2:
            freq_days = max(1, round(horizon_days * 7 / 5))  # ≈ jours calendaires par période
            acc = returns_df[directional].vbt.returns(freq=f"{freq_days}D")
            sharpe = acc.sharpe_ratio()
            dsr = acc.deflated_sharpe_ratio()
            for name in directional:
                metrics[name]["sharpe"] = float(sharpe[name]) if np.isfinite(sharpe[name]) else None
                metrics[name]["deflated_sharpe"] = float(dsr[name]) if np.isfinite(dsr[name]) else None

    return {
        "n_test_points": len(dates),
        "test_dates": [d.isoformat() for d in dates],
        "models": metrics,
        "errors": errors,
        "crps_series": crps_series,
    }
