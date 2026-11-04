"""Utilitaires communs aux modèles « long terme » (1–10 ans) : la littérature académique derrière
ces modèles (CAPE, Gordon/DDM, prime de risque implicite...) raisonne en rendement ANNUEL
attendu, pas en rendement sur quelques jours. Chaque module calcule donc un rendement/écart-type
ANNUEL, puis `scale_to_horizon` le met à l'échelle du `horizon_days` réellement demandé par le
pipeline (5 jours à "1 semaine", 21 jours à "1 mois" — ces modèles ne tournent qu'à "1 mois", voir
`pipeline.py` ; projeter un rendement annuel sur 5/21 jours reste une approximation grossière,
documentée comme telle — la vraie valeur de ces modèles est à l'échelle de l'année, pas du mois).

Mise à l'échelle : même convention que `medium_term/_common.py` (rendement proportionnel au
nombre de jours, écart-type en racine carrée du rapport)."""
from __future__ import annotations

ANNUAL_TRADING_DAYS = 252


def scale_to_horizon(mu_pct_per_year: float, sigma_pct_per_year: float, horizon_days: int) -> tuple[float, float]:
    ratio = horizon_days / ANNUAL_TRADING_DAYS
    return mu_pct_per_year * ratio, sigma_pct_per_year * (ratio**0.5)
