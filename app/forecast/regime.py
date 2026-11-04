"""Détection de régime de marché via un Hidden Markov Model (HMM) gaussien, ajusté sur deux
variables par jour : le rendement log et la volatilité réalisée sur `vol_window` jours. Objectif :
distinguer des phases (haussière, baissière, range/haute volatilité) pour, à terme, activer des
modèles différents selon le régime en cours — voir le README, section « Onglet Prévision ». Nécessite `hmmlearn` (`pip install hmmlearn`).

Les états bruts d'un HMM n'ont pas d'ordre ni de nom : `hmmlearn` numérote ses états
arbitrairement. L'étiquetage ci-dessous (Haussier/Baissier/Range) est fait APRÈS l'ajustement, en
triant les états par leur rendement moyen — donc stable et interprétable d'un ajustement à
l'autre sur un même actif, mais peut changer de numéro de composant sous-jacent sans que ça n'ait
d'importance pour la lecture du résultat.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


class HmmlearnNotInstalled(ImportError):
    pass


MIN_OBS = 250  # ~1 an de bourse : en dessous, un HMM à plusieurs états est peu fiable


def _label_states(n_states: int, means: np.ndarray) -> dict[int, str]:
    order = np.argsort(means)  # indices triés du rendement moyen le plus bas au plus haut
    if n_states == 2:
        return {int(order[0]): "Baissier", int(order[1]): "Haussier"}
    if n_states == 3:
        return {int(order[0]): "Baissier", int(order[1]): "Range / haute volatilité", int(order[2]): "Haussier"}
    return {int(idx): f"État {rank + 1} (rendement moyen croissant)" for rank, idx in enumerate(order)}


def fit_regimes(log_returns: pd.Series, n_states: int = 3, vol_window: int = 10) -> dict:
    try:
        from hmmlearn.hmm import GaussianHMM
    except ImportError as exc:
        raise HmmlearnNotInstalled("le paquet 'hmmlearn' n'est pas installé : `pip install hmmlearn`") from exc
    if n_states not in (2, 3):
        raise ValueError("n_states doit être 2 ou 3")

    returns = log_returns.dropna()
    vol = returns.rolling(vol_window).std()
    X = pd.concat([returns, vol], axis=1).dropna()
    X.columns = ["ret", "vol"]
    if len(X) < MIN_OBS:
        raise ValueError(f"historique trop court pour un HMM fiable ({len(X)} points, {MIN_OBS} recommandés)")

    # covariance "diag" plutôt que "full" : avec seulement 2 variables (rendement, volatilité),
    # une covariance pleine peut devenir numériquement singulière (non définie positive) faute
    # de données assez distinctes entre états — "diag" est nettement plus robuste ici, au prix
    # de ne pas modéliser la corrélation entre rendement et volatilité (acceptable : ce n'est
    # pas ce qu'on cherche à capturer, seulement des régimes de niveau/dispersion différents).
    model = GaussianHMM(n_components=n_states, covariance_type="diag", n_iter=200, random_state=0, min_covar=1e-4)
    model.fit(X[["ret", "vol"]].values)
    hidden_states = model.predict(X[["ret", "vol"]].values)

    means = model.means_[:, 0]  # rendement moyen par état (1ère colonne de la moyenne du vecteur [ret, vol])
    labels = _label_states(n_states, means)

    current_state = int(hidden_states[-1])
    state_summary = {
        labels[i]: {
            "mean_daily_return_pct": float(means[i] * 100),
            "std_daily_return_pct": float(np.sqrt(model.covars_[i][0, 0]) * 100),
            "n_days_observed": int((hidden_states == i).sum()),
        }
        for i in range(n_states)
    }

    tail = min(40, len(X))
    recent_sequence = [
        {"date": str(X.index[i].date()), "regime": labels[int(hidden_states[i])]}
        for i in range(len(X) - tail, len(X))
    ]

    return {
        "n_states": n_states,
        "current_regime": labels[current_state],
        "current_regime_since": str(X.index[_run_start(hidden_states, current_state)].date()),
        "state_summary": state_summary,
        "transition_matrix": [[float(p) for p in row] for row in model.transmat_],
        "recent_regime_sequence": recent_sequence,
        "n_obs": int(len(X)),
    }


def _run_start(hidden_states: np.ndarray, state: int) -> int:
    """Indice de début de la série courante dans l'état `state` (pour dire depuis quand le
    régime actuel dure)."""
    i = len(hidden_states) - 1
    while i > 0 and hidden_states[i - 1] == state:
        i -= 1
    return i
