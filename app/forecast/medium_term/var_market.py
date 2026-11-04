"""VAR (Vector AutoRegression) bivarié : titre / indice de marché large (^GSPC, S&P 500) —
capture les effets de tête/traîne (lead-lag) entre le titre et le marché, au-delà de ce qu'une
simple régression contemporaine (bêta) donnerait : le VAR autorise le rendement passé du MARCHÉ
à prédire le rendement futur du TITRE (et réciproquement), avec un nombre de retards choisi
automatiquement par AIC (`statsmodels.tsa.api.VAR`).

⚠️ Simplification : la version complète de l'architecture du projet envisage un VAR sur un
panier plus large de séries macro/actifs ; ce module se limite à deux séries (titre + indice de
marché, la seule série systématiquement disponible sans dépendre du pays/de la disponibilité
d'une série macro) — un VAR enrichi du contexte macro du pays (comme `macro_context.py` le fait
déjà pour XGBoost à horizon 1 mois) resterait à construire séparément."""
from __future__ import annotations

import asyncio

import numpy as np
import pandas as pd

from ..model_base import PredictionResult

MIN_OBS = 250
MARKET_SYMBOL = "^GSPC"
MAX_LAGS = 5


def fit_var_market_forecast(stock_close: pd.Series, market_close: pd.Series, horizon_days: int = 21) -> dict:
    from statsmodels.tsa.api import VAR

    stock_ret = stock_close.pct_change()
    market_ret = market_close.pct_change()
    df = pd.DataFrame({"stock": stock_ret, "market": market_ret}).dropna()
    if len(df) < MIN_OBS:
        raise ValueError(f"historique commun titre/marché trop court ({len(df)} points, {MIN_OBS} recommandés)")

    res = VAR(df.values).fit(maxlags=MAX_LAGS, ic="aic")
    k_ar = max(res.k_ar, 1)  # AIC peut choisir 0 retard (séries peu autocorrélées) ; on garde au
    # moins 1 ligne d'historique récent en entrée de `forecast`, le modèle ajusté reste celui choisi

    forecast = res.forecast(df.values[-k_ar:], steps=horizon_days)  # (horizon_days, 2)
    stock_daily_forecast = forecast[:, 0]
    cum_simple_return = float(np.prod(1 + stock_daily_forecast) - 1)

    mse = res.mse(horizon_days)  # (horizon_days, 2, 2) : variance de l'erreur de prévision par pas
    # approximation : somme des variances pas par pas (corrélations entre pas ignorées), même
    # convention d'agrégation que les autres modèles de ce projet (GARCH, ARIMA...)
    cum_var = float(np.sum(mse[:, 0, 0]))

    return {
        "expected_return_pct": cum_simple_return * 100,
        "sigma_pct": float(np.sqrt(max(cum_var, 0.0))) * 100,
        "lags_used": int(res.k_ar),
        "n_obs": int(len(df)),
    }


async def fetch_var_market_forecast(
    stock_close: pd.Series, horizon_days: int, period: str = "5y", ohlcv_cache=None
) -> PredictionResult:
    """Récupère l'historique de l'indice de marché (même mécanisme de cache que le reste du
    projet si `ohlcv_cache` est fourni) puis ajuste/prévoit. Fonction async car elle fait un appel
    réseau — appelée comme une tâche parallèle dans `pipeline.run_forecast`, pas depuis le thread
    CPU de `_compute`."""
    from ...connectors.yfin import _fetch_history_sync
    from ...marketdata import get_daily_bars_frame

    if ohlcv_cache is not None:
        market_bars = await get_daily_bars_frame(MARKET_SYMBOL, period, ohlcv_cache)
    else:
        market_bars = await asyncio.to_thread(_fetch_history_sync, MARKET_SYMBOL, period)
    if market_bars is None or market_bars.empty:
        raise ValueError(f"aucune donnée disponible pour l'indice de marché {MARKET_SYMBOL}")

    result = fit_var_market_forecast(stock_close, market_bars["Close"], horizon_days=horizon_days)
    return PredictionResult(mu_pct=result["expected_return_pct"], sigma_pct=result["sigma_pct"], diagnostics=result)
