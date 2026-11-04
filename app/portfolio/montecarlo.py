"""Simulation de Monte Carlo par bootstrap par blocs : évalue la distribution des performances
futures possibles d'un portefeuille à poids fixes, à partir de SES rendements journaliers
historiques réels — pas d'hypothèse de normalité des rendements.

Principe : plutôt que de tirer des rendements aléatoires dans une loi normale (ce qui sous-estime
systématiquement le risque de queue, un biais bien documenté en finance), on rééchantillonne des
BLOCS CONTIGUS de jours historiques réels du portefeuille — en gardant toutes les actions
ensemble pour préserver leur corrélation du jour — et on les met bout à bout pour simuler des
trajectoires futures plausibles. C'est un bootstrap PAR BLOCS, pas un bootstrap i.i.d. jour par
jour : un rééchantillonnage jour par jour détruirait les régimes de volatilité (un jour calme
suivi d'un jour calme, un jour agité suivi d'un jour agité, le même phénomène que modélise GARCH
ailleurs dans ce projet). Garder les lignes intactes (plutôt que de rééchantillonner chaque
colonne séparément) est tout aussi essentiel : c'est ce qui préserve la corrélation entre les
actifs un jour donné — vérifié par
`tests/test_portfolio.py::test_bootstrap_preserves_cross_asset_correlation`.

⚠️ Comme tout bootstrap historique : les résultats reflètent fidèlement CE QUI S'EST PASSÉ sur la
période d'historique utilisée, pas une prévision de l'avenir — un choc sans précédent dans les
données utilisées (un krach plus sévère que tout ce qui s'est produit dans la fenêtre d'historique,
par exemple) n'est pas capturé.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

MIN_HISTORY_FOR_BLOCK = 2  # au moins 2x block_size jours d'historique, sinon le bootstrap n'a presque aucune variété de blocs à piocher


def simulate_portfolio(
    aligned_returns: pd.DataFrame, weights: pd.Series,
    horizon_days: int = 252, n_sims: int = 2000, block_size: int = 21, seed: int | None = None,
) -> dict:
    """`aligned_returns` : rendements log quotidiens (T jours × N actifs), déjà alignés sur un
    historique commun (voir `stats.compute_return_stats`). `weights` : poids du portefeuille
    (mêmes codes que les colonnes de `aligned_returns`, pas nécessairement dans le même ordre).

    Renvoie un résumé de la distribution des rendements cumulés sur `horizon_days` jours de
    bourse : percentiles, probabilité de perte, VaR/CVaR à 95 %, et une bande de percentiles
    jour par jour (`fan_chart_pct`) pour un graphique en éventail."""
    codes = list(weights.index)
    missing = [c for c in codes if c not in aligned_returns.columns]
    if missing:
        raise ValueError(f"codes absents de la matrice de rendements : {missing}")

    R = aligned_returns[codes].to_numpy()
    w = weights.to_numpy()
    T = R.shape[0]

    if T < block_size * MIN_HISTORY_FOR_BLOCK:
        raise ValueError(
            f"historique trop court ({T} jours) pour des blocs de {block_size} jours "
            f"({block_size * MIN_HISTORY_FOR_BLOCK} jours minimum)"
        )

    rng = np.random.default_rng(seed)
    n_blocks_needed = int(np.ceil(horizon_days / block_size))
    max_start = T - block_size

    # Version vectorisée (avant : boucle Python sur chaque trajectoire, avec concaténation de
    # blocs T×N à chaque tour). Les poids étant FIXES, le rendement quotidien du portefeuille
    # (R @ w) ne dépend que du jour historique tiré : on le calcule une seule fois, puis on
    # rééchantillonne directement ce vecteur. Tirer un jour historique pour le portefeuille revient
    # exactement à tirer la LIGNE complète de R pour ce jour (toutes les actions ensemble) : la
    # corrélation entre actifs est préservée à l'identique. Mêmes tirages aléatoires qu'avant pour
    # une même graine (un seul appel de taille (n_sims, n_blocks) au lieu de n_sims appels).
    port_hist = R @ w  # (T,) rendement log quotidien historique du portefeuille
    starts = rng.integers(0, max_start + 1, size=(n_sims, n_blocks_needed))
    day_idx = (starts[:, :, None] + np.arange(block_size)).reshape(n_sims, -1)[:, :horizon_days]
    all_paths = np.exp(np.cumsum(port_hist[day_idx], axis=1))  # valeur relative, 1.0 = valeur initiale
    del day_idx

    final_return_pct = (all_paths[:, -1] - 1.0) * 100
    percentile_levels = (5, 25, 50, 75, 95)
    percentiles = {str(p): float(np.percentile(final_return_pct, p)) for p in percentile_levels}

    var_95 = percentiles["5"]  # au moins 5% de chances de faire pire que ce rendement
    tail = final_return_pct[final_return_pct <= var_95]
    cvar_95 = float(tail.mean()) if tail.size else var_95

    # Un seul tri pour les 5 percentiles (au lieu de 5 appels séparés sur la matrice complète).
    fan = (np.percentile(all_paths, percentile_levels, axis=0) - 1.0) * 100
    fan_chart_pct = {str(p): fan[i].tolist() for i, p in enumerate(percentile_levels)}

    return {
        "n_sims": n_sims,
        "horizon_days": horizon_days,
        "block_size": block_size,
        "n_history_days": T,
        "percentiles_final_return_pct": percentiles,
        "probability_of_loss_pct": float((final_return_pct < 0).mean() * 100),
        "var_95_pct": var_95,
        "cvar_95_pct": cvar_95,
        "fan_chart_pct": fan_chart_pct,
    }
