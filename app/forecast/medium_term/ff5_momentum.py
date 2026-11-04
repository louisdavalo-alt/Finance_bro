"""Fama-French 5 facteurs + momentum (Fama & French, 2015 ; Carhart, 1997) — ajuste les BÊTAS du
titre sur 6 facteurs (régression multiple des rendements quotidiens), puis prévoit un rendement
attendu = alpha + bêtas · primes de facteurs historiques moyennes.

⚠️ Simplification majeure, documentée explicitement : les vraies séries Fama-French (Kenneth
French Data Library) ne sont disponibles ni via `yfinance` ni ailleurs dans ce projet. Ce module
les APPROXIME par des ETF cotés, récupérés via `yfinance` comme le reste du projet :

    Marché (Mkt)          : SPY (S&P 500) — le taux sans risque n'est PAS soustrait (proxy brut
                            du marché, pas un rendement excédentaire)
    Taille (SMB)          : IWM (Russell 2000, petites capitalisations) − SPY
    Value (HML)           : VTV (grandes capitalisations value) − VUG (grandes capitalisations growth)
    Profitabilité (RMW)   : QUAL (facteur qualité MSCI USA) − SPY
    Investissement (CMA)  : USMV (facteur low-volatility MSCI USA) − SPY — le proxy le plus
                            approximatif des six : la volatilité minimale n'est pas le facteur
                            investissement conservateur/agressif de Fama-French, faute d'ETF
                            public largement coté qui corresponde mieux
    Momentum (MOM)         : MTUM (facteur momentum MSCI USA) − SPY

Ce sont des APPROXIMATIONS DE STYLE par ETF, pas les vraies séries académiques — à ne jamais
présenter comme telles."""
from __future__ import annotations

import asyncio

import numpy as np
import pandas as pd

from ..model_base import PredictionResult

MIN_OBS = 120
PROXY_TICKERS = ["SPY", "IWM", "VTV", "VUG", "QUAL", "USMV", "MTUM"]
FACTOR_COLUMNS = ["mkt", "smb", "hml", "rmw", "cma", "mom"]


def _build_factor_returns(proxy_closes: dict[str, pd.Series]) -> pd.DataFrame:
    rets = {t: proxy_closes[t].pct_change() for t in PROXY_TICKERS}
    return pd.DataFrame(
        {
            "mkt": rets["SPY"],
            "smb": rets["IWM"] - rets["SPY"],
            "hml": rets["VTV"] - rets["VUG"],
            "rmw": rets["QUAL"] - rets["SPY"],
            "cma": rets["USMV"] - rets["SPY"],
            "mom": rets["MTUM"] - rets["SPY"],
        }
    )


def fit_ff5_momentum_forecast(
    stock_close: pd.Series, proxy_closes: dict[str, pd.Series], horizon_days: int = 21
) -> dict:
    factors = _build_factor_returns(proxy_closes)
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
    resid_std_daily = float(np.std(resid))

    mean_factor_returns = df[FACTOR_COLUMNS].mean().values
    expected_daily_return = alpha + float(np.dot(betas, mean_factor_returns))

    cum_simple_return = float((1 + expected_daily_return) ** horizon_days - 1)
    cum_sigma = resid_std_daily * float(np.sqrt(horizon_days))

    return {
        "expected_return_pct": cum_simple_return * 100,
        "sigma_pct": cum_sigma * 100,
        "alpha_daily_pct": alpha * 100,
        "betas": dict(zip(FACTOR_COLUMNS, (float(b) for b in betas))),
        "n_obs": int(len(df)),
    }


async def fetch_ff5_momentum_forecast(
    stock_close: pd.Series, horizon_days: int, period: str = "5y", ohlcv_cache=None
) -> PredictionResult:
    """Récupère les 7 ETF proxys en parallèle (même cache que le reste du projet si `ohlcv_cache`
    est fourni), ajuste et prévoit. Fonction async car elle fait des appels réseau — appelée comme
    une tâche parallèle dans `pipeline.run_forecast`, pas depuis le thread CPU de `_compute`."""
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

    result = fit_ff5_momentum_forecast(stock_close, proxy_closes, horizon_days=horizon_days)
    return PredictionResult(mu_pct=result["expected_return_pct"], sigma_pct=result["sigma_pct"], diagnostics=result)
