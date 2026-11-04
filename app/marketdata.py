"""Historique OHLCV quotidien pour la vue graphique, servi depuis le cache local
(`ohlcv_cache.py`) avec récupération incrémentale auprès de Yahoo Finance : au lieu de
retélécharger tout l'historique à chaque ouverture du graphique, on ne redemande que les jours
manquants depuis la dernière barre déjà en cache pour CE symbole (et, dans la même journée,
aucun appel réseau du tout — le cache est déjà considéré à jour).

Utilisé par `/ohlc` (vue graphique avancée, via `get_daily_bars`), par `/forecast` (GARCH/
XGBoost/régime/Kronos, via `get_daily_bars_frame` — l'historique 5 ans ne change quasiment pas
d'un appel à l'autre pour un même titre, c'est le cas d'usage qui profite le plus de ne pas tout
retélécharger) et par les plages quotidiennes de `/chart` (1M/3M/1Y/5Y/YTD, via `get_daily_bars`
aussi — voir `app/quote.py`). Les plages intraday (1D/5D, barres de 5/30 min) et hebdomadaire
(MAX) de `/chart` ne correspondent pas au même modèle de barres quotidiennes et restent en appel
direct.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import os
import threading
import time

import pandas as pd

from .connectors.yfin import _fetch_history_sync
from .ohlcv_cache import OhlcvCache

# Correspond aux options de PERIOD_PATTERN côté API (voir api.py) : approximation en jours
# calendaires, cohérente avec la tolérance déjà acceptée pour une fenêtre d'affichage/modèle
# (quelques jours de plus ou de moins ne changent rien à un graphique ou à un GARCH sur 5 ans).
# Délai minimal entre deux synchronisations Yahoo d'un même symbole quand le cache n'est pas
# encore « à jour du jour » (voir `_sync_cache_sync`). 0 désactive le délai.
MIN_RESYNC_S = float(os.environ.get("OHLCV_MIN_RESYNC_S", 900))

_PERIOD_DAYS = {"1mo": 31, "3mo": 93, "6mo": 186, "1y": 365, "2y": 730, "5y": 1825, "10y": 3650}


def _period_cutoff(period: str, today: dt.date) -> dt.date | None:
    """Date la plus ancienne à conserver pour une fenêtre `period` — `None` pour "max" (pas de
    borne, tout ce qui est en cache est renvoyé)."""
    if period == "max":
        return None
    if period == "ytd":
        return dt.date(today.year, 1, 1)
    return today - dt.timedelta(days=_PERIOD_DAYS[period])


def _sync_cache_sync(symbol: str, cache: OhlcvCache) -> None:
    """Backfill complet (`period="max"`, la toute première fois pour ce symbole) ou
    récupération des seuls jours manquants depuis la dernière barre en cache (`start=`). Ne fait
    rien si le cache est déjà à jour pour la date du jour — c'est précisément ce qui évite de
    retélécharger tout l'historique à chaque ouverture du graphique."""
    with cache.sync_guard:
        lock = cache.sync_locks.setdefault(symbol, threading.Lock())
    with lock:
        last = cache.last_date(symbol)
        today = dt.date.today()
        if last is not None and last >= today:
            return
        synced = cache.last_sync.get(symbol)
        if last is not None and synced is not None and time.monotonic() - synced < MIN_RESYNC_S:
            return
        _download_into_cache(symbol, last, cache)
        cache.last_sync[symbol] = time.monotonic()


def _download_into_cache(symbol: str, last: dt.date | None, cache: OhlcvCache) -> None:
    df = _fetch_history_sync(symbol, period=None if last else "max", start=last)
    if df is None or df.empty:
        return
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    if df.empty:
        return
    bars = df[["Open", "High", "Low", "Close", "Volume"]].reset_index()
    bars.columns = ["date", "open", "high", "low", "close", "volume"]
    bars["date"] = bars["date"].dt.date
    cache.upsert(symbol, bars)


async def get_daily_bars(symbol: str, period: str, cache: OhlcvCache) -> list[dict]:
    """Barres quotidiennes `{date, open, high, low, close, volume}` pour `symbol`, triées du
    plus ancien au plus récent — même forme que l'ancien appel direct à Yahoo Finance
    (`ohlc.fetch_ohlcv`), pour rester un remplacement direct partout où ce format est attendu."""
    await asyncio.to_thread(_sync_cache_sync, symbol, cache)
    cutoff = _period_cutoff(period, dt.date.today())
    return await asyncio.to_thread(cache.read, symbol, cutoff)


async def get_daily_bars_frame(symbol: str, period: str, cache: OhlcvCache) -> pd.DataFrame:
    """Même historique que `get_daily_bars`, mais sous la forme DataFrame
    Open/High/Low/Close/Volume indexée par date attendue par le pipeline de prévision
    (`app/forecast/pipeline.py`) et le client Kronos — un remplacement direct de l'ancien appel
    à `_fetch_history_sync` pour ce qui les concerne."""
    rows = await get_daily_bars(symbol, period, cache)
    if not rows:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    df = pd.DataFrame(rows)
    df.index = pd.DatetimeIndex(pd.to_datetime(df.pop("date")))
    df.columns = ["Open", "High", "Low", "Close", "Volume"]
    return df
