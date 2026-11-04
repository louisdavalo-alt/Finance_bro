"""Limiteur de débit asynchrone : un seau à jetons par source.

Chaque source a son propre `TokenBucket`, construit à partir de son `RateLimit`
(`config.py`). `acquire()` attend le temps nécessaire plutôt que de rejeter la requête :
adapté à un pipeline planifié, pas à une API interactive.
"""
from __future__ import annotations

import asyncio
import time

from .config import RateLimit


class TokenBucket:
    def __init__(self, limit: RateLimit):
        self.capacity = max(1, limit.max_calls)
        self.refill_rate = self.capacity / limit.per_seconds  # jetons par seconde
        self._tokens = float(self.capacity)
        self._last = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, weight: float = 1.0) -> None:
        while True:
            async with self._lock:
                now = time.monotonic()
                elapsed = now - self._last
                self._last = now
                self._tokens = min(self.capacity, self._tokens + elapsed * self.refill_rate)
                if self._tokens >= weight:
                    self._tokens -= weight
                    return
                wait = (weight - self._tokens) / self.refill_rate
            await asyncio.sleep(wait)


class RateLimiterRegistry:
    """Un seau par nom de source, créé à la demande."""

    def __init__(self):
        self._buckets: dict[str, TokenBucket] = {}

    def get(self, name: str, limit: RateLimit) -> TokenBucket:
        b = self._buckets.get(name)
        if b is None:
            b = TokenBucket(limit)
            self._buckets[name] = b
        return b
