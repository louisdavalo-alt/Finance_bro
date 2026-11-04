"""HAR-RV (Heterogeneous Autoregressive model of Realized Volatility, Corsi 2009) : régresse la
volatilité réalisée de demain sur ses composantes jour / semaine / mois — référence simple et
robuste pour la prévision de VOLATILITÉ à très court terme, souvent proche d'un GARCH en
pratique mais sans hypothèse de processus ARCH. Ce modèle ne prévoit aucun rendement moyen
(`mu_pct` vaut toujours 0.0, voir `HarRvModel.predict`) — c'est un modèle de risque, pas de
direction.

Proxy de volatilité réalisée : carré du rendement log quotidien. Le HAR-RV original utilise une
vraie RV intrajournalière (somme de rendements à haute fréquence) ; faute de données intraday
dans ce projet (barres quotidiennes `yfinance`), on reprend l'approximation standard RV_t ≈
r_t², comme documenté dans la littérature appliquée lorsque seules des données quotidiennes sont
disponibles.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..model_base import PredictionResult

MIN_OBS = 80  # il faut de quoi construire une moyenne glissante de 22 jours + marge pour l'OLS


def fit_har_rv_forecast(log_returns: pd.Series, horizon_days: int = 5) -> dict:
    """Ajuste RV_{t+1} = c + b_d·RV_d,t + b_w·RV_w,t + b_m·RV_m,t par OLS, puis projette la
    variance jour par jour sur `horizon_days` en faisant glisser les fenêtres jour/semaine/mois
    avec les valeurs prévues (chaque jour prévu devient une pseudo-observation pour le suivant).
    L'écart-type sur l'horizon complet est la racine de la somme des variances journalières
    prévues (même convention d'agrégation que `garch.fit_garch_forecast`)."""
    r = log_returns.dropna()
    if len(r) < MIN_OBS:
        raise ValueError(f"historique trop court pour un HAR-RV fiable ({len(r)} points, {MIN_OBS} recommandés)")

    rv_d = r.pow(2)
    rv_w = rv_d.rolling(5).mean()
    rv_m = rv_d.rolling(22).mean()
    train = pd.DataFrame({"rv_d": rv_d, "rv_w": rv_w, "rv_m": rv_m})
    train["target"] = train["rv_d"].shift(-1)
    fit_df = train.dropna()
    if len(fit_df) < 30:
        raise ValueError("pas assez de lignes exploitables pour ajuster le HAR-RV")

    X = np.column_stack(
        [np.ones(len(fit_df)), fit_df["rv_d"].values, fit_df["rv_w"].values, fit_df["rv_m"].values]
    )
    y = fit_df["target"].values
    coeffs, *_ = np.linalg.lstsq(X, y, rcond=None)
    c, b_d, b_w, b_m = (float(v) for v in coeffs)

    resid = y - X @ coeffs
    resid_std_pct = float(np.sqrt(np.var(resid))) * 100

    # contexte de départ pour la projection itérative : les 22 derniers RV_d réels (pas leurs
    # seules moyennes), pour pouvoir faire glisser les fenêtres jour après jour.
    hist = list(rv_d.dropna().values[-22:])
    daily_var: list[float] = []
    for _ in range(horizon_days):
        rv_d_t = hist[-1]
        rv_w_t = float(np.mean(hist[-5:]))
        rv_m_t = float(np.mean(hist[-22:]))
        nxt = c + b_d * rv_d_t + b_w * rv_w_t + b_m * rv_m_t
        nxt = max(nxt, 1e-12)  # une variance ne peut pas être négative, mais l'OLS ne le garantit pas
        daily_var.append(nxt)
        hist.append(nxt)
        hist = hist[-22:]

    sigma_pct = float(np.sqrt(sum(daily_var))) * 100

    return {
        "sigma_pct": sigma_pct,
        "daily_vol_forecast_pct": [float(np.sqrt(v)) * 100 for v in daily_var],
        "params": {"const": c, "b_day": b_d, "b_week": b_w, "b_month": b_m},
        "residual_std_pct": resid_std_pct,
        "n_obs": int(len(fit_df)),
    }


class HarRvModel:
    name = "har_rv"

    def predict(self, bars: pd.DataFrame, horizon_days: int) -> PredictionResult:
        log_ret = np.log(bars["Close"]).diff()
        result = fit_har_rv_forecast(log_ret, horizon_days=horizon_days)
        return PredictionResult(mu_pct=0.0, sigma_pct=result["sigma_pct"], diagnostics=result)
