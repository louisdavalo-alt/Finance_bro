"""Tendance latente lissée par filtre de Kalman — modèle "local linear trend" de Harvey, ajusté
via `statsmodels.tsa.statespace.structural.UnobservedComponents` (le package dédié `pykalman`
n'est pas installé dans ce projet ; `UnobservedComponents` résout le même filtre de Kalman pour
cette famille de modèles à espace d'état, en restant dans une dépendance déjà présente).

Le modèle sépare, dans le log-prix, un niveau et une pente qui évoluent lentement (marches
aléatoires imbriquées), et projette cette tendance filtrée sur l'horizon — à la différence d'un
ARIMA sur les rendements qui suppose une moyenne constante, le filtre de Kalman laisse la
tendance dérive au cours du temps.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..model_base import PredictionResult

MIN_OBS = 120


def fit_kalman_trend_forecast(close: pd.Series, horizon_days: int = 5) -> dict:
    from statsmodels.tsa.statespace.structural import UnobservedComponents

    log_price = np.log(close.dropna())
    if len(log_price) < MIN_OBS:
        raise ValueError(
            f"historique trop court pour un filtre de Kalman fiable ({len(log_price)} points, {MIN_OBS} recommandés)"
        )

    res = UnobservedComponents(log_price.values, level="local linear trend").fit(disp=False)
    fc = res.get_forecast(steps=horizon_days)
    mean_fc = np.asarray(fc.predicted_mean)  # log-prix prévu, jour par jour
    se_fc = np.asarray(fc.se_mean)

    last_log_price = float(log_price.iloc[-1])
    cum_log_return = float(mean_fc[-1] - last_log_price)
    cum_sigma = float(se_fc[-1])  # incertitude du log-prix prévu au terme de l'horizon

    diagnostics = {
        "expected_return_pct": (np.exp(cum_log_return) - 1) * 100,
        "sigma_pct": cum_sigma * 100,
        "aic": float(res.aic),
        "n_obs": int(len(log_price)),
    }

    # état filtré (niveau/pente) : purement informatif, on ne bloque pas la prévision si
    # l'extraction échoue (la forme exacte de smoothed_state peut varier selon la version).
    try:
        level = float(res.smoothed_state[0, -1])
        trend = float(res.smoothed_state[1, -1])
        diagnostics["latent_level"] = float(np.exp(level))
        diagnostics["latent_daily_trend_pct"] = trend * 100
    except Exception:
        pass

    return diagnostics


class KalmanTrendModel:
    name = "kalman_trend"

    def predict(self, bars: pd.DataFrame, horizon_days: int) -> PredictionResult:
        result = fit_kalman_trend_forecast(bars["Close"], horizon_days=horizon_days)
        return PredictionResult(
            mu_pct=result["expected_return_pct"], sigma_pct=result["sigma_pct"], diagnostics=result
        )
