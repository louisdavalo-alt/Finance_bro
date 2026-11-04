"""Modèles de prévision à court terme (1 jour–2 semaines) NON liés à une IA, implémentés sur
l'interface commune `app/forecast/model_base.py` (`HorizonModel`/`PredictionResult`).

Vient compléter le GARCH déjà en place (`app/forecast/garch.py`) : cinq modèles classiques listés
dans l'architecture du projet, section « Modèles de prédiction par horizon » (court terme) :

- `har_rv.py`      — HAR-RV (Corsi) : volatilité réalisée, régression jour/semaine/mois.
- `arima_baseline.py` — ARIMA sur les rendements log quotidiens.
- `kalman_trend.py`   — tendance locale linéaire filtrée (Kalman via `statsmodels`).
- `ou_meanrevert.py`  — retour à la moyenne façon Ornstein-Uhlenbeck.
- `reversal.py`       — retournement à court terme.

Les deux derniers sont des SIMPLIFICATIONS explicitement documentées dans leur module : la
version complète (paires cointégrées pour OU, facteur cross-sectionnel pour le retournement)
suppose une infrastructure multi-titres qui n'existe pas encore dans ce projet.

Chaque module expose une fonction pure `fit_*_forecast(...)` (testable isolément, mêmes
conventions que `garch.fit_garch_forecast`) et une classe `*Model` qui l'enveloppe pour se
conformer au protocole `HorizonModel`. `MODELS` liste les cinq classes, pour l'orchestration dans
`pipeline.py`.
"""
from __future__ import annotations

from .arima_baseline import ArimaModel
from .har_rv import HarRvModel
from .kalman_trend import KalmanTrendModel
from .ou_meanrevert import OuMeanRevertModel
from .reversal import ReversalModel

MODELS = [HarRvModel, ArimaModel, KalmanTrendModel, OuMeanRevertModel, ReversalModel]

__all__ = [
    "HarRvModel",
    "ArimaModel",
    "KalmanTrendModel",
    "OuMeanRevertModel",
    "ReversalModel",
    "MODELS",
]
