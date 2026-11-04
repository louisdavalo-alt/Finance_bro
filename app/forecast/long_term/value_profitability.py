"""Facteurs value et profitabilité — même logique que `medium_term/ff5_momentum.py` mais
restreinte aux 2 facteurs explicitement cités pour le long terme dans l'architecture du projet
(value et profitabilité), approximés par les mêmes ETF proxys.

⚠️ Même limitation que `ff5_momentum.py` : les vraies séries Fama-French ne sont disponibles ni
via `yfinance` ni ailleurs dans ce projet. VLUE (value) et QUAL (profitabilité/qualité) sont des
APPROXIMATIONS DE STYLE par ETF cotés, pas les vraies séries académiques."""
from __future__ import annotations

import asyncio

import numpy as np
import pandas as pd

from ..model_base import PredictionResult
from ._common import scale_to_horizon

MIN_OBS = 250
PROXY_TICKERS = ["SPY", "VLUE", "QUAL"]
FACTOR_COLUMNS = ["value", "profitability"]


def fit_value_profitability_forecast(
    stock_close: pd.Series, proxy_closes: dict[str, pd.Series], horizon_days: int = 21
) -> dict:
    rets = {t: proxy_closes[t].pct_change() for t in PROXY_TICKERS}
    factors = pd.DataFrame({"value": rets["VLUE"] - rets["SPY"], "profitability": rets["QUAL"] - rets["SPY"]})
    stock_ret = stock_close.pct_change().rename("stock")

    df = factors.join(stock_ret, how="inner").dropna()
    if len(df) < MIN_OBS:
        raise ValueError(f"historique commun titre/facteurs trop court ({len(df)} points, {MIN_OBS} recommandés)")

    X = np.column_stack([np.ones(len(df))] + [df[c].values for c in FACTOR_COLUMNS])
    y = df["stock"].values
    coeffs, *_ = np.linalg.lstsq(X, y, rcond=None)
    alpha = float(coeffs[0])
    betas = coeffs[1:]

    resid = y - X @ coeffs
    resid_daily_std = float(np.std(resid))

    mean_factor_returns = df[FACTOR_COLUMNS].mean().values
    expected_daily_return = alpha + float(np.dot(betas, mean_factor_returns))

    expected_annual_return_pct = ((1 + expected_daily_return) ** 252 - 1) * 100
    sigma_annual_pct = resid_daily_std * 100 * float(np.sqrt(252))

    mu_pct, sigma_pct = scale_to_horizon(expected_annual_return_pct, sigma_annual_pct, horizon_days)
    return {
        "expected_return_pct": mu_pct,
        "sigma_pct": sigma_pct,
        "alpha_daily_pct": alpha * 100,
        "betas": dict(zip(FACTOR_COLUMNS, (float(b) for b in betas))),
        "n_obs": int(len(df)),
    }


async def fetch_value_profitability_forecast(
    stock_close: pd.Series, horizon_days: int, period: str = "5y", ohlcv_cache=None
) -> PredictionResult:
    """Fonction async car appels réseau (ETF proxys) — appelée comme une tâche parallèle dans
    `pipeline.run_forecast`."""
    from ...connectors.yfin import _fetch_history_sync
    from ...marketdata import get_daily_bars_frame

    async def _one(ticker: str) -> pd.DataFrame:
        if ohlcv_cache is not None:
            return await get_daily_bars_frame(ticker, period, ohlcv_cache)
        return await asyncio.to_thread(_fetch_history_sync, ticker, period)

    frames = await asyncio.gather(*[_one(t) for t in PROXY_TICKERS])
    proxy_closes: dict[str, pd.Series] = {}
    for ticker, frame in zip(PROXY_TICKERS, frames):
        if frame is None or frame.empty:
            raise ValueError(f"aucune donnée disponible pour le proxy de facteur {ticker}")
        proxy_closes[ticker] = frame["Close"]

    result = fit_value_profitability_forecast(stock_close, proxy_closes, horizon_days=horizon_days)
    return PredictionResult(mu_pct=result["expected_return_pct"], sigma_pct=result["sigma_pct"], diagnostics=result)
