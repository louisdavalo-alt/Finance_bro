"""Optimisation de portefeuille moyenne-variance (Markowitz), à partir des statistiques
historiques de `stats.py`.

⚠️ Les rendements attendus utilisés ici sont des MOYENNES HISTORIQUES, un estimateur connu pour
être instable et peu fiable en pratique (très sensible à la période choisie) — ce n'est pas une
prévision. Quand aucun rendement cible n'est demandé, le niveau de risque choisi détermine un
compromis rendement/risque (aversion au risque) sur l'historique observé, pas une garantie pour
l'avenir. Même esprit que le reste du système de prévision : utile pour comparer des compromis,
pas pour prédire.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize

RISK_AVERSION = {"faible": 12.0, "modere": 4.0, "eleve": 1.0}


class InfeasibleTarget(ValueError):
    """Levée quand le rendement cible demandé est hors de portée de l'univers sélectionné."""


def _bounds_and_constraints(n: int, max_weight: float, target_return: float | None, mean_returns: np.ndarray):
    bounds = [(0.0, max_weight)] * n
    ones = np.ones(n)
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0, "jac": lambda w: ones}]
    if target_return is not None:
        constraints.append({"type": "ineq", "fun": lambda w, mu=mean_returns: w @ mu - target_return,
                            "jac": lambda w, mu=mean_returns: mu})
    return bounds, constraints


def optimize_weights(
    mean_returns: pd.Series, cov_matrix: pd.DataFrame,
    risk_level: str = "modere", target_return: float | None = None, max_weight: float = 0.25,
) -> pd.Series:
    """Renvoie les poids optimaux (somme à 1, bornés à `max_weight` chacun, pas de vente à
    découvert). Si `target_return` est fourni : minimise la variance sous contrainte d'atteindre
    au moins ce rendement annualisé. Sinon : maximise `w'mu - (aversion/2) w'Σw`, l'aversion étant
    fixée par `risk_level` (voir `RISK_AVERSION`)."""
    if risk_level not in RISK_AVERSION:
        raise ValueError(f"niveau de risque invalide : {risk_level!r} (attendu : {list(RISK_AVERSION)})")
    n = len(mean_returns)
    if n == 0:
        raise ValueError("aucun titre disponible pour l'optimisation")
    if n * max_weight < 1.0 - 1e-9:
        raise ValueError(f"{n} titres avec un poids maximal de {max_weight:.0%} chacun ne peuvent pas sommer à 100% — élargis l'univers ou augmente max_weight")

    mu = mean_returns.to_numpy()
    sigma = cov_matrix.to_numpy()

    if target_return is not None:
        max_reachable = float(np.max(mu))  # tout sur le titre au rendement historique le plus élevé
        if target_return > max_reachable + 1e-9:
            raise InfeasibleTarget(
                f"rendement cible ({target_return:.1%}) hors de portée : le titre le plus performant "
                f"de l'univers sélectionné affiche {max_reachable:.1%} de rendement annualisé historique."
            )

    bounds, constraints = _bounds_and_constraints(n, max_weight, target_return, mu)
    w0 = np.full(n, 1.0 / n)

    # Gradients ANALYTIQUES fournis au solveur (`jac`) : sans eux, SLSQP estime chaque gradient
    # par différences finies, soit n+1 évaluations de w'Σw par itération — sur l'univers complet
    # (~400 actions) cela prenait plus de 10 secondes ; quelques centaines de ms avec.
    if target_return is not None:
        objective = lambda w: w @ sigma @ w  # minimiser la variance seule
        gradient = lambda w: 2.0 * (sigma @ w)
    else:
        risk_aversion = RISK_AVERSION[risk_level]
        objective = lambda w: -(w @ mu) + 0.5 * risk_aversion * (w @ sigma @ w)
        gradient = lambda w: -mu + risk_aversion * (sigma @ w)

    result = minimize(objective, w0, jac=gradient, method="SLSQP", bounds=bounds, constraints=constraints,
                       options={"maxiter": 500, "ftol": 1e-10})
    if not result.success:
        raise RuntimeError(f"l'optimisation n'a pas convergé : {result.message}")

    weights = np.clip(result.x, 0, None)
    weights = weights / weights.sum()  # renormalisation : corrige les résidus numériques du solveur
    return pd.Series(weights, index=mean_returns.index)


def portfolio_summary(weights: pd.Series, mean_returns: pd.Series, cov_matrix: pd.DataFrame) -> dict:
    """Rendement et volatilité annualisés du portefeuille pondéré, et ratio rendement/volatilité
    (approximation d'un ratio de Sharpe SANS taux sans risque déduit — à interpréter comme un
    ordre de grandeur relatif entre portefeuilles, pas un vrai ratio de Sharpe)."""
    w = weights.to_numpy()
    mu = mean_returns.to_numpy()
    sigma = cov_matrix.to_numpy()
    port_return = float(w @ mu)
    port_vol = float(np.sqrt(w @ sigma @ w))
    return {
        "expected_return_pct": port_return * 100,
        "expected_vol_pct": port_vol * 100,
        "return_over_vol": (port_return / port_vol) if port_vol > 0 else None,
    }
