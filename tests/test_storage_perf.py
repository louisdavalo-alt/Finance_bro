"""Tests du stockage (export Parquet incrémental et atomique, lecture sans verrou) et du cache
mémoire de l'API."""
import asyncio
import os

import pandas as pd
import pytest

from app.cache import ParquetReader, Store
from app.livecache import LiveCache
from app.schema import build_frame


def _frame(code, values, start="2024-01-01"):
    ts = pd.date_range(start, periods=len(values), freq="MS")
    return build_frame(timestamp=ts, country="USA", indicator_code=code, value=values, frequency="M", unit="%", source="fred", publication_lag_days=10)


def test_parquet_rewritten_only_when_series_changes(tmp_path):
    store = Store(tmp_path)
    try:
        store.upsert_observations(pd.concat([_frame("A", [1, 2, 3]), _frame("B", [4, 5])]))
        pa, pb = store.parquet_dir / "A.parquet", store.parquet_dir / "B.parquet"
        mtime_a, mtime_b = pa.stat().st_mtime_ns, pb.stat().st_mtime_ns

        # Même données (cas typique : réponse servie par le cache) -> aucun fichier ré-écrit.
        store.upsert_observations(pd.concat([_frame("A", [1, 2, 3]), _frame("B", [4, 5])]))
        assert pa.stat().st_mtime_ns == mtime_a and pb.stat().st_mtime_ns == mtime_b

        # Une valeur révisée sur B -> seul B est ré-écrit, et contient la révision.
        store.upsert_observations(pd.concat([_frame("A", [1, 2, 3]), _frame("B", [4, 6])]))
        assert pa.stat().st_mtime_ns == mtime_a
        assert pb.stat().st_mtime_ns != mtime_b
        assert pd.read_parquet(pb)["value"].tolist() == [4, 6]

        # Export manquant (ex. supprimé à la main) -> recréé même sans changement.
        pa.unlink()
        store.upsert_observations(_frame("A", [1, 2, 3]))
        assert pa.is_file()
        # Aucun fichier temporaire ne traîne.
        assert not [p for p in os.listdir(store.parquet_dir) if p.endswith(".tmp")]
    finally:
        store.close()


def test_reader_works_while_pipeline_holds_the_database(tmp_path):
    """L'ancien « Conflicting lock is held » : l'API et le pipeline ouverts en même temps."""
    store = Store(tmp_path)
    reader = ParquetReader(tmp_path)
    try:
        store.upsert_observations(pd.concat([_frame("A", [1, 2, 3]), _frame("B", [4, 5])]))
        assert reader.read_series("A")["value"].tolist() == [1, 2, 3]
        assert set(reader.read_panel(["A", "B"])["indicator_code"]) == {"A", "B"}
        assert reader.read_series("NOPE").empty
        assert reader.read_series("../etc/passwd").empty  # code invalide : ignoré, pas lu

        listing = reader.list_indicators().set_index("indicator_code")
        assert listing.loc["A", "n_obs"] == 3

        # Le cache d'agrégats est invalidé dès qu'un export change.
        store.upsert_observations(_frame("A", [1, 2, 3, 4]))
        assert reader.list_indicators().set_index("indicator_code").loc["A", "n_obs"] == 4

        lag = reader.lag_report().set_index("indicator_code")
        assert lag.loc["A", "median_lag_days"] == 10
    finally:
        reader.close()
        store.close()


def test_reader_matches_store_semantics(tmp_path):
    store = Store(tmp_path)
    reader = ParquetReader(tmp_path)
    try:
        store.upsert_observations(pd.concat([_frame("A", [1.5, 2.5]), _frame("B", [3.0])]))
        a, b = store.read_panel(["A", "B"]), reader.read_panel(["A", "B"])
        pd.testing.assert_frame_equal(a.reset_index(drop=True), b.reset_index(drop=True), check_dtype=False)
    finally:
        reader.close()
        store.close()


def test_empty_reader(tmp_path):
    reader = ParquetReader(tmp_path)
    try:
        assert reader.read_panel(None).empty
        assert reader.list_indicators().empty
        assert reader.lag_report().empty
    finally:
        reader.close()


@pytest.mark.asyncio
async def test_livecache_single_flight_and_ttl():
    cache = LiveCache(max_concurrent=2)
    calls = 0

    async def compute():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.05)
        return {"v": calls}

    r = await asyncio.gather(*(cache.get(("k",), 60, compute) for _ in range(5)))
    assert calls == 1 and all(x == {"v": 1} for x in r)  # 5 requêtes simultanées, 1 seul calcul
    assert await cache.get(("k",), 60, compute) == {"v": 1}  # servi depuis le cache
    assert calls == 1
    await cache.get(("k2",), 0, compute)  # TTL 0 : pas de mise en cache
    await cache.get(("k2",), 0, compute)
    assert calls == 3


@pytest.mark.asyncio
async def test_livecache_errors_are_not_cached():
    cache = LiveCache()
    n = 0

    async def flaky():
        nonlocal n
        n += 1
        if n == 1:
            raise RuntimeError("boom")
        return 42

    with pytest.raises(RuntimeError):
        await cache.get(("x",), 60, flaky)
    assert await cache.get(("x",), 60, flaky) == 42


@pytest.mark.asyncio
async def test_livecache_concurrency_limit():
    cache = LiveCache(max_concurrent=1)
    running = peak = 0

    async def job():
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.02)
        running -= 1
        return 1

    await asyncio.gather(*(cache.run_limited(job) for _ in range(4)))
    assert peak == 1
