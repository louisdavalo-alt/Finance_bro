"""Prime de risque implicite (Implied Equity Risk Premium) — façon Damodaran : la prime de
risque actions ex ante est déduite du marché (earnings yield du S&P 500 moins le taux sans
risque), puis appliquée au titre via son bêta (CAPM) : rendement attendu = taux sans risque +
bêta × prime de risque du marché.

⚠️ Simplifications documentées :
- Le earnings yield du marché est approximé par celui de SPY (P/E trailing, `yfinance`), pas une
  vraie estimation ex ante des flux de trésorerie actualisés du S&P 500 (la méthode Damodaran
  complète utilise des flux futurs projetés, pas seulement le P/E courant).
- Le taux sans risque est le rendement souverain 10 ans US (`^TNX`, déjà utilisé comme proxy
  ailleurs dans ce projet — voir `app/connectors/yfin.py` : coté en points de %, divisé par 10).
- Le bêta est estimé par régression simple (covariance/variance) sur tout l'historique commun
  disponible, pas en walk-forward."""
from __future__ import annotations

import asyncio

import numpy as np
import pandas as pd

from ..model_base import PredictionResult
from ._common import scale_to_horizon

MIN_OBS = 250
MARKET_SYMBOL = "SPY"
RISK_FREE_SYMBOL = "^TNX"


def fit_implied_erp_forecast(
    stock_close: pd.Series,
    market_close: pd.Series,
    market_trailing_pe: float | None,
    risk_free_pct: float,
    horizon_days: int = 21,
) -> dict:
    if not market_trailing_pe or market_trailing_pe <= 0:
        raise ValueError("P/E du marché (SPY) indisponible ou non positif")

    stock_ret = stock_close.pct_change()
    market_ret = market_close.pct_change()
    df = pd.DataFrame({"stock": stock_ret, "market": market_ret}).dropna()
    if len(df) < MIN_OBS:
        raise ValueError(f"historique commun titre/marché trop court ({len(df)} points, {MIN_OBS} recommandés)")

    cov = float(np.cov(df["stock"], df["market"])[0, 1])
    var_market = float(np.var(df["market"]))
    beta = cov / var_market if var_market > 0 else 0.0
    resid_daily_std = float(np.std(df["stock"].values - beta * df["market"].values))

    market_earnings_yield_pct = 100.0 / market_trailing_pe
    market_erp_pct = market_earnings_yield_pct - risk_free_pct

    expected_annual_return_pct = risk_free_pct + beta * market_erp_pct
    sigma_annual_pct = resid_daily_std * 100 * float(np.sqrt(252))

    mu_pct, sigma_pct = scale_to_horizon(expected_annual_return_pct, sigma_annual_pct, horizon_days)
    return {
        "expected_return_pct": mu_pct,
        "sigma_pct": sigma_pct,
        "beta": beta,
        "risk_free_pct": risk_free_pct,
        "market_earnings_yield_pct": market_earnings_yield_pct,
        "market_erp_pct": market_erp_pct,
        "n_obs": int(len(df)),
    }


async def fetch_implied_erp_forecast(
    stock_close: pd.Series, horizon_days: int, period: str = "5y", ohlcv_cache=None
) -> PredictionResult:
    """Fonction async car appels réseau (marché, taux sans risque, P/E du marché) — appelée
    comme une tâche parallèle dans `pipeline.run_forecast`."""
    from ...connectors.yfin import _fetch_history_sync
    from ...marketdata import get_daily_bars_frame

    async def _history(ticker: str) -> pd.DataFrame:
        if ohlcv_cache is not None:
            return await get_daily_bars_frame(ticker, period, ohlcv_cache)
        return await asyncio.to_thread(_fetch_history_sync, ticker, period)

    def _market_info() -> dict:
        import yfinance as yf

        return yf.Ticker(MARKET_SYMBOL).get_info()

    market_bars, risk_free_bars, market_info = await asyncio.gather(
        _history(MARKET_SYMBOL), _history(RISK_FREE_SYMBOL), asyncio.to_thread(_market_info)
    )
    if market_bars is None or market_bars.empty:
        raise ValueError(f"aucune donnée disponible pour le marché ({MARKET_SYMBOL})")
    if risk_free_bars is None or risk_free_bars.empty:
        raise ValueError(f"aucune donnée disponible pour le taux sans risque ({RISK_FREE_SYMBOL})")

    risk_free_pct = float(risk_free_bars["Close"].iloc[-1]) / 10  # ^TNX coté en points de %, voir yfin.py
    market_trailing_pe = (market_info or {}).get("trailingPE")

    result = fit_implied_erp_forecast(
        stock_close, market_bars["Close"], market_trailing_pe, risk_free_pct, horizon_days=horizon_days
    )
    return PredictionResult(mu_pct=result["expected_return_pct"], sigma_pct=result["sigma_pct"], diagnostics=result)
