"""Retournement à très court terme ("short-term reversal").

⚠️ Simplification explicite : le signal classique (Jegadeesh, 1990) est TRANSVERSAL — les
perdants de la semaine écoulée, en moyenne sur un large univers de titres, surperforment les
gagnants la semaine/le mois suivant — et a donc besoin d'un univers de titres comparés entre eux,
pas d'un seul ticker. Ce module en propose une version simplifiée à un seul actif ("own-series") :
régression historique du rendement futur de CE titre sur son propre rendement des 5 derniers
jours. Ce n'est pas le facteur cross-sectionnel complet ; celui-ci resterait à construire
séparément, avec un univers d'actions comparées (le pipeline macro/actions du projet ne collecte
pas encore un tel univers multi-titres en lot)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..model_base import PredictionResult

MIN_OBS = 120
LOOKBACK_DAYS = 5


def fit_reversal_forecast(close: pd.Series, horizon_days: int = 5) -> dict:
    past = close.pct_change(LOOKBACK_DAYS)
    fwd = close.shift(-horizon_days) / close - 1

    df = pd.DataFrame({"past": past, "fwd": fwd}).dropna()
    if len(df) < MIN_OBS:
        raise ValueError(
            f"historique trop court pour estimer un retournement fiable ({len(df)} points, {MIN_OBS} recommandés)"
        )

    b, a = np.polyfit(df["past"].values, df["fwd"].values, 1)
    resid = df["fwd"].values - (a + b * df["past"].values)
    resid_std = float(np.std(resid))

    last_past_return = float(past.dropna().iloc[-1])
    predicted_fwd_return = float(a + b * last_past_return)

    return {
        "expected_return_pct": predicted_fwd_return * 100,
        "sigma_pct": resid_std * 100,
        "slope": float(b),
        "intercept": float(a),
        "last_5d_return_pct": last_past_return * 100,
        "n_obs": int(len(df)),
    }


class ReversalModel:
    name = "reversal"

    def predict(self, bars: pd.DataFrame, horizon_days: int) -> PredictionResult:
        result = fit_reversal_forecast(bars["Close"], horizon_days=horizon_days)
        return PredictionResult(
            mu_pct=result["expected_return_pct"], sigma_pct=result["sigma_pct"], diagnostics=result
        )
