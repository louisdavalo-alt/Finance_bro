"""Volatilité à très court terme via un GARCH(1,1) (distribution de Student, plus réaliste que
la normale pour des rendements financiers) sur les rendements log quotidiens. Nécessite le
paquet `arch` (Kevin Sheppard) : `pip install arch`.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


class ArchNotInstalled(ImportError):
    pass


MIN_OBS = 250  # ~1 an de bourse : en dessous, un GARCH(1,1) est peu fiable


def fit_garch_forecast(log_returns: pd.Series, horizon: int = 5) -> dict:
    """Ajuste un GARCH(1,1)-t sur `log_returns` (rendements log bruts, PAS en %) et prévoit la
    volatilité des `horizon` prochains jours de bourse.

    Renvoie :
      - daily_vol_forecast_pct : volatilité prévue jour par jour sur l'horizon (en %)
      - weekly_vol_forecast_pct : volatilité cumulée sur l'horizon, racine de la somme des
        variances (convention standard d'agrégation sous indépendance conditionnelle)
      - current_conditional_vol_annualized_pct : volatilité conditionnelle du dernier jour
        observé, annualisée (racine de 252) — pour comparer au régime récent
      - params : paramètres ajustés du modèle (omega, alpha[1], beta[1], nu)
    """
    try:
        from arch import arch_model
    except ImportError as exc:
        raise ArchNotInstalled("le paquet 'arch' n'est pas installé : `pip install arch`") from exc

    r = log_returns.dropna() * 100  # arch converge mieux sur des rendements exprimés en %
    if len(r) < MIN_OBS:
        raise ValueError(f"historique trop court pour un GARCH fiable ({len(r)} points, {MIN_OBS} recommandés)")

    am = arch_model(r, mean="Constant", vol="Garch", p=1, q=1, dist="t")
    res = am.fit(disp="off")
    fc = res.forecast(horizon=horizon, reindex=False)

    daily_var_pct2 = fc.variance.values[-1]  # variance prévue par jour, en %^2
    daily_vol_pct = np.sqrt(daily_var_pct2)  # écart-type prévu par jour, en %
    weekly_vol_pct = float(np.sqrt(daily_var_pct2.sum()))

    current_vol_pct = float(res.conditional_volatility.iloc[-1])
    current_vol_annualized_pct = current_vol_pct * np.sqrt(252)

    return {
        "daily_vol_forecast_pct": [float(v) for v in daily_vol_pct],
        "weekly_vol_forecast_pct": weekly_vol_pct,
        "current_conditional_vol_annualized_pct": current_vol_annualized_pct,
        "params": {str(k): float(v) for k, v in res.params.items()},
        "n_obs": int(len(r)),
    }
