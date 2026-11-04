"""Régression du rendement du dividende (dividend yield).

La littérature empirique constate qu'un rendement du dividende élevé prédit statistiquement des
rendements futurs plus élevés (mean-reversion vers une valorisation « normale »), sur des
échantillons de plusieurs décennies et plusieurs centaines de titres.

⚠️ Simplification à un seul actif : faute d'un tel panel multi-titres/multi-décennies dans ce
projet, ce module régresse le rendement futur (~1 an) du titre sur SON PROPRE rendement de
dividende glissant — un proxy own-series, pas la régression de panel classique.

⚠️ Ne s'applique pas à un titre qui ne verse pas de dividende (échec explicite plutôt que
d'inventer un rendement — voir la discussion du projet)."""
from __future__ import annotations

import asyncio

import numpy as np
import pandas as pd

from ..model_base import PredictionResult
from ._common import scale_to_horizon

HOLDING_DAYS = 252  # ~1 an : horizon de référence pour cette régression (voir _common.py)
MIN_OBS = 250


def fit_dividend_yield_forecast(close: pd.Series, dividends: pd.Series | None, horizon_days: int = 21) -> dict:
    if dividends is None or dividends.empty:
        raise ValueError(
            "aucun dividende versé par ce titre (yfinance) : le rendement du dividende ne s'applique pas"
        )

    dividends = dividends.copy()
    if dividends.index.tz is not None:
        dividends.index = dividends.index.tz_localize(None)

    # dividende glissant sur 12 mois (sommé), ré-échantillonné sur les dates de `close` en
    # reportant en avant le dernier dividende connu jusqu'au suivant.
    trailing_12m_div = dividends.rolling("365D").sum()
    trailing_12m_div = trailing_12m_div.reindex(close.index, method="ffill")
    div_yield = trailing_12m_div / close

    fwd = close.shift(-HOLDING_DAYS) / close - 1
    df = pd.DataFrame({"yield": div_yield, "fwd": fwd}).dropna()
    if len(df) < MIN_OBS:
        raise ValueError(f"historique dividende/prix trop court ({len(df)} points, {MIN_OBS} recommandés)")

    b, a = np.polyfit(df["yield"].values, df["fwd"].values, 1)
    resid = df["fwd"].values - (a + b * df["yield"].values)
    resid_std = float(np.std(resid))

    last_yield = float(div_yield.dropna().iloc[-1])
    predicted_annual_return = float(a + b * last_yield)

    mu_pct, sigma_pct = scale_to_horizon(predicted_annual_return * 100, resid_std * 100, horizon_days)
    return {
        "expected_return_pct": mu_pct,
        "sigma_pct": sigma_pct,
        "slope": float(b),
        "intercept": float(a),
        "current_dividend_yield_pct": last_yield * 100,
        "n_obs": int(len(df)),
    }


async def fetch_dividend_yield_forecast(symbol: str, close: pd.Series, horizon_days: int) -> PredictionResult:
    """Fonction async car appel réseau (`Ticker.dividends`) — appelée comme une tâche parallèle
    dans `pipeline.run_forecast`."""

    def _sync() -> pd.Series:
        import yfinance as yf

        return yf.Ticker(symbol).dividends

    dividends = await asyncio.to_thread(_sync)
    result = fit_dividend_yield_forecast(close, dividends, horizon_days=horizon_days)
    return PredictionResult(mu_pct=result["expected_return_pct"], sigma_pct=result["sigma_pct"], diagnostics=result)
