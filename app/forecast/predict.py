"""Interface commune `predict(ticker, as_of, horizon)` de la couche 4 de l'architecture — la
partie qui restait « anticipée mais pas câblée » dans `model_base.py` jusqu'ici. Ce module est le
« adaptateur fin » que ce docstring promettait : il lit les barres point-in-time
(`feature_store.read_point_in_time_bars`) puis délègue à `HorizonModel.predict(bars,
horizon_days)`, SANS toucher aux 17 classes de modèles déjà écrites — exactement le découplage
que `model_base.py` avait posé en préparation de cette étape.

Seuls les modèles qui n'ont besoin QUE de barres OHLCV (`HorizonModel`, voir `model_base.py`)
rentrent dans cette interface : les 5 modèles court terme (`short_term.MODELS`) et les 3 modèles
moyen terme « own-series » (`medium_term.SYNC_MODELS`), soit 8 modèles. Les 9 modèles réseau
(FF5+momentum/PEAD/VAR en moyen terme, les 6 modèles long terme) ont une signature différente
(ils vont chercher eux-mêmes des données annexes — ETF proxys, dividendes, taux sans risque — à
l'instant de l'appel) et ne peuvent pas être rendus point-in-time sans stocker aussi ces séries
annexes dans le feature store : hors de portée de cette étape, qui se limite à `raw_prices` (voir
`feature_store.py`). Ils restent accessibles comme avant, via `pipeline.run_forecast` (toujours
"aujourd'hui", jamais "comme si on était à telle date passée").

Pas encore câblé sur un endpoint HTTP : rien ne le consomme encore (ce sera le rôle du backtest
walk-forward, étape 2 de l'architecture, pas encore demandée) — cette interface est écrite pour
être appelée en Python, y compris de façon répétée sur des `as_of` différents pour UN MÊME
ticker, sans réappel réseau (voir `feature_store.py`)."""
from __future__ import annotations

import asyncio
import datetime as dt

from ..ohlcv_cache import OhlcvCache
from .feature_store import read_point_in_time_bars
from .medium_term import SYNC_MODELS as MEDIUM_TERM_SYNC_MODELS
from .model import HORIZON_MONTH_DAYS, HORIZON_WEEK_DAYS
from .model_base import HorizonModel, PredictionResult
from .short_term import MODELS as SHORT_TERM_MODELS

HORIZON_DAYS_BY_KEY = {"1w": HORIZON_WEEK_DAYS, "1m": HORIZON_MONTH_DAYS}

# Les 8 modèles point-in-time-compatibles (bars uniquement, aucun appel réseau propre) — voir le
# docstring du module pour pourquoi les 9 modèles réseau en sont exclus.
ALL_SYNC_MODELS: list[type[HorizonModel]] = [*SHORT_TERM_MODELS, *MEDIUM_TERM_SYNC_MODELS]


class NoPointInTimeData(ValueError):
    """Aucune barre disponible pour ce ticker à `as_of` (jamais collecté, ou historique trop
    récent pour couvrir cette date)."""


async def predict_one(
    model_cls: type[HorizonModel], ticker: str, as_of: dt.date, horizon: str, cache: OhlcvCache,
) -> PredictionResult:
    """`predict(ticker, as_of, horizon)` pour UN modèle précis — la forme la plus proche de
    l'interface de l'architecture (`predict(ticker, as_of, horizon) -> {mu, sigma, quantiles}`,
    `PredictionResult` portant `mu_pct`/`sigma_pct`/`quantiles_pct`). Lève `NoPointInTimeData` si
    aucune barre n'est disponible, et laisse remonter toute autre exception du modèle lui-même
    (voir `predict_all` pour l'isolation des échecs, utilisée partout ailleurs dans ce projet)."""
    if horizon not in HORIZON_DAYS_BY_KEY:
        raise ValueError(f"horizon invalide : {horizon!r} (attendu : '1w' ou '1m')")
    bars = await read_point_in_time_bars(ticker, as_of, cache)
    if bars.empty:
        raise NoPointInTimeData(f"aucune barre point-in-time pour {ticker} à as_of={as_of.isoformat()}")
    model = model_cls()
    return model.predict(bars, horizon_days=HORIZON_DAYS_BY_KEY[horizon])


async def predict_all(
    ticker: str, as_of: dt.date, horizon: str, cache: OhlcvCache,
) -> tuple[dict[str, dict], dict[str, str]]:
    """`predict(ticker, as_of, horizon)` sur les 8 modèles point-in-time-compatibles à la fois,
    avec la même isolation des échecs que partout ailleurs dans le système de prévision (un
    modèle en échec n'empêche jamais les autres) : renvoie (résultats, erreurs), les deux dicts
    étant indexés par `HorizonModel.name`. Une seule lecture de barres (via `feature_store.py`,
    donc au plus un appel réseau) partagée par les 8 modèles."""
    if horizon not in HORIZON_DAYS_BY_KEY:
        raise ValueError(f"horizon invalide : {horizon!r} (attendu : '1w' ou '1m')")
    bars = await read_point_in_time_bars(ticker, as_of, cache)
    if bars.empty:
        raise NoPointInTimeData(f"aucune barre point-in-time pour {ticker} à as_of={as_of.isoformat()}")

    horizon_days = HORIZON_DAYS_BY_KEY[horizon]

    def _run_all() -> tuple[dict[str, dict], dict[str, str]]:
        results: dict[str, dict] = {}
        errors: dict[str, str] = {}
        for model_cls in ALL_SYNC_MODELS:
            model = model_cls()
            try:
                result = model.predict(bars, horizon_days=horizon_days)
                results[model.name] = {
                    "mu_pct": result.mu_pct,
                    "sigma_pct": result.sigma_pct,
                    "quantiles_pct": result.quantiles_pct,
                    "diagnostics": result.diagnostics,
                }
            except Exception as exc:  # noqa: BLE001 - un modèle en échec n'empêche jamais les autres
                errors[model.name] = f"{type(exc).__name__}: {exc}"
        return results, errors

    # Ajustements de modèles = CPU : dans un thread, pour ne pas bloquer la boucle asyncio de l'API.
    return await asyncio.to_thread(_run_all)
