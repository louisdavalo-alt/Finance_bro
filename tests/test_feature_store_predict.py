"""Feature store point-in-time (`app/forecast/feature_store.py`) et l'interface commune
`predict(ticker, as_of, horizon)` qu'il alimente (`app/forecast/predict.py`) — la réalisation de
l'étape 1 de l'architecture (« Feature store point-in-time + interface predict() commune »).

Trois choses à vérifier, dans l'esprit anti-look-ahead du reste du projet
(`resample.align_panel`, validation walk-forward de `model.py`) :
1. aucune barre postérieure à `as_of` ne doit jamais atteindre un modèle ;
2. au plus UN appel réseau, même en interrogeant plusieurs `as_of` passés pour le même ticker ;
3. `predict_all` isole les échecs modèle par modèle, comme le reste du système de prévision.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from app.forecast.feature_store import read_point_in_time_bars
from app.forecast.predict import ALL_SYNC_MODELS, NoPointInTimeData, predict_all, predict_one
from app.forecast.short_term.arima_baseline import ArimaModel
from app.ohlcv_cache import OhlcvCache


def _bars_df(dates: list[str], seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0002, 0.015, len(dates))))
    return pd.DataFrame(
        {
            "Open": close, "High": close * 1.01, "Low": close * 0.99, "Close": close,
            "Volume": 1_000_000.0,
        },
        index=pd.to_datetime(dates),
    )


@pytest.fixture()
def cache(tmp_path):
    c = OhlcvCache(tmp_path)
    yield c
    c.close()


def _seed_cache(cache: OhlcvCache, symbol: str, n: int = 900, seed: int = 1) -> pd.DataFrame:
    """Pré-remplit le cache avec `n` barres se terminant HIER (jamais aujourd'hui), pour que les
    tests avec `as_of` dans le passé n'aient besoin d'aucune synchronisation réseau."""
    end = dt.date.today() - dt.timedelta(days=1)
    dates = pd.bdate_range(end=end, periods=n)
    bars = _bars_df([d.date().isoformat() for d in dates], seed=seed)
    payload = bars.reset_index().rename(columns={"index": "date"})
    payload["date"] = payload["date"].dt.date
    payload.columns = ["date", "open", "high", "low", "close", "volume"]
    cache.upsert(symbol, payload)
    return bars


# --------------------------------------------------------------------------- #
# feature_store.read_point_in_time_bars : pas de fuite de barres futures
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_no_future_bars_leak_past_as_of(cache):
    full = _seed_cache(cache, "TEST", n=900, seed=2)
    as_of = full.index[-100].date()  # une date bien avant la fin du cache

    got = await read_point_in_time_bars("TEST", as_of, cache)

    assert got.index.max().date() <= as_of
    # bien tronqué, pas juste "tout le cache" renvoyé sans filtrage
    assert len(got) < len(full)


@pytest.mark.asyncio
async def test_unknown_symbol_returns_empty_frame(cache, monkeypatch):
    """Symbole jamais vu ET réseau indisponible (simulé) : doit renvoyer un DataFrame vide, pas
    lever — c'est `predict_one`/`predict_all` qui transforment "vide" en erreur explicite."""
    import sys

    class _FakeTicker:
        def __init__(self, symbol):
            pass

        def history(self, period=None, auto_adjust=True, interval=None, start=None):
            return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])

    class _FakeYf:
        Ticker = _FakeTicker

    monkeypatch.setitem(sys.modules, "yfinance", _FakeYf)

    as_of = dt.date.today() - dt.timedelta(days=10)
    got = await read_point_in_time_bars("INCONNU", as_of, cache)
    assert got.empty


@pytest.mark.asyncio
async def test_repeated_past_as_of_queries_hit_network_at_most_once(cache, monkeypatch):
    """Le cas d'usage du futur backtest walk-forward : interroger le MÊME ticker à plusieurs
    `as_of` passés différents ne doit déclencher qu'UN appel réseau au total (le premier
    backfill), jamais un par date testée."""
    import sys

    calls = []
    full_dates = pd.bdate_range(end=dt.date.today() - dt.timedelta(days=1), periods=900)

    class _FakeTicker:
        def __init__(self, symbol):
            pass

        def history(self, period=None, auto_adjust=True, interval=None, start=None):
            calls.append(1)
            return _bars_df([d.date().isoformat() for d in full_dates], seed=3)

    class _FakeYf:
        Ticker = _FakeTicker

    monkeypatch.setitem(sys.modules, "yfinance", _FakeYf)

    as_of_points = [full_dates[-500].date(), full_dates[-300].date(), full_dates[-100].date()]
    for as_of in as_of_points:
        got = await read_point_in_time_bars("NEWSYM", as_of, cache)
        assert got.index.max().date() <= as_of

    assert len(calls) == 1  # un seul backfill réseau pour les trois dates interrogées


@pytest.mark.asyncio
async def test_live_as_of_today_always_syncs(cache, monkeypatch):
    """`as_of` = aujourd'hui (usage "en direct", pas backtest) : resynchronise comme les autres
    consommateurs du cache (`marketdata.get_daily_bars`), même si le symbole est déjà connu."""
    import sys

    _seed_cache(cache, "LIVE", n=50, seed=4)
    calls = []

    class _FakeTicker:
        def __init__(self, symbol):
            pass

        def history(self, period=None, auto_adjust=True, interval=None, start=None):
            calls.append(1)
            return _bars_df([dt.date.today().isoformat()], seed=5)

    class _FakeYf:
        Ticker = _FakeTicker

    monkeypatch.setitem(sys.modules, "yfinance", _FakeYf)

    await read_point_in_time_bars("LIVE", dt.date.today(), cache)
    assert len(calls) == 1


# --------------------------------------------------------------------------- #
# predict.predict_one / predict_all
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_predict_one_matches_direct_model_call_on_same_bars(cache):
    bars = _seed_cache(cache, "DIRECT", n=900, seed=6)
    as_of = bars.index[-1].date()

    via_adapter = await predict_one(ArimaModel, "DIRECT", as_of, "1m", cache)
    direct = ArimaModel().predict(bars, horizon_days=21)

    assert via_adapter.mu_pct == pytest.approx(direct.mu_pct)
    assert via_adapter.sigma_pct == pytest.approx(direct.sigma_pct)


@pytest.mark.asyncio
async def test_predict_one_raises_when_no_data(cache, monkeypatch):
    import sys

    class _FakeTicker:
        def __init__(self, symbol):
            pass

        def history(self, period=None, auto_adjust=True, interval=None, start=None):
            return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])

    class _FakeYf:
        Ticker = _FakeTicker

    monkeypatch.setitem(sys.modules, "yfinance", _FakeYf)

    with pytest.raises(NoPointInTimeData):
        await predict_one(ArimaModel, "RIEN", dt.date.today() - dt.timedelta(days=5), "1m", cache)


@pytest.mark.asyncio
async def test_predict_all_covers_all_8_sync_models_and_isolates_failures(cache):
    _seed_cache(cache, "ALL8", n=900, seed=7)
    as_of = dt.date.today() - dt.timedelta(days=1)

    results, errors = await predict_all("ALL8", as_of, "1m", cache)

    assert len(ALL_SYNC_MODELS) == 8
    names = set(results) | set(errors)
    assert len(names) == 8
    for r in results.values():
        assert isinstance(r["mu_pct"], float)
        assert isinstance(r["sigma_pct"], float)


@pytest.mark.asyncio
async def test_predict_all_rejects_invalid_horizon(cache):
    _seed_cache(cache, "BADHZ", n=900, seed=8)
    with pytest.raises(ValueError):
        await predict_all("BADHZ", dt.date.today() - dt.timedelta(days=1), "1y", cache)
