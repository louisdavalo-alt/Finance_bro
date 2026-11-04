"""Cointégration / VECM (Vector Error Correction Model ; Engle & Granger, 1987) : teste si le
titre et l'indice de marché (^GSPC) sont cointégrés (test d'Engle-Granger sur les log-prix), et si
oui, ajuste un VECM pour prévoir le retour vers l'équilibre de long terme entre les deux séries.

⚠️ Beaucoup de titres ne sont PAS cointégrés avec l'indice de marché au sens statistique strict :
ce modèle ÉCHOUE EXPLICITEMENT (p-value du test de cointégration au-dessus du seuil) plutôt que
de forcer un VECM sur une relation qui n'existe pas — un échec de ce modèle est un résultat
statistique légitime, pas un bug.

⚠️ Simplification : la version complète de l'architecture envisage un panier plus large de séries
(cf. aussi `medium_term/var_market.py`, même limitation) ; ce module se limite à une paire
titre/marché."""
from __future__ import annotations

import asyncio

import numpy as np
import pandas as pd

from ..model_base import PredictionResult

MIN_OBS = 250
MARKET_SYMBOL = "^GSPC"
COINT_PVALUE_THRESHOLD = 0.05


def fit_cointegration_vecm_forecast(stock_close: pd.Series, market_close: pd.Series, horizon_days: int = 21) -> dict:
    from statsmodels.tsa.stattools import coint
    from statsmodels.tsa.vector_ar.vecm import VECM, select_coint_rank

    df = pd.DataFrame({"stock": stock_close, "market": market_close}).dropna()
    if len(df) < MIN_OBS:
        raise ValueError(f"historique commun titre/marché trop court ({len(df)} points, {MIN_OBS} recommandés)")

    log_data = np.log(df)
    _, pvalue, _ = coint(log_data["stock"].values, log_data["market"].values)
    if pvalue > COINT_PVALUE_THRESHOLD:
        raise ValueError(
            f"pas de cointégration détectée entre le titre et le marché (p={pvalue:.3f} > {COINT_PVALUE_THRESHOLD})"
        )

    rank_result = select_coint_rank(log_data, det_order=0, k_ar_diff=1)
    # un VECM bivarié ne peut avoir un rang de cointégration pertinent que de 1 (un rang égal au
    # nombre de variables impliquerait que chaque série est déjà stationnaire individuellement,
    # ce qui contredit la nature même d'un indice/titre en marche aléatoire) ; on borne.
    rank = min(max(rank_result.rank, 1), log_data.shape[1] - 1)
    res = VECM(log_data, k_ar_diff=1, coint_rank=rank, deterministic="co").fit()

    forecast = res.predict(steps=horizon_days)  # (horizon_days, 2), niveaux en log
    log_stock_forecast = forecast[:, 0]
    last_log_stock = float(log_data["stock"].iloc[-1])
    cum_log_return = float(log_stock_forecast[-1] - last_log_stock)

    sigma_daily = float(np.sqrt(res.sigma_u[0, 0]))
    cum_sigma = sigma_daily * float(np.sqrt(horizon_days))

    return {
        "expected_return_pct": (np.exp(cum_log_return) - 1) * 100,
        "sigma_pct": cum_sigma * 100,
        "coint_pvalue": float(pvalue),
        "coint_rank": int(rank),
        "n_obs": int(len(df)),
    }


async def fetch_cointegration_vecm_forecast(
    stock_close: pd.Series, horizon_days: int, period: str = "5y", ohlcv_cache=None
) -> PredictionResult:
    """Fonction async car appel réseau (indice de marché) — appelée comme une tâche parallèle
    dans `pipeline.run_forecast`."""
    from ...connectors.yfin import _fetch_history_sync
    from ...marketdata import get_daily_bars_frame

    if ohlcv_cache is not None:
        market_bars = await get_daily_bars_frame(MARKET_SYMBOL, period, ohlcv_cache)
    else:
        market_bars = await asyncio.to_thread(_fetch_history_sync, MARKET_SYMBOL, period)
    if market_bars is None or market_bars.empty:
        raise ValueError(f"aucune donnée disponible pour l'indice de marché {MARKET_SYMBOL}")

    result = fit_cointegration_vecm_forecast(stock_close, market_bars["Close"], horizon_days=horizon_days)
    return PredictionResult(mu_pct=result["expected_return_pct"], sigma_pct=result["sigma_pct"], diagnostics=result)
