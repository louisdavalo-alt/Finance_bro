"""Récupération OHLCV pour la vue graphique avancée du tableau de bord.

Le pipeline principal (`pipeline.py`) ne stocke qu'UNE seule valeur par observation dans DuckDB
(voir `schema.py`) — c'est suffisant pour toutes les séries macro et pour un graphique en ligne
simple. Mais les graphiques financiers (bougies, barres OHLC, Heikin Ashi, Kagi, Line Break,
Range) ont besoin d'Open/High/Low/Close/Volume complets, que le connecteur `yfinance` actuel
n'extrait pas pour les séries macro (il ne garde que la colonne `Close`, voir `connectors/yfin.py`).

Cela ne s'applique qu'aux indicateurs dont le connecteur déclaré dans `registry.py` est
"yfinance" — les indicateurs macro n'ont pas de notion d'O/H/L/C/V.

L'historique lui-même est servi par `marketdata.py`, qui le met en cache localement
(`ohlcv_cache.py`) et ne redemande à Yahoo Finance que les jours manquants depuis la dernière
barre déjà connue — plutôt que de retélécharger tout l'historique à chaque ouverture du
graphique.
"""
from __future__ import annotations

from .connectors.yfin import YFinanceNotInstalled
from .marketdata import get_daily_bars
from .ohlcv_cache import OhlcvCache


async def fetch_ohlcv(symbol: str, period: str, cache: OhlcvCache) -> list[dict]:
    """Renvoie une liste de barres quotidiennes {date, open, high, low, close, volume},
    triées du plus ancien au plus récent. Liste vide si le ticker n'a renvoyé aucune donnée."""
    return await get_daily_bars(symbol, period, cache)
