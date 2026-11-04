"""Time-series momentum (Moskowitz, Ooi & Pedersen, 2012) — momentum ABSOLU : contrairement au
momentum 12-1 (`momentum_12_1.py`, qui compare le titre aux AUTRES titres d'un univers), le TSMOM
ne regarde que le SIGNE du rendement passé du titre lui-même sur 12 mois, sans comparaison
cross-sectionnelle — un titre qui a monté continue statistiquement à monter (et inversement), sur
un large éventail de classes d'actifs selon la littérature. Ce module régresse le rendement futur
sur le SIGNE (−1/+1) du rendement passé, pas sur sa MAGNITUDE (c'est la magnitude qui est régressée
dans `momentum_12_1.py`) — c'est la distinction conceptuelle entre les deux facteurs.

⚠️ Ce module ne fait pas de ciblage de volatilité (`position = signe × vol_cible / vol_réalisée`,
comme dans l'article original) : c'est un modèle de PRÉVISION de rendement, pas un
dimensionnement de position — celui-ci relèverait de la construction de portefeuille, hors scope
de ce module."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..model_base import PredictionResult
from ._common import scale_to_horizon

LOOKBACK_DAYS = 252
HOLDING_DAYS = 21
MIN_OBS = 400


def fit_ts_momentum_forecast(close: pd.Series, horizon_days: int = 21) -> dict:
    trailing = close.pct_change(LOOKBACK_DAYS)
    sign = np.sign(trailing)
    fwd = close.shift(-HOLDING_DAYS) / close - 1

    df = pd.DataFrame({"sign": sign, "fwd": fwd}).dropna()
    df = df[df["sign"] != 0]  # un rendement passé exactement nul n'a pas de direction à exploiter
    if len(df) < MIN_OBS:
        raise ValueError(f"historique trop court pour un TSMOM fiable ({len(df)} points, {MIN_OBS} recommandés)")

    b, a = np.polyfit(df["sign"].values, df["fwd"].values, 1)
    resid = df["fwd"].values - (a + b * df["sign"].values)
    resid_std = float(np.std(resid))

    last_trailing = float(trailing.dropna().iloc[-1])
    last_sign = float(np.sign(last_trailing)) or 1.0  # signe nul (rare) traité comme haussier par convention
    predicted_monthly = float(a + b * last_sign)

    mu_pct, sigma_pct = scale_to_horizon(predicted_monthly * 100, resid_std * 100, horizon_days)
    return {
        "expected_return_pct": mu_pct,
        "sigma_pct": sigma_pct,
        "slope": float(b),
        "intercept": float(a),
        "trailing_12m_sign": int(last_sign),
        "trailing_12m_return_pct": last_trailing * 100,
        "n_obs": int(len(df)),
    }


class TsMomentumModel:
    name = "ts_momentum"

    def predict(self, bars: pd.DataFrame, horizon_days: int) -> PredictionResult:
        result = fit_ts_momentum_forecast(bars["Close"], horizon_days=horizon_days)
        return PredictionResult(
            mu_pct=result["expected_return_pct"], sigma_pct=result["sigma_pct"], diagnostics=result
        )
