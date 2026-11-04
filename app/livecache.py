"""Petit cache mémoire à durée de vie (TTL) pour les appels À LA DEMANDE de l'API (Yahoo Finance,
prévision) — avec dédoublonnage des requêtes simultanées (« single-flight ») et une limite de
concurrence.

Pourquoi : `/ohlc`, `/quote`, `/chart` et `/forecast` appelaient Yahoo à CHAQUE ouverture de
vue, et `/forecast` ré-entraînait 6 modèles XGBoost + un GARCH + un HMM à chaque clic. Deux onglets
ouverts sur le même titre doublaient le travail, et une rafale de requêtes pouvait saturer la
machine (ou faire bloquer l'adresse IP par Yahoo). Ici :
- une réponse récente (TTL court, réglable dans `.env`) est resservie telle quelle ;
- deux requêtes identiques simultanées partagent le même calcul ;
- au plus `max_concurrent` calculs tournent en même temps, les suivants attendent
  (`Busy` -> 503 côté API si l'attente dépasse `queue_timeout_s`).

Les valeurs renvoyées sont PARTAGÉES entre requêtes : l'appelant ne doit pas les modifier (toute
mise en forme se fait dans `compute`, avant la mise en cache).
"""
from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from typing import Awaitable, Callable


class Busy(RuntimeError):
    """Trop de calculs en cours : la requête a attendu trop longtemps son tour."""


class LiveCache:
    def __init__(self, max_concurrent: int = 2, max_entries: int = 256, queue_timeout_s: float = 60.0):
        self._entries: OrderedDict[tuple, tuple[float, object]] = OrderedDict()
        self._inflight: dict[tuple, asyncio.Future] = {}
        self._sem = asyncio.Semaphore(max_concurrent)
        self._max_entries = max_entries
        self._queue_timeout_s = queue_timeout_s

    async def get(self, key: tuple, ttl_s: float, compute: Callable[[], Awaitable[object]]):
        now = time.monotonic()
        hit = self._entries.get(key)
        if hit is not None and hit[0] > now:
            self._entries.move_to_end(key)
            return hit[1]

        pending = self._inflight.get(key)
        if pending is not None:
            try:
                return await asyncio.shield(pending)
            except asyncio.CancelledError:
                if pending.cancelled():  # le calcul partagé a été annulé (client parti) : on le relance
                    return await self.get(key, ttl_s, compute)
                raise

        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._inflight[key] = fut
        try:
            try:
                await asyncio.wait_for(self._sem.acquire(), timeout=self._queue_timeout_s)
            except asyncio.TimeoutError:
                raise Busy("serveur occupé : trop de calculs en cours, réessaie dans un instant") from None
            try:
                value = await compute()
            finally:
                self._sem.release()
        except asyncio.CancelledError:
            fut.cancel()
            raise
        except BaseException as exc:
            if not fut.done():
                fut.set_exception(exc)
                fut.exception()  # marque l'exception comme récupérée (pas d'avertissement asyncio)
            raise
        else:
            if ttl_s > 0 and value is not None:
                self._entries[key] = (time.monotonic() + ttl_s, value)
                self._entries.move_to_end(key)
                while len(self._entries) > self._max_entries:
                    self._entries.popitem(last=False)
            fut.set_result(value)
            return value
        finally:
            self._inflight.pop(key, None)

    async def run_limited(self, compute: Callable[[], Awaitable[object]]):
        """Exécute `compute` sous la même limite de concurrence, sans mise en cache."""
        try:
            await asyncio.wait_for(self._sem.acquire(), timeout=self._queue_timeout_s)
        except asyncio.TimeoutError:
            raise Busy("serveur occupé : trop de calculs en cours, réessaie dans un instant") from None
        try:
            return await compute()
        finally:
            self._sem.release()
