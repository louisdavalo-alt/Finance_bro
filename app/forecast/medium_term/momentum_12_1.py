"""Momentum 12-1 (Jegadeesh & Titman, 1993).

⚠️ Simplification à un seul actif : la version originale classe un UNIVERS de titres par leur
rendement passé sur 12 mois (en excluant le dernier mois, pour isoler l'effet de la courte
réversion à très court terme déjà couverte par `short_term/reversal.py`), et prend une position
longue sur les gagnants / courte sur les perdants RELATIVEMENT aux autres titres de l'univers.
Faute d'un tel univers multi-titres dans ce projet, ce module régresse le rendement futur du
titre sur SON PROPRE rendement passé 12-1 mois — un proxy "own-series", pas le facteur
cross-sectionnel complet (qui resterait à construire séparément, avec un univers d'actions
comparées)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..model_base import PredictionResult
from ._common import scale_to_horizon

LOOKBACK_DAYS = 252  # ~12 mois de bourse
SKIP_DAYS = 21  # dernier mois exclu (effet de retournement à très court terme)
HOLDING_DAYS = 21  # horizon de référence (~1 mois) utilisé pour l'ajustement, voir _common.py
MIN_OBS = 400


def fit_momentum_12_1_forecast(close: pd.Series, horizon_days: int = 21) -> dict:
    mom = close.shift(SKIP_DAYS) / close.shift(LOOKBACK_DAYS + SKIP_DAYS) - 1
    fwd = close.shift(-HOLDING_DAYS) / close - 1
    df = pd.DataFrame({"mom": mom, "fwd": fwd}).dropna()
    if len(df) < MIN_OBS:
        raise ValueError(
            f"historique trop court pour un momentum 12-1 fiable ({len(df)} points, {MIN_OBS} recommandés)"
        )

    b, a = np.polyfit(df["mom"].values, df["fwd"].values, 1)
    resid = df["fwd"].values - (a + b * df["mom"].values)
    resid_std = float(np.std(resid))

    last_mom = float(mom.dropna().iloc[-1])
    predicted_monthly = float(a + b * last_mom)

    mu_pct, sigma_pct = scale_to_horizon(predicted_monthly * 100, resid_std * 100, horizon_days)
    return {
        "expected_return_pct": mu_pct,
        "sigma_pct": sigma_pct,
        "slope": float(b),
        "intercept": float(a),
        "trailing_12_1_return_pct": last_mom * 100,
        "n_obs": int(len(df)),
    }


class Momentum121Model:
    name = "momentum_12_1"

    def predict(self, bars: pd.DataFrame, horizon_days: int) -> PredictionResult:
        result = fit_momentum_12_1_forecast(bars["Close"], horizon_days=horizon_days)
        return PredictionResult(
            mu_pct=result["expected_return_pct"], sigma_pct=result["sigma_pct"], diagnostics=result
        )
