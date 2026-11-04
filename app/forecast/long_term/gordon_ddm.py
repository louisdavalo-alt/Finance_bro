"""Modèle de Gordon / Dividend Discount Model (Gordon, 1962) : le rendement total attendu d'une
action qui verse un dividende croissant à taux constant g est r = D1/P0 + g (rendement du
dividende + taux de croissance). Un calcul direct, pas une régression — à la différence de
`dividend_yield.py` qui régresse empiriquement le rendement futur sur le rendement du dividende.

⚠️ Le taux de croissance g est estimé par le TCAC (taux de croissance annuel composé) des
dividendes versés sur l'historique disponible via `yfinance` — pas un taux "normatif"/de long
terme établi par ailleurs. Un historique de dividendes court ou erratique rend cette estimation
fragile, d'où le nombre minimal d'années exigé (`MIN_YEARS`). Ne s'applique pas à un titre qui ne
verse pas de dividende."""
from __future__ import annotations

import asyncio

import pandas as pd

from ..model_base import PredictionResult
from ._common import scale_to_horizon

MIN_YEARS = 3
LITERATURE_ANNUAL_SIGMA_PCT = 16.0


def fit_gordon_ddm_forecast(close: pd.Series, dividends: pd.Series | None, horizon_days: int = 21) -> dict:
    if dividends is None or dividends.empty:
        raise ValueError("aucun dividende versé par ce titre (yfinance) : le modèle de Gordon ne s'applique pas")

    dividends = dividends.copy()
    if dividends.index.tz is not None:
        dividends.index = dividends.index.tz_localize(None)

    annual = dividends.groupby(dividends.index.year).sum()
    annual = annual[annual > 0]
    if len(annual) < MIN_YEARS:
        raise ValueError(
            f"historique de dividendes trop court pour estimer une croissance ({len(annual)} années, {MIN_YEARS} recommandées)"
        )

    n_periods = len(annual) - 1
    growth = (float(annual.iloc[-1]) / float(annual.iloc[0])) ** (1 / n_periods) - 1 if n_periods > 0 else 0.0

    last_price = float(close.iloc[-1])
    cutoff = dividends.index.max() - pd.Timedelta(days=365)
    trailing_12m_div = float(dividends[dividends.index > cutoff].sum())
    dividend_yield = trailing_12m_div / last_price

    expected_annual_return = dividend_yield + growth
    mu_pct, sigma_pct = scale_to_horizon(expected_annual_return * 100, LITERATURE_ANNUAL_SIGMA_PCT, horizon_days)
    return {
        "expected_return_pct": mu_pct,
        "sigma_pct": sigma_pct,
        "dividend_yield_pct": dividend_yield * 100,
        "dividend_growth_annual_pct": growth * 100,
        "n_years_dividend_history": int(len(annual)),
    }


async def fetch_gordon_ddm_forecast(symbol: str, close: pd.Series, horizon_days: int) -> PredictionResult:
    """Fonction async car appel réseau (`Ticker.dividends`) — appelée comme une tâche parallèle
    dans `pipeline.run_forecast`."""

    def _sync() -> pd.Series:
        import yfinance as yf

        return yf.Ticker(symbol).dividends

    dividends = await asyncio.to_thread(_sync)
    result = fit_gordon_ddm_forecast(close, dividends, horizon_days=horizon_days)
    return PredictionResult(mu_pct=result["expected_return_pct"], sigma_pct=result["sigma_pct"], diagnostics=result)
