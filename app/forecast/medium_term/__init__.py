"""Modèles de prévision à moyen terme (1–12 mois) NON liés à une IA, listés dans l'architecture
du projet, section « Modèles de prédiction par horizon » (moyen terme) :

- `momentum_12_1.py`    — Momentum 12-1 (Jegadeesh & Titman) : proxy own-series.
- `ts_momentum.py`      — Time-series momentum (Moskowitz, Ooi & Pedersen) : own-series, signe.
- `markov_switching.py` — Markov switching (Hamilton) : changement de régime moyenne/variance.
- `ff5_momentum.py`     — Fama-French 5 + momentum : approximé par des ETF proxys (réseau).
- `pead.py`             — Post-earnings announcement drift : via `yfinance` (réseau).
- `var_market.py`       — VAR titre/indice de marché (réseau).

Les trois premiers suivent le protocole `HorizonModel` (`model_base.py`, comme les modèles court
terme de `short_term/`) et tournent dans le thread CPU de `pipeline._compute`. Les trois derniers
ont besoin d'un appel réseau (facteurs ETF, dates de résultats, indice de marché) : ce sont des
fonctions `async fetch_*_forecast(...)`, appelées comme des tâches parallèles dans
`pipeline.run_forecast` (même schéma que `options_task`/`kronos_task`), PAS depuis le thread CPU.

Tous ces modèles ne tournent qu'à l'horizon « 1 mois » (voir `pipeline.py`) : un historique de 12
mois (momentum) ou une surprise de résultats qui se dénoue sur 1-2 trimestres (PEAD) n'a pas de
sens à l'horizon « 1 semaine »."""
from __future__ import annotations

from .ff5_momentum import fetch_ff5_momentum_forecast
from .markov_switching import MarkovSwitchingModel
from .momentum_12_1 import Momentum121Model
from .pead import fetch_pead_forecast
from .ts_momentum import TsMomentumModel
from .var_market import fetch_var_market_forecast

SYNC_MODELS = [Momentum121Model, TsMomentumModel, MarkovSwitchingModel]

__all__ = [
    "Momentum121Model",
    "TsMomentumModel",
    "MarkovSwitchingModel",
    "SYNC_MODELS",
    "fetch_ff5_momentum_forecast",
    "fetch_pead_forecast",
    "fetch_var_market_forecast",
]
