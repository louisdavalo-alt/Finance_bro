"""Première brique du « feature store point-in-time » décrit dans l'architecture (couche 3) :
pas de nouvelle table — `app/ohlcv_cache.py` (déjà le cache incrémental de barres OHLCV quotidien
pour `/ohlc`/`/forecast`/`/chart`) JOUE DÉJÀ le rôle de `raw_prices` : une ligne par
(symbole, date), upsert idempotent, persistant entre redémarrages. Il lui manquait juste une borne
haute sur la date pour pouvoir répondre « comme si on était à telle date passée » plutôt que
toujours « jusqu'à aujourd'hui » — c'est tout ce que ce module ajoute, via `end=` sur
`OhlcvCache.read` (voir son docstring).

Pourquoi ne PAS créer une table séparée : dupliquer les barres dans un `raw_prices` à part aurait
voulu dire deux caches à synchroniser pour la même donnée (celui-ci et `ohlcv_cache.py`), pour
aucun bénéfice réel — une barre quotidienne est connue le jour même, sans délai de publication à
modéliser comme pour les séries macro de `cache.Store` (`release_date`). `features_daily` (couche
3 de l'architecture) n'existe pas non plus ici : les 8 modèles « own-series » de court/moyen
terme recalculent leurs propres indicateurs à la volée à partir des barres (`bars["Close"]`), ce
qui reste bon marché — un tel cache de features ne gagnerait sa place que lorsque le backtest
walk-forward (étape 2 de l'architecture, pas encore demandée) rendra ce recalcul répété coûteux.

`read_point_in_time_bars` est le SEUL point d'entrée : il garantit qu'aucune barre postérieure à
`as_of` ne fuite dans le résultat (`end=as_of` sur la lecture), tout en minimisant les appels
réseau — un seul cas déclenche une synchronisation Yahoo Finance :
- `as_of` est aujourd'hui (ou dans le futur, ramené à aujourd'hui) : usage « en direct », comme
  les autres consommateurs du cache (`marketdata.get_daily_bars`) — récupère les barres
  manquantes depuis la dernière connue.
- rien n'est encore en cache du tout pour ce symbole : un premier backfill complet
  (`period="max"`) est nécessaire pour pouvoir répondre à N'IMPORTE QUEL `as_of` passé par la
  suite SANS nouvel appel réseau — exactement le même raisonnement que le premier appel de
  `marketdata._sync_cache_sync`.
Dans tous les autres cas (symbole déjà connu, `as_of` dans le passé), la lecture est purement
locale : interroger le même titre pour plusieurs dates `as_of` différentes (le cas d'usage du
futur backtest walk-forward) ne coûte qu'UN appel réseau au total, pas un par date testée.
"""
from __future__ import annotations

import asyncio
import datetime as dt

import pandas as pd

from ..marketdata import _sync_cache_sync
from ..ohlcv_cache import OhlcvCache


async def read_point_in_time_bars(symbol: str, as_of: dt.date, cache: OhlcvCache) -> pd.DataFrame:
    """Barres OHLCV de `symbol` connues « comme si on était à `as_of` » (toutes les dates <=
    `as_of`, jamais au-delà), sous la forme `DataFrame` Open/High/Low/Close/Volume indexée par
    date attendue par `HorizonModel.predict` (même forme que `marketdata.get_daily_bars_frame`).
    Renvoie un DataFrame vide si rien n'est disponible (symbole inconnu, ou historique trop
    récent pour couvrir `as_of`)."""
    today = dt.date.today()
    needs_live_sync = as_of >= today
    if not needs_live_sync:
        last = await asyncio.to_thread(cache.last_date, symbol)
        needs_live_sync = last is None  # jamais rien en cache : backfill complet, une seule fois
    if needs_live_sync:
        await asyncio.to_thread(_sync_cache_sync, symbol, cache)

    rows = await asyncio.to_thread(cache.read, symbol, None, as_of)
    if not rows:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    df = pd.DataFrame(rows)
    df.index = pd.DatetimeIndex(pd.to_datetime(df.pop("date")))
    df.columns = ["Open", "High", "Low", "Close", "Volume"]
    return df
