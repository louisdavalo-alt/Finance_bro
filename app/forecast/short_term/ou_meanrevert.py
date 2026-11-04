"""Retour à la moyenne façon Ornstein-Uhlenbeck.

⚠️ Simplification explicite : la version classique s'applique au SPREAD de deux actifs
cointégrés (trading de paires), pas au prix d'une action seule — un prix d'action individuel n'a
en général aucune raison de revenir à une moyenne fixe. Ce module applique l'OU à un seul actif :
l'écart entre le log-prix et sa moyenne glissante sur `ma_window` jours, qui a bien, PAR
CONSTRUCTION (c'est un écart à une moyenne glissante du même prix), une dynamique de retour vers
zéro — mais ce n'est pas un signal de paires cointégrées. Un vrai module de paires (test de
cointégration/ADF sur le spread, univers de paires candidates) reste à construire séparément et
n'est pas ce que fait ce module.

Estimation par AR(1) discrétisé sur la déviation : x_{t+1} = a + b·x_t + ε, avec θ = -ln(|b|) la
vitesse de retour à la moyenne journalière (plus θ est grand, plus le retour est rapide)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..model_base import PredictionResult

MIN_OBS = 80


def fit_ou_meanreversion_forecast(close: pd.Series, horizon_days: int = 5, ma_window: int = 60) -> dict:
    log_price = np.log(close.dropna())
    deviation = (log_price - log_price.rolling(ma_window).mean()).dropna()
    if len(deviation) < MIN_OBS:
        raise ValueError(
            f"historique trop court pour un ajustement OU fiable ({len(deviation)} points, {MIN_OBS} recommandés)"
        )

    x = deviation.values[:-1]
    y = deviation.values[1:]
    b, a = np.polyfit(x, y, 1)  # np.polyfit(x, y, 1) -> [pente, intercept] = [b, a]
    resid = y - (a + b * x)
    resid_std = float(np.std(resid))

    b_clamped = float(np.clip(b, -0.999, 0.999))  # |b|>=1 : pas de retour à la moyenne ; on borne pour rester interprétable
    theta = -np.log(abs(b_clamped)) if b_clamped != 0 else np.inf
    long_run_mean = a / (1 - b_clamped) if abs(1 - b_clamped) > 1e-9 else 0.0

    current_dev = float(deviation.iloc[-1])
    dev_path = []
    d = current_dev
    for _ in range(horizon_days):
        d = a + b_clamped * d
        dev_path.append(d)

    cum_log_return = dev_path[-1] - current_dev  # rendement log impliqué par le retour vers la moyenne glissante
    cum_sigma = resid_std * np.sqrt(horizon_days)  # approximation : accumulation des chocs sur l'horizon

    return {
        "expected_return_pct": (np.exp(cum_log_return) - 1) * 100,
        "sigma_pct": cum_sigma * 100,
        "half_life_days": (float(np.log(2) / theta) if np.isfinite(theta) and theta > 0 else None),
        "current_deviation_pct": (np.exp(current_dev) - 1) * 100,
        "long_run_mean_deviation_pct": (np.exp(long_run_mean) - 1) * 100,
        "ma_window": ma_window,
        "n_obs": int(len(deviation)),
    }


class OuMeanRevertModel:
    name = "ou_meanrevert"

    def predict(self, bars: pd.DataFrame, horizon_days: int) -> PredictionResult:
        result = fit_ou_meanreversion_forecast(bars["Close"], horizon_days=horizon_days)
        return PredictionResult(
            mu_pct=result["expected_return_pct"], sigma_pct=result["sigma_pct"], diagnostics=result
        )
