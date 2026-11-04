"""ARIMA sur les rendements log quotidiens — référence de prévision de RENDEMENT (pas de
volatilité) à très court terme. Avec l'ordre par défaut (1,0,0), c'est un AR(1) autour d'une
moyenne constante : souvent proche d'une marche aléatoire (rendement moyen ≈ rendement
historique), ce qui en fait un bon point de comparaison plutôt qu'un modèle sophistiqué. Utilise
`statsmodels` (déjà une dépendance du projet pour le contexte macro)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..model_base import PredictionResult

MIN_OBS = 120


def fit_arima_forecast(
    log_returns: pd.Series, horizon_days: int = 5, order: tuple[int, int, int] = (1, 0, 0)
) -> dict:
    from statsmodels.tsa.arima.model import ARIMA

    r = log_returns.dropna()
    if len(r) < MIN_OBS:
        raise ValueError(f"historique trop court pour un ARIMA fiable ({len(r)} points, {MIN_OBS} recommandés)")

    res = ARIMA(r.values, order=order).fit()
    fc = res.get_forecast(steps=horizon_days)
    mean_fc = np.asarray(fc.predicted_mean)  # rendement log moyen prévu, jour par jour
    se_fc = np.asarray(fc.se_mean)

    cum_log_return = float(np.sum(mean_fc))
    # agrégation sous indépendance conditionnelle, même convention que garch.fit_garch_forecast
    cum_sigma = float(np.sqrt(np.sum(se_fc**2)))

    return {
        "expected_return_pct": (np.exp(cum_log_return) - 1) * 100,
        "sigma_pct": cum_sigma * 100,
        "order": list(order),
        "daily_mean_log_return_pct": [float(v) * 100 for v in mean_fc],
        "aic": float(res.aic),
        "n_obs": int(len(r)),
    }


class ArimaModel:
    name = "arima"

    def predict(self, bars: pd.DataFrame, horizon_days: int) -> PredictionResult:
        log_ret = np.log(bars["Close"]).diff()
        result = fit_arima_forecast(log_ret, horizon_days=horizon_days)
        return PredictionResult(
            mu_pct=result["expected_return_pct"], sigma_pct=result["sigma_pct"], diagnostics=result
        )
