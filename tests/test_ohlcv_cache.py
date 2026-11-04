"""Cache OHLCV local (ohlcv_cache.py) et récupération incrémentale (marketdata.py) : vérifie
qu'un second appel pour le même symbole, le même jour, ne redemande RIEN à Yahoo Finance, et
qu'un appel un autre jour ne redemande que les jours manquants (`start=`), jamais tout
l'historique."""
import datetime as dt

import pandas as pd
import pytest

from app.marketdata import _period_cutoff, get_daily_bars
from app.ohlcv_cache import OhlcvCache


def _bars(dates: list[str], start_close: float = 100.0) -> pd.DataFrame:
    idx = pd.to_datetime(dates)
    closes = [start_close + i for i in range(len(dates))]
    return pd.DataFrame(
        {
            "Open": closes,
            "High": [c + 1 for c in closes],
            "Low": [c - 1 for c in closes],
            "Close": closes,
            "Volume": [1000 + i for i in range(len(dates))],
        },
        index=idx,
    )


@pytest.fixture()
def cache(tmp_path):
    c = OhlcvCache(tmp_path)
    yield c
    c.close()


def test_upsert_then_read_roundtrip(cache):
    assert cache.last_date("DAX") is None
    df = pd.DataFrame(
        {
            "date": [dt.date(2026, 1, 2), dt.date(2026, 1, 3)],
            "open": [100.0, 101.0],
            "high": [105.0, 106.0],
            "low": [99.0, 100.0],
            "close": [104.0, 105.0],
            "volume": [1000.0, 1200.0],
        }
    )
    cache.upsert("DAX", df)
    assert cache.last_date("DAX") == dt.date(2026, 1, 3)
    rows = cache.read("DAX")
    assert len(rows) == 2
    assert rows[0] == {"date": "2026-01-02", "open": 100.0, "high": 105.0, "low": 99.0, "close": 104.0, "volume": 1000.0}


def test_upsert_overwrites_existing_date_instead_of_duplicating(cache):
    df1 = pd.DataFrame({"date": [dt.date(2026, 1, 2)], "open": [100.0], "high": [101.0], "low": [99.0], "close": [100.5], "volume": [10.0]})
    df2 = pd.DataFrame({"date": [dt.date(2026, 1, 2)], "open": [100.0], "high": [102.0], "low": [99.0], "close": [101.5], "volume": [20.0]})
    cache.upsert("DAX", df1)
    cache.upsert("DAX", df2)
    rows = cache.read("DAX")
    assert len(rows) == 1
    assert rows[0]["close"] == 101.5
    assert rows[0]["volume"] == 20.0


def test_read_with_start_filters_older_rows(cache):
    df = pd.DataFrame(
        {
            "date": [dt.date(2026, 1, 1), dt.date(2026, 1, 10), dt.date(2026, 1, 20)],
            "open": [1.0, 2.0, 3.0], "high": [1.0, 2.0, 3.0], "low": [1.0, 2.0, 3.0],
            "close": [1.0, 2.0, 3.0], "volume": [1.0, 2.0, 3.0],
        }
    )
    cache.upsert("DAX", df)
    rows = cache.read("DAX", start=dt.date(2026, 1, 10))
    assert [r["date"] for r in rows] == ["2026-01-10", "2026-01-20"]


def test_read_with_end_filters_newer_rows(cache):
    """`end` (borne point-in-time, voir `app/forecast/feature_store.py`) : aucune barre
    postérieure à `end` ne doit être renvoyée, même si elle est déjà en cache."""
    df = pd.DataFrame(
        {
            "date": [dt.date(2026, 1, 1), dt.date(2026, 1, 10), dt.date(2026, 1, 20)],
            "open": [1.0, 2.0, 3.0], "high": [1.0, 2.0, 3.0], "low": [1.0, 2.0, 3.0],
            "close": [1.0, 2.0, 3.0], "volume": [1.0, 2.0, 3.0],
        }
    )
    cache.upsert("DAX", df)
    rows = cache.read("DAX", end=dt.date(2026, 1, 10))
    assert [r["date"] for r in rows] == ["2026-01-01", "2026-01-10"]
    rows = cache.read("DAX", start=dt.date(2026, 1, 5), end=dt.date(2026, 1, 15))
    assert [r["date"] for r in rows] == ["2026-01-10"]


def test_period_cutoff_ytd_and_max():
    today = dt.date(2026, 10, 21)
    assert _period_cutoff("ytd", today) == dt.date(2026, 1, 1)
    assert _period_cutoff("max", today) is None
    assert _period_cutoff("1y", today) == today - dt.timedelta(days=365)


@pytest.mark.asyncio
async def test_first_fetch_backfills_with_period_max(cache, monkeypatch):
    """Cache vide : la première récupération doit demander TOUT l'historique (`period="max"`),
    pas seulement la fenêtre affichée — pour pouvoir servir localement n'importe quelle fenêtre
    plus tard sans nouvel appel réseau."""
    calls = []

    class _FakeTicker:
        def __init__(self, symbol):
            self.symbol = symbol

        def history(self, period=None, auto_adjust=True, interval=None, start=None):
            calls.append({"period": period, "start": start})
            return _bars(["2020-01-02", "2020-01-03"])

    class _FakeYf:
        Ticker = _FakeTicker

    import sys

    monkeypatch.setitem(sys.modules, "yfinance", _FakeYf)

    bars = await get_daily_bars("DAX", "max", cache)
    assert len(calls) == 1
    assert calls[0]["period"] == "max"
    assert calls[0]["start"] is None
    assert len(bars) == 2


@pytest.mark.asyncio
async def test_second_call_same_day_skips_network_entirely(cache, monkeypatch):
    """Le cœur de la fonctionnalité demandée : une fois le cache à jour pour aujourd'hui, un
    second appel (même session, même journée) ne doit déclencher AUCUN appel à Yahoo Finance."""
    calls = []
    today = dt.date.today()

    class _FakeTicker:
        def __init__(self, symbol):
            self.symbol = symbol

        def history(self, period=None, auto_adjust=True, interval=None, start=None):
            calls.append(1)
            return _bars([today.isoformat()])

    class _FakeYf:
        Ticker = _FakeTicker

    import sys

    monkeypatch.setitem(sys.modules, "yfinance", _FakeYf)

    first = await get_daily_bars("DAX", "max", cache)
    second = await get_daily_bars("DAX", "max", cache)
    assert len(calls) == 1  # un seul appel réseau pour les deux requêtes
    assert first == second


@pytest.mark.asyncio
async def test_stale_cache_refetches_only_missing_tail(cache, monkeypatch):
    """Cache déjà peuplé jusqu'à une date passée (pas aujourd'hui) : le second appel doit
    utiliser `start=<dernière date en cache>`, jamais `period=` — on ne redemande que les jours
    manquants, pas tout l'historique."""
    df = pd.DataFrame(
        {"date": [dt.date(2026, 1, 2)], "open": [100.0], "high": [101.0], "low": [99.0], "close": [100.5], "volume": [10.0]}
    )
    cache.upsert("DAX", df)

    calls = []

    class _FakeTicker:
        def __init__(self, symbol):
            self.symbol = symbol

        def history(self, period=None, auto_adjust=True, interval=None, start=None):
            calls.append({"period": period, "start": start})
            return _bars(["2026-01-03"], start_close=200.0)

    class _FakeYf:
        Ticker = _FakeTicker

    import sys

    monkeypatch.setitem(sys.modules, "yfinance", _FakeYf)

    bars = await get_daily_bars("DAX", "max", cache)
    assert len(calls) == 1
    assert calls[0]["period"] is None
    assert calls[0]["start"] == dt.date(2026, 1, 2)
    assert len(bars) == 2  # l'ancienne barre du 2 janvier + la nouvelle du 3 janvier
