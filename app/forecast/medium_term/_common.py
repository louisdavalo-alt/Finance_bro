"""Utilitaires communs aux modèles « moyen terme » (1–12 mois) : ces modèles sont historiquement
étudiés sur un horizon de détention standard d'~1 mois (21 jours de bourse). Chaque module ajuste
donc sa régression/son modèle sur cette base, puis `scale_to_horizon` met le résultat à l'échelle
du `horizon_days` réellement demandé (celui du pipeline : 5 jours à "1 semaine", 21 jours à
"1 mois" — ces modèles ne tournent qu'à "1 mois", voir `pipeline.py`).

Mise à l'échelle : rendement proportionnel au nombre de jours (hypothèse d'un rendement moyen
constant par jour), écart-type en racine carrée du rapport (même hypothèse de marche aléatoire que
les modèles court terme, `short_term/`)."""
from __future__ import annotations

MONTH_TRADING_DAYS = 21


def scale_to_horizon(mu_pct_per_month: float, sigma_pct_per_month: float, horizon_days: int) -> tuple[float, float]:
    ratio = horizon_days / MONTH_TRADING_DAYS
    return mu_pct_per_month * ratio, sigma_pct_per_month * (ratio**0.5)
