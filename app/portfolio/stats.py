"""Statistiques historiques (rendement annualisé, covariance) pour le constructeur de
portefeuille — lues dans ce que le pipeline principal a DÉJÀ COLLECTÉ en base (comme
`macro_context.py` pour le modèle à 1 mois), aucun appel réseau ici. Si `run_pipeline.sh` n'a pas
tourné récemment pour tel titre, ou si un titre a échoué, il est simplement absent du calcul.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252
MIN_OBS = 180  # ~9 mois de bourse : en dessous, covariance et rendement annualisés peu fiables


def compute_return_stats(store, codes: list[str]) -> tuple[pd.Series, pd.DataFrame, list[str], pd.DataFrame]:
    """Renvoie (rendements annualisés, matrice de covariance annualisée, codes effectivement
    utilisés, matrice des rendements log quotidiens alignés) à partir des séries de clôture déjà
    en base pour `codes`. Les titres sans assez d'historique commun sont exclus plutôt que de
    forcer un calcul peu fiable — `codes_used` le reflète pour que l'appelant puisse le signaler.
    Le 4e élément (rendements quotidiens bruts, non annualisés) alimente le bootstrap de
    Monte Carlo (`montecarlo.py`), qui a besoin de l'historique jour par jour, pas seulement de
    son résumé moyenne/covariance."""
    empty = (pd.Series(dtype=float), pd.DataFrame(), [], pd.DataFrame())
    if not codes:
        return empty

    long_df = store.read_panel(codes, columns=["timestamp", "indicator_code", "value"])
    if long_df.empty:
        return empty

    # `pivot` (sans agrégation) est ~3x plus rapide que `pivot_table` ; un éventuel doublon
    # (timestamp, code) est d'abord réduit à la dernière valeur, pour rester robuste.
    wide = (
        long_df.drop_duplicates(["timestamp", "indicator_code"], keep="last")
        .pivot(index="timestamp", columns="indicator_code", values="value")
        .sort_index(axis=1)
    )
    wide = wide.sort_index()
    returns = np.log(wide).diff().dropna(how="all")

    # Ne garder que les titres avec au moins MIN_OBS observations communes (intersection des
    # dates valides pour TOUS les titres gardés), pour que la matrice de covariance repose sur un
    # historique commun cohérent plutôt que sur des paires de dates partiellement manquantes.
    enough = [c for c in returns.columns if returns[c].notna().sum() >= MIN_OBS]
    if not enough:
        return empty

    aligned = returns[enough].dropna(how="any")
    if len(aligned) < MIN_OBS or aligned.shape[1] == 0:
        return empty

    mean_returns = aligned.mean() * TRADING_DAYS_PER_YEAR
    cov_matrix = aligned.cov() * TRADING_DAYS_PER_YEAR
    return mean_returns, cov_matrix, list(aligned.columns), aligned
