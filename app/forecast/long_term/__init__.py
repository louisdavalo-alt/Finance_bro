"""Modèles de prévision à long terme (1–10 ans) NON liés à une IA, listés dans l'architecture du
projet, section « Modèles de prédiction par horizon » (long terme) :

- `cape.py`                 — CAPE de Shiller : proxy P/E trailing (réseau : `get_info()`).
- `dividend_yield.py`       — Régression du rendement du dividende : own-series (réseau : `dividends`).
- `gordon_ddm.py`           — Gordon/DDM : dividende + croissance (réseau : `dividends`).
- `implied_erp.py`          — Prime de risque implicite (CAPM, marché SPY + ^TNX, réseau).
- `value_profitability.py`  — Facteurs value/profitabilité : ETF proxys (réseau).
- `cointegration_vecm.py`   — Cointégration/VECM titre/marché (réseau).

Les six ont besoin d'un appel réseau (fondamentaux du titre, ETF proxys, indices) : ce sont des
fonctions `async fetch_*_forecast(...)`, appelées comme des tâches parallèles dans
`pipeline.run_forecast` (même schéma que les modèles moyen terme réseau), jamais depuis le thread
CPU de `_compute` — il n'y a donc pas de `SYNC_MODELS` ici (à la différence de `short_term/` et
`medium_term/`). Comme les modèles moyen terme, ils ne tournent qu'à l'horizon « 1 mois » (voir
`pipeline.py`) — un rendement annuel projeté sur 5 jours de bourse n'aurait aucun sens."""
from __future__ import annotations

from .cape import fetch_cape_forecast
from .cointegration_vecm import fetch_cointegration_vecm_forecast
from .dividend_yield import fetch_dividend_yield_forecast
from .gordon_ddm import fetch_gordon_ddm_forecast
from .implied_erp import fetch_implied_erp_forecast
from .value_profitability import fetch_value_profitability_forecast

__all__ = [
    "fetch_cape_forecast",
    "fetch_cointegration_vecm_forecast",
    "fetch_dividend_yield_forecast",
    "fetch_gordon_ddm_forecast",
    "fetch_implied_erp_forecast",
    "fetch_value_profitability_forecast",
]
