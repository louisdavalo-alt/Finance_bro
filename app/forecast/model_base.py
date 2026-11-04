"""Interface commune à tous les modèles de prévision classés par horizon (voir l'architecture
du projet, section « Modèles de prédiction par horizon ») : `predict(ticker, as_of, horizon) ->
{mu, sigma, quantiles}`.

Ce `Protocol` reste volontairement posé sur des barres OHLCV déjà récupérées
(`predict(self, bars, horizon_days)`), PAS sur `(ticker, as_of)` directement : chaque modèle
reste une fonction pure testable isolément sans dépendre d'une base ou d'un réseau (voir
`har_rv.py`, `arima_baseline.py`, etc.), et la classe ci-dessous n'est qu'un adaptateur fin vers
le contrat commun.

Le feature store point-in-time existe maintenant (`feature_store.py`, au-dessus de
`app/ohlcv_cache.py` — pas une nouvelle table, voir son docstring) et l'adaptateur externe
annoncé ci-dessus EST câblé : `predict.py` expose `predict_one`/`predict_all`, qui prennent
exactement `(ticker, as_of, horizon)`, lisent les barres point-in-time puis délèguent à
`HorizonModel.predict` tel quel — aucune des 17 classes de modèles n'a eu besoin d'être
réécrite, exactement le découplage que ce module préparait. Seuls les 8 modèles qui ne lisent que
`bars` (5 court terme + 3 moyen terme « own-series ») passent par cet adaptateur ; les 9 modèles
réseau (moyen/long terme) restent appelés via `pipeline.run_forecast`, toujours « en direct »
(voir le docstring de `predict.py`).

Pour le futur backtest walk-forward et la méta-pondération (étapes suivantes de l'architecture,
pas encore construites) : `predict_one`/`predict_all` sont déjà la bonne forme d'appel — répéter
`as_of` sur une grille de dates passées pour un même ticker ne coûte qu'un seul appel réseau
(voir `feature_store.py`), le reste est purement local.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import pandas as pd


@dataclass
class PredictionResult:
    """`mu_pct`/`sigma_pct` : rendement moyen et écart-type prévus sur `horizon_days`, en %.
    `quantiles_pct` : optionnel, ex. {"5": ..., "50": ..., "95": ...} (rendement cumulé, en %).
    `diagnostics` : détails propres au modèle (paramètres ajustés, etc.), pour l'affichage et le
    débogage — jamais utilisé par le backtest/la pondération, qui ne regardent que mu/sigma."""

    mu_pct: float
    sigma_pct: float
    quantiles_pct: dict[str, float] = field(default_factory=dict)
    diagnostics: dict = field(default_factory=dict)


class HorizonModel(Protocol):
    """Tout modèle de prévision par horizon implémente ceci. `name` identifie le modèle dans les
    réponses de l'API et, plus tard, dans `model_metrics`/`model_weights`."""

    name: str

    def predict(self, bars: pd.DataFrame, horizon_days: int) -> PredictionResult: ...
