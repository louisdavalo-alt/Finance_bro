"""Post-Earnings Announcement Drift (PEAD ; Ball & Brown, 1968 ; Bernard & Thomas, 1989) : après
une surprise de résultats (EPS réel vs. consensus), le rendement continue de « dériver » dans le
sens de la surprise pendant plusieurs semaines — une anomalie bien documentée et persistante.

⚠️ Double simplification, documentée explicitement :
1. Les surprises de résultats viennent de `yfinance` (`Ticker.get_earnings_dates()`), dont la
   couverture et la qualité (dates, EPS estimé/réel) varient selon le titre et ne remontent
   souvent que sur quelques trimestres — pas une source d'estimations consensus professionnelle.
2. Faute d'assez de surprises passées pour CE titre pour estimer une pente de dérive propre à lui
   (`MIN_SURPRISES_FOR_OWN_FIT` ci-dessous), ce module se rabat sur un coefficient de dérive
   CALIBRÉ SUR LA LITTÉRATURE (pas ajusté sur ce titre) — explicitement signalé dans
   `diagnostics["fit_mode"]` ("own_regression" vs "literature_fallback")."""
from __future__ import annotations

import asyncio

import numpy as np
import pandas as pd

from ..model_base import PredictionResult

HOLDING_DAYS = 60  # littérature PEAD : la dérive se poursuit typiquement 1 à 2 trimestres
MIN_SURPRISES_FOR_OWN_FIT = 8
# Pente et volatilité calibrées sur l'ordre de grandeur usuel de la littérature (quelques % de
# rendement anormal cumulé sur le trimestre suivant pour une grosse surprise) — PAS ajustées sur
# ce titre précis, voir docstring ci-dessus.
LITERATURE_SLOPE_PCT_PER_PCT_SURPRISE = 0.03
LITERATURE_DAILY_SIGMA_PCT = 1.5


def _extract_past_surprises(earnings_dates: pd.DataFrame) -> pd.DataFrame:
    """`earnings_dates` est le DataFrame renvoyé par `Ticker.get_earnings_dates()` : on ne garde
    que les publications déjà passées avec une colonne de surprise (%) renseignée."""
    surprise_col = next((c for c in earnings_dates.columns if "surprise" in c.lower()), None)
    if surprise_col is None:
        raise ValueError("aucune colonne de surprise dans les données de résultats yfinance")

    idx = earnings_dates.index
    now = pd.Timestamp.now(tz=idx.tz) if idx.tz is not None else pd.Timestamp.now()
    past = earnings_dates[idx <= now].copy()
    past = past.dropna(subset=[surprise_col]).sort_index()
    past["surprise_pct"] = past[surprise_col].astype(float) * 100
    return past


def fit_pead_forecast(close: pd.Series, earnings_dates: pd.DataFrame, horizon_days: int = 21) -> dict:
    past = _extract_past_surprises(earnings_dates)
    if past.empty:
        raise ValueError("aucune surprise de résultats passée disponible pour ce titre")

    last_surprise_pct = float(past["surprise_pct"].iloc[-1])

    # `close.index` est tz-naive (barres yfinance) ; les dates de résultats peuvent être tz-aware
    # (ex. America/New_York) — on les ramène au même référentiel avant de chercher la barre la
    # plus proche.
    close_index = close.index
    pairs: list[tuple[float, float]] = []
    for ts, row in past.iterrows():
        ts_naive = ts.tz_localize(None) if ts.tzinfo is not None else ts
        pos = close_index.searchsorted(ts_naive)
        if pos < 0 or pos >= len(close_index) - HOLDING_DAYS:
            continue
        start_px = float(close.iloc[pos])
        end_px = float(close.iloc[pos + HOLDING_DAYS])
        pairs.append((row["surprise_pct"], (end_px / start_px - 1) * 100))

    if len(pairs) >= MIN_SURPRISES_FOR_OWN_FIT:
        surprises = np.array([p[0] for p in pairs])
        fwd_returns = np.array([p[1] for p in pairs])
        b, a = np.polyfit(surprises, fwd_returns, 1)
        resid_std_pct = float(np.std(fwd_returns - (a + b * surprises)))
        predicted_holding_return_pct = float(a + b * last_surprise_pct)
        fit_mode = "own_regression"
    else:
        predicted_holding_return_pct = LITERATURE_SLOPE_PCT_PER_PCT_SURPRISE * last_surprise_pct
        resid_std_pct = LITERATURE_DAILY_SIGMA_PCT * float(np.sqrt(HOLDING_DAYS))
        fit_mode = "literature_fallback"

    ratio = horizon_days / HOLDING_DAYS
    mu_pct = predicted_holding_return_pct * ratio
    sigma_pct = resid_std_pct * (ratio**0.5)

    return {
        "expected_return_pct": mu_pct,
        "sigma_pct": sigma_pct,
        "last_surprise_pct": last_surprise_pct,
        "n_past_surprises_used": len(pairs),
        "fit_mode": fit_mode,
    }


async def fetch_pead_forecast(symbol: str, close: pd.Series, horizon_days: int) -> PredictionResult:
    """Récupère les dates/surprises de résultats via `yfinance` — fonction async car appel
    réseau — appelée comme une tâche parallèle dans `pipeline.run_forecast`."""

    def _sync() -> pd.DataFrame:
        import yfinance as yf

        return yf.Ticker(symbol).get_earnings_dates(limit=40)

    earnings_dates = await asyncio.to_thread(_sync)
    if earnings_dates is None or earnings_dates.empty:
        raise ValueError(f"aucune date de résultats disponible pour {symbol}")

    result = fit_pead_forecast(close, earnings_dates, horizon_days=horizon_days)
    return PredictionResult(mu_pct=result["expected_return_pct"], sigma_pct=result["sigma_pct"], diagnostics=result)
