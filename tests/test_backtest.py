"""Backtest walk-forward (`app/forecast/backtest.py`, étape 2 de l'architecture) : garde-fous
anti-look-ahead (fenêtre expansive), baseline naïve, isolation des échecs modèle par modèle, et
cohérence des métriques (IC/hit_ratio/MAE/CRPS/Sharpe/Sharpe déflaté)."""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from app.forecast.backtest import (
    BASELINE_NAME,
    GARCH_NAME,
    _crps_normal,
    run_walk_forward_backtest,
)
from app.forecast.predict import ALL_SYNC_MODELS
from app.ohlcv_cache import OhlcvCache


@pytest.fixture()
def cache(tmp_path):
    c = OhlcvCache(tmp_path)
    yield c
    c.close()


def _seed_cache_ending_today(cache: OhlcvCache, symbol: str, n: int = 1200, seed: int = 0, drift: float = 0.0002) -> None:
    """Cache couvrant jusqu'à AUJOURD'HUI (pas hier) : évite tout appel réseau dans
    `read_point_in_time_bars` (voir `feature_store.py` — `as_of >= today` sinon)."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end=dt.date.today(), periods=n)
    close = 100 * np.exp(np.cumsum(rng.normal(drift, 0.015, n)))
    df = pd.DataFrame(
        {
            "date": [d.date() for d in dates], "open": close, "high": close * 1.01,
            "low": close * 0.99, "close": close, "volume": 1_000_000.0,
        }
    )
    cache.upsert(symbol, df)


# --------------------------------------------------------------------------- #
# CRPS normal : forme fermée
# --------------------------------------------------------------------------- #

def test_crps_normal_zero_when_perfectly_certain_and_correct():
    assert _crps_normal(mu_pct=1.0, sigma_pct=0.0, realized_pct=1.0) == 0.0


def test_crps_normal_degenerates_to_abs_error_without_uncertainty():
    assert _crps_normal(mu_pct=0.0, sigma_pct=0.0, realized_pct=2.5) == pytest.approx(2.5)


def test_crps_normal_positive_and_finite():
    val = _crps_normal(mu_pct=0.5, sigma_pct=2.0, realized_pct=-1.0)
    assert val > 0
    assert np.isfinite(val)


# --------------------------------------------------------------------------- #
# run_walk_forward_backtest : structure, garde-fous, isolation des échecs
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_rejects_invalid_horizon(cache):
    _seed_cache_ending_today(cache, "BADHZ")
    with pytest.raises(ValueError, match="horizon invalide"):
        await run_walk_forward_backtest("BADHZ", "1y", cache)


@pytest.mark.asyncio
async def test_rejects_insufficient_history(cache):
    _seed_cache_ending_today(cache, "SHORT", n=300)  # bien sous MIN_TRAIN_DAYS + horizon
    with pytest.raises(ValueError, match="insuffisant"):
        await run_walk_forward_backtest("SHORT", "1m", cache)


@pytest.mark.asyncio
async def test_all_models_present_including_garch_and_baseline(cache):
    _seed_cache_ending_today(cache, "FULL", n=550, seed=1)
    result = await run_walk_forward_backtest("FULL", "1m", cache)

    expected_names = {m().name for m in ALL_SYNC_MODELS} | {GARCH_NAME, BASELINE_NAME}
    present_names = set(result["models"]) | set(result["errors"])
    assert expected_names <= present_names
    assert result["n_test_points"] >= 5


@pytest.mark.asyncio
async def test_non_directional_models_have_none_hit_ratio_and_ic(cache):
    """GARCH, la baseline naïve et HAR-RV ne prennent jamais position (`mu_pct=0`
    systématique) : leur hit_ratio/IC doivent être `None`, jamais un nombre trompeur (ex. 0%, qui
    ressemblerait à un échec directionnel alors qu'aucun pari n'a été fait)."""
    _seed_cache_ending_today(cache, "NODIR", n=550, seed=2)
    result = await run_walk_forward_backtest("NODIR", "1m", cache)

    for name in (GARCH_NAME, BASELINE_NAME, "har_rv"):
        m = result["models"][name]
        assert m["hit_ratio"] is None
        assert m["ic"] is None
        assert m["n_bets"] == 0
        assert m["sharpe"] is None  # P&L constamment nul : Sharpe indéfini
        assert m["deflated_sharpe"] is None


@pytest.mark.asyncio
async def test_directional_models_have_bounded_hit_ratio_and_metrics(cache):
    _seed_cache_ending_today(cache, "DIR", n=550, seed=3)
    result = await run_walk_forward_backtest("DIR", "1m", cache)

    for name in ("arima", "kalman_trend", "reversal"):
        m = result["models"][name]
        assert m["n_bets"] > 0
        assert 0.0 <= m["hit_ratio"] <= 1.0
        assert m["mae_pct"] >= 0.0
        assert m["crps_pct"] >= 0.0
        assert -1.0 <= m["ic"] <= 1.0


@pytest.mark.asyncio
async def test_models_needing_more_history_fail_early_points_then_succeed(cache):
    """`momentum_12_1`/`ts_momentum` (MIN_OBS=400) doivent échouer sur les premiers points testés
    (fenêtre expansive encore trop courte) mais réussir une fois `min_train_days` dépassé pour
    eux — et ces échecs partiels ne doivent jamais faire disparaître le modèle des résultats."""
    _seed_cache_ending_today(cache, "GROW", n=760, seed=4)
    result = await run_walk_forward_backtest("GROW", "1m", cache, min_train_days=650)

    assert "momentum_12_1" in result["models"]
    assert result["models"]["momentum_12_1"]["n_points"] < result["n_test_points"]
    assert "momentum_12_1" in result["errors"]  # trace du dernier échec rencontré


@pytest.mark.asyncio
async def test_no_lookahead_new_future_bars_dont_change_past_as_of_reads(cache, monkeypatch):
    """Garde-fou anti-look-ahead, au niveau exact où `run_walk_forward_backtest` le délègue
    (`read_point_in_time_bars`, voir `feature_store.py`) : des barres ajoutées PLUS TARD (plus
    récentes que `as_of`) — le cas normal où de nouvelles séances arrivent au fil du temps — ne
    doivent JAMAIS changer la lecture pour un `as_of` déjà passé. `run_walk_forward_backtest`
    tronque `full_bars` de la même façon (`full_bars.iloc[:i+1]`) pour chaque point testé, donc
    cette garantie au niveau barres couvre directement le backtest aussi."""
    rng = np.random.default_rng(5)
    n_before, n_after = 550, 50
    # Toutes les dates restent nettement dans le passé (bien avant aujourd'hui), pour qu'AUCUNE
    # des deux lectures ne déclenche de resynchronisation réseau (voir `feature_store.py` :
    # seul `as_of >= aujourd'hui` ou un symbole jamais vu la déclenche).
    end_before = dt.date.today() - dt.timedelta(days=200)
    dates_before = pd.bdate_range(end=end_before, periods=n_before)
    close_before = 100 * np.exp(np.cumsum(rng.normal(0.0002, 0.015, n_before)))
    dates_after = pd.bdate_range(start=dates_before[-1] + pd.Timedelta(days=1), periods=n_after)
    close_after = close_before[-1] * np.exp(np.cumsum(rng.normal(0.0002, 0.015, n_after)))

    def _frame(dates, close):
        return pd.DataFrame(
            {
                "date": [d.date() for d in dates], "open": close, "high": close * 1.01,
                "low": close * 0.99, "close": close, "volume": 1_000_000.0,
            }
        )

    cache.upsert("GROWCACHE", _frame(dates_before, close_before))

    import sys

    class _ExplodingTicker:
        def __init__(self, symbol):
            pass

        def history(self, *a, **k):
            raise AssertionError("ne doit jamais appeler le réseau : historique déjà en cache, as_of dans le passé")

    class _FakeYf:
        Ticker = _ExplodingTicker

    monkeypatch.setitem(sys.modules, "yfinance", _FakeYf)

    from app.forecast.feature_store import read_point_in_time_bars

    as_of = dates_before[300].date()  # bien avant la fin du cache, et avant tout ajout futur
    bars_before_append = await read_point_in_time_bars("GROWCACHE", as_of, cache)
    assert len(bars_before_append) > 0

    cache.upsert("GROWCACHE", _frame(dates_after, close_after))  # "le temps passe", nouvelles barres
    bars_after_append = await read_point_in_time_bars("GROWCACHE", as_of, cache)

    pd.testing.assert_frame_equal(bars_before_append, bars_after_append)
