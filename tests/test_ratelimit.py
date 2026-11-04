"""Tests du seau à jetons asynchrone."""
import asyncio
import time

from app.config import RateLimit
from app.ratelimit import TokenBucket


def test_bucket_allows_burst_up_to_capacity():
    async def run():
        bucket = TokenBucket(RateLimit(max_calls=3, per_seconds=60))
        start = time.monotonic()
        for _ in range(3):
            await bucket.acquire()
        return time.monotonic() - start

    elapsed = asyncio.run(run())
    assert elapsed < 0.05  # les 3 premiers jetons sont immédiats (capacité pleine au départ)


def test_bucket_throttles_beyond_capacity():
    async def run():
        bucket = TokenBucket(RateLimit(max_calls=2, per_seconds=0.2))  # 1 jeton / 0.1 s
        for _ in range(2):
            await bucket.acquire()
        start = time.monotonic()
        await bucket.acquire()  # doit attendre le réapprovisionnement
        return time.monotonic() - start

    elapsed = asyncio.run(run())
    assert elapsed >= 0.08
