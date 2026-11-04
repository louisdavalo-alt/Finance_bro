"""Tests du Volet A (app/forecast/) : indicateurs techniques, absence de biais de look-ahead,
GARCH, walk-forward. Le test le plus important est `test_backtest_on_pure_noise_is_close_to_random` :
sur des rendements purement aléatoires (sans aucun signal réel), la précision directionnelle
mesurée doit rester proche de 50 % — si le pipeline « prédisait » du bruit avec un bon score, ce
serait presque toujours le signe d'une fuite de données (le même genre de bug que le biais de
look-ahead déjà traité pour les séries macro dans `resample.py`).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.forecast.features import bollinger, build_feature_frame, macd, rsi
from app.forecast.garch import ArchNotInstalled, fit_garch_forecast
from app.forecast.model import build_dataset, fit_final_and_predict, walk_forward_backtest


def _synthetic_bars(n=1500, seed=0, daily_vol=0.015, drift=0.0002) -> pd.DataFrame:
    """Barres OHLCV synthétiques (marche aléatoire), CLAIREMENT PAS des données de marché
    réelles — uniquement pour vérifier que le pipeline calcule juste et ne plante pas."""
    rng = np.random.default_rng(seed)
    log_returns = rng.normal(drift, daily_vol, n)
    close = 100 * np.exp(np.cumsum(log_returns))
    high = close * (1 + np.abs(rng.normal(0, 0.003, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.003, n)))
    open_ = np.roll(close, 1)
    open_[0] = 100
    volume = rng.integers(1_000_000, 5_000_000, n).astype(float)
    idx = pd.bdate_range("2018-01-01", periods=n)
    return pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume}, index=idx)


# --------------------------------------------------------------------------- #
# Indicateurs techniques
# --------------------------------------------------------------------------- #

def test_rsi_bounds_and_direction():
    close = pd.Series([10, 11, 12, 13, 14, 13, 12, 11, 10, 9, 8, 10, 12, 14, 16, 18, 20])
    r = rsi(close, period=5)
    valid = r.dropna()
    assert (valid >= 0).all() and (valid <= 100).all()
    # après une remontée nette et soutenue, le RSI doit être élevé (marché "suracheté")
    assert r.iloc[-1] > 70


def test_rsi_all_gains_saturates_near_100():
    close = pd.Series(range(1, 20))  # hausse stricte à chaque pas -> aucune perte
    r = rsi(close, period=5)
    assert r.dropna().iloc[-1] == pytest.approx(100.0)


def test_macd_line_equals_ema_difference():
    close = pd.Series(np.linspace(10, 20, 60))
    macd_line, signal_line, hist = macd(close, fast=12, slow=26, signal=9)
    expected = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
    pd.testing.assert_series_equal(macd_line, expected, check_names=False)
    pd.testing.assert_series_equal(hist, macd_line - signal_line, check_names=False)


def test_bollinger_band_ordering():
    close = pd.Series(np.sin(np.linspace(0, 12, 100)) * 5 + 100)
    mid, upper, lower, pct_b, bandwidth = bollinger(close, period=20)
    valid = mid.notna()
    assert (lower[valid] <= mid[valid]).all() and (mid[valid] <= upper[valid]).all()
    assert (bandwidth.dropna() >= 0).all()


def test_features_do_not_look_ahead():
    """Le cœur de la discipline anti-look-ahead : la valeur d'une feature à la date t ne doit
    JAMAIS changer selon que des lignes postérieures à t existent ou non dans l'entrée."""
    bars = _synthetic_bars(300)
    full = build_feature_frame(bars)
    truncated = build_feature_frame(bars.iloc[:200])  # coupé avant la fin

    common_idx = truncated.index[-1]  # dernière date commune aux deux calculs
    from app.forecast.features import FEATURE_COLUMNS
    for col in FEATURE_COLUMNS + ["ret_1d", "log_ret_1d"]:
        a, b = full.loc[common_idx, col], truncated.loc[common_idx, col]
        if pd.isna(a) and pd.isna(b):
            continue
        assert a == pytest.approx(b), f"{col} dépend de données futures (look-ahead)"


# --------------------------------------------------------------------------- #
# GARCH
# --------------------------------------------------------------------------- #

def test_garch_forecast_structure():
    bars = _synthetic_bars(600, seed=1)
    feat = build_feature_frame(bars)
    result = fit_garch_forecast(feat["log_ret_1d"], horizon=5)
    assert len(result["daily_vol_forecast_pct"]) == 5
    assert all(v > 0 for v in result["daily_vol_forecast_pct"])
    assert result["weekly_vol_forecast_pct"] > 0
    assert result["current_conditional_vol_annualized_pct"] > 0
    assert result["n_obs"] > 500


def test_garch_rejects_short_history():
    bars = _synthetic_bars(100, seed=2)
    feat = build_feature_frame(bars)
    with pytest.raises(ValueError):
        fit_garch_forecast(feat["log_ret_1d"], horizon=5)


# --------------------------------------------------------------------------- #
# Modèle ML — structure et, surtout, détection de fuite sur du bruit pur
# --------------------------------------------------------------------------- #

def test_walk_forward_backtest_structure():
    bars = _synthetic_bars(800, seed=3)
    dataset = build_dataset(build_feature_frame(bars))
    result = walk_forward_backtest(dataset, n_splits=4)
    assert len(result["folds"]) == 4
    for fold in result["folds"]:
        assert 0.0 <= fold["direction_accuracy"] <= 1.0
        assert fold["mae"] >= 0
    assert 0.0 <= result["mean_direction_accuracy"] <= 1.0


def test_backtest_on_pure_noise_is_close_to_random():
    """Sur une marche aléatoire pure (pas de signal exploitable par construction), la précision
    directionnelle moyenne en walk-forward doit rester proche de 50 % — loin des 65-70%+ qu'on
    verrait si une fuite de données donnait au modèle un accès indu à l'information future."""
    bars = _synthetic_bars(1500, seed=42, drift=0.0)  # dérive nulle : aucun signal directionnel
    dataset = build_dataset(build_feature_frame(bars))
    result = walk_forward_backtest(dataset, n_splits=5)
    assert 0.35 <= result["mean_direction_accuracy"] <= 0.65, (
        f"précision {result['mean_direction_accuracy']:.2%} trop loin de 50% sur du bruit pur "
        "— suspicion de fuite de données (look-ahead) dans les features ou la validation"
    )


def test_fit_final_and_predict_structure():
    bars = _synthetic_bars(800, seed=4)
    dataset = build_dataset(build_feature_frame(bars))
    result = fit_final_and_predict(dataset)
    assert isinstance(result["predicted_return_pct"], float)
    assert result["horizon_days"] == 5
    from app.forecast.features import FEATURE_COLUMNS
    assert set(result["feature_importances"]) == set(FEATURE_COLUMNS)
    assert pytest.approx(sum(result["feature_importances"].values()), abs=1e-3) == 1.0


def test_fit_final_uses_latest_available_row_not_a_future_one():
    """La prévision doit porter sur la toute dernière date disponible, pas sur une date
    antérieure qui aurait par erreur une cible connue."""
    bars = _synthetic_bars(800, seed=5)
    dataset = build_dataset(build_feature_frame(bars))
    result = fit_final_and_predict(dataset)
    assert result["as_of_date"] == str(bars.index[-1].date())


# --------------------------------------------------------------------------- #
# Orchestration bout-en-bout (yfinance simulé, comme pour /ohlc et /quote)
# --------------------------------------------------------------------------- #

def test_run_forecast_end_to_end(monkeypatch):
    import asyncio

    bars = _synthetic_bars(1500, seed=7)

    class _FakeTicker:
        def __init__(self, symbol):
            pass

        def history(self, period, auto_adjust, interval=None):
            return bars

    class _FakeYf:
        Ticker = _FakeTicker

    monkeypatch.setitem(__import__("sys").modules, "yfinance", _FakeYf)

    from app.forecast.pipeline import run_forecast
    result = asyncio.run(run_forecast("TEST.PA", period="5y"))

    assert result["n_bars"] == 1500
    assert result["garch_error"] is None and result["garch"] is not None
    assert result["ml_error"] is None and result["ml_forecast"] is not None
    assert result["ml_backtest"] is not None
    assert result["history_end"] == str(bars.index[-1].date())


# --------------------------------------------------------------------------- #
# Options — Put/Call Ratio, Max Pain, skew d'IV (calculs vérifiés à la main)
# --------------------------------------------------------------------------- #

def test_put_call_ratio():
    from app.forecast.options import put_call_ratio
    calls = pd.DataFrame({"strike": [95, 100], "volume": [200, 300], "openInterest": [1000, 500]})
    puts = pd.DataFrame({"strike": [95, 100], "volume": [150, 450], "openInterest": [800, 700]})
    r = put_call_ratio(calls, puts)
    assert r["call_volume"] == 500 and r["put_volume"] == 600
    assert r["pcr_volume"] == pytest.approx(600 / 500)
    assert r["call_open_interest"] == 1500 and r["put_open_interest"] == 1500
    assert r["pcr_open_interest"] == pytest.approx(1.0)


def test_put_call_ratio_handles_zero_call_volume():
    from app.forecast.options import put_call_ratio
    calls = pd.DataFrame({"strike": [100], "volume": [0], "openInterest": [0]})
    puts = pd.DataFrame({"strike": [100], "volume": [50], "openInterest": [20]})
    r = put_call_ratio(calls, puts)
    assert r["pcr_volume"] is None and r["pcr_open_interest"] is None  # pas de division par zéro silencieuse


def test_max_pain_hand_computed():
    """Carnet à 3 strikes, payout calculé à la main (voir le message de livraison) :
    strike 95 -> 325, strike 100 -> 175, strike 105 -> 200. Minimum à 100."""
    from app.forecast.options import max_pain
    calls = pd.DataFrame({"strike": [95, 100, 105], "openInterest": [10, 20, 5]})
    puts = pd.DataFrame({"strike": [95, 100, 105], "openInterest": [5, 15, 25]})
    r = max_pain(calls, puts)
    assert r["strikes"] == [95.0, 100.0, 105.0]
    assert r["total_payout_by_strike"] == pytest.approx([325.0, 175.0, 200.0])
    assert r["max_pain_strike"] == 100.0


def test_iv_skew_hand_computed():
    from app.forecast.options import iv_skew
    calls = pd.DataFrame({"strike": [90, 100, 108, 110, 120], "impliedVolatility": [0.30, 0.25, 0.22, 0.21, 0.19]})
    puts = pd.DataFrame({"strike": [80, 90, 95, 100, 110], "impliedVolatility": [0.40, 0.35, 0.32, 0.28, 0.24]})
    r = iv_skew(calls, puts, spot=100.0)
    assert r["otm_put_iv_pct"] == pytest.approx(35.0)   # strike 90 (spot*0.90), le plus proche exact
    assert r["otm_call_iv_pct"] == pytest.approx(21.0)  # strike 110 (spot*1.10), le plus proche exact
    assert r["skew_pct_points"] == pytest.approx(14.0)
    assert r["atm_call_iv_pct"] == pytest.approx(25.0)
    assert r["atm_put_iv_pct"] == pytest.approx(28.0)


def test_iv_skew_returns_none_without_spot():
    from app.forecast.options import iv_skew
    calls = pd.DataFrame({"strike": [100], "impliedVolatility": [0.2]})
    puts = pd.DataFrame({"strike": [100], "impliedVolatility": [0.25]})
    assert iv_skew(calls, puts, spot=None) is None


def test_analyze_options_end_to_end(monkeypatch):
    import asyncio

    calls = pd.DataFrame({
        "strike": [95, 100, 105], "volume": [100, 200, 50],
        "openInterest": [10, 20, 5], "impliedVolatility": [0.28, 0.25, 0.23],
    })
    puts = pd.DataFrame({
        "strike": [95, 100, 105], "volume": [80, 250, 40],
        "openInterest": [5, 15, 25], "impliedVolatility": [0.33, 0.29, 0.26],
    })

    class _Chain:
        def __init__(self): self.calls, self.puts = calls, puts

    class _FakeFastInfo:
        last_price = 100.0

    class _FakeTicker:
        options = ("2026-10-17", "2026-10-24")
        fast_info = _FakeFastInfo()

        def __init__(self, symbol): pass
        def option_chain(self, date): return _Chain()

    class _FakeYf:
        Ticker = _FakeTicker

    monkeypatch.setitem(__import__("sys").modules, "yfinance", _FakeYf)

    from app.forecast.options import analyze_options
    result = asyncio.run(analyze_options("TEST"))
    assert result["expiration_used"] == "2026-10-17"
    assert result["available_expirations"] == ["2026-10-17", "2026-10-24"]
    assert result["spot_price"] == 100.0
    assert result["max_pain"]["max_pain_strike"] == 100.0
    assert result["pcr"]["pcr_volume"] == pytest.approx(370 / 350)


def test_analyze_options_no_expirations_raises(monkeypatch):
    import asyncio
    from app.forecast.options import OptionChainUnavailable, analyze_options

    class _FakeTicker:
        options = ()
        def __init__(self, symbol): pass

    class _FakeYf:
        Ticker = _FakeTicker

    monkeypatch.setitem(__import__("sys").modules, "yfinance", _FakeYf)
    with pytest.raises(OptionChainUnavailable):
        asyncio.run(analyze_options("NO_OPTIONS"))


# --------------------------------------------------------------------------- #
# Régimes de marché (HMM)
# --------------------------------------------------------------------------- #

def _two_regime_returns(n_per_regime=400, seed=0):
    """Rendements log synthétiques : une longue phase haussière calme, puis une phase baissière
    plus volatile — deux régimes nettement séparés, pour vérifier que le HMM les distingue."""
    rng = np.random.default_rng(seed)
    bull = rng.normal(0.003, 0.008, n_per_regime)
    bear = rng.normal(-0.004, 0.020, n_per_regime)
    idx = pd.bdate_range("2018-01-01", periods=2 * n_per_regime)
    return pd.Series(np.concatenate([bull, bear]), index=idx)


def test_fit_regimes_identifies_bull_and_bear():
    from app.forecast.regime import fit_regimes
    returns = _two_regime_returns()
    result = fit_regimes(returns, n_states=2)
    assert result["current_regime"] == "Baissier"  # la série se termine sur la phase baissière
    summary = result["state_summary"]
    assert summary["Haussier"]["mean_daily_return_pct"] > summary["Baissier"]["mean_daily_return_pct"]
    # la grande majorité des 40 derniers jours (tous dans la phase baissière) doivent être étiquetés comme tels
    recent_labels = [p["regime"] for p in result["recent_regime_sequence"]]
    assert recent_labels.count("Baissier") >= len(recent_labels) * 0.7


def test_fit_regimes_rejects_short_history():
    from app.forecast.regime import fit_regimes
    returns = pd.Series(np.random.default_rng(1).normal(0, 0.01, 100))
    with pytest.raises(ValueError):
        fit_regimes(returns, n_states=2)


def test_fit_regimes_rejects_invalid_n_states():
    from app.forecast.regime import fit_regimes
    returns = _two_regime_returns()
    with pytest.raises(ValueError):
        fit_regimes(returns, n_states=5)


def test_fit_regimes_three_states_structure():
    from app.forecast.regime import fit_regimes
    returns = _two_regime_returns(n_per_regime=300, seed=2)
    result = fit_regimes(returns, n_states=3)
    assert set(result["state_summary"]) == {"Haussier", "Baissier", "Range / haute volatilité"}
    assert len(result["transition_matrix"]) == 3 and len(result["transition_matrix"][0]) == 3
    for row in result["transition_matrix"]:
        assert sum(row) == pytest.approx(1.0, abs=1e-6)  # chaque ligne d'une matrice de transition somme à 1


# --------------------------------------------------------------------------- #
# run_forecast inclut maintenant options + régime
# --------------------------------------------------------------------------- #

def test_run_forecast_includes_options_and_regime(monkeypatch):
    import asyncio

    bars = _synthetic_bars(1500, seed=9)
    calls = pd.DataFrame({"strike": [95, 100, 105], "volume": [10, 20, 5], "openInterest": [10, 20, 5], "impliedVolatility": [0.3, 0.25, 0.22]})
    puts = pd.DataFrame({"strike": [95, 100, 105], "volume": [8, 25, 4], "openInterest": [5, 15, 25], "impliedVolatility": [0.33, 0.29, 0.26]})

    class _Chain:
        def __init__(self): self.calls, self.puts = calls, puts

    class _FakeFastInfo:
        last_price = float(bars["Close"].iloc[-1])

    class _FakeTicker:
        options = ("2026-10-17",)
        fast_info = _FakeFastInfo()

        def __init__(self, symbol): pass
        def history(self, period, auto_adjust, interval=None): return bars
        def option_chain(self, date): return _Chain()

    class _FakeYf:
        Ticker = _FakeTicker

    monkeypatch.setitem(__import__("sys").modules, "yfinance", _FakeYf)

    from app.forecast.pipeline import run_forecast
    result = asyncio.run(run_forecast("TEST.PA", period="5y"))

    assert result["regime_error"] is None and result["regime"] is not None
    assert result["regime"]["current_regime"] in ("Haussier", "Baissier", "Range / haute volatilité")
    assert result["options_error"] is None and result["options"] is not None
    assert result["options"]["max_pain"]["max_pain_strike"] == 100.0


# --------------------------------------------------------------------------- #
# Contexte macro (horizon 1 mois) — le test le plus important vérifie que la
# discipline anti-look-ahead de resample.py est bien respectée ici aussi.
# --------------------------------------------------------------------------- #

class _FakeStore:
    """Store minimal pour les tests : `read_panel` renvoie exactement ce que
    `Store.read_panel` renvoie en réalité (mêmes colonnes), à partir de lignes fournies à la
    main au lieu de DuckDB."""
    def __init__(self, rows: list[dict]):
        self._df = pd.DataFrame(rows, columns=["timestamp", "country", "indicator_code", "value", "frequency", "unit", "source", "release_date", "ingested_at"])
        for c in ("timestamp", "release_date", "ingested_at"):
            self._df[c] = pd.to_datetime(self._df[c])

    def read_panel(self, codes):
        return self._df[self._df["indicator_code"].isin(codes)].copy()


def _macro_row(code, timestamp, release_date, value, country="USA"):
    return {"timestamp": timestamp, "country": country, "indicator_code": code, "value": value,
            "frequency": "M", "unit": "%", "source": "test", "release_date": release_date, "ingested_at": release_date}


def test_resolve_codes_includes_declared_fallback():
    from app.forecast.macro_context import _resolve_codes
    resolved = _resolve_codes(["IN_REPO_RATE"])
    assert "IN_REPO_RATE" in resolved and "IN_REPO_RATE_WB" in resolved


def test_macro_codes_for_country_known_and_unknown():
    from app.forecast.macro_context import macro_codes_for_country
    assert "US_FEDFUNDS" in macro_codes_for_country("USA")
    assert macro_codes_for_country("GBR") == []  # aucune série macro GBR dans ce projet


def test_build_macro_features_empty_for_unmapped_country():
    from app.forecast.macro_context import build_macro_features
    dates = pd.bdate_range("2024-01-01", periods=10)
    macro, used = build_macro_features(_FakeStore([]), "GBR", dates)
    assert macro.empty and used == []


def test_build_macro_features_respects_release_date_no_lookahead():
    """LE test critique : une valeur publiée le 2024-02-15 ne doit apparaître qu'à partir de
    cette date dans le panneau — jamais avant, même si elle décrit une période antérieure."""
    from app.forecast.macro_context import build_macro_features
    rows = [
        _macro_row("US_FEDFUNDS", "2023-12-01", "2023-12-05", 5.25),
        _macro_row("US_FEDFUNDS", "2024-01-01", "2024-02-15", 5.50),  # publiée en retard, exprès
    ]
    dates = pd.bdate_range("2024-01-01", "2024-03-01")
    macro, used = build_macro_features(_FakeStore(rows), "USA", dates)
    assert "US_FEDFUNDS" in used
    col = "macro_US_FEDFUNDS"
    before = macro.loc[macro.index < "2024-02-15", col]
    after = macro.loc[macro.index >= "2024-02-15", col]
    assert (before == 5.25).all(), "une valeur publiée le 15/02 apparaît avant cette date : biais de look-ahead"
    assert (after == 5.50).all()


def test_build_macro_features_merges_fallback_when_primary_empty():
    """IN_REPO_RATE n'a jamais de ligne (fichier manuel jamais déposé, cas réel de ce projet) ;
    seul le repli IN_REPO_RATE_WB a des données — la colonne fusionnée doit les reprendre."""
    from app.forecast.macro_context import build_macro_features
    rows = [_macro_row("IN_REPO_RATE_WB", "2023-01-01", "2023-06-01", 6.5, country="IND")]
    dates = pd.bdate_range("2023-06-01", "2023-12-01")
    macro, used = build_macro_features(_FakeStore(rows), "IND", dates)
    assert "IN_REPO_RATE" in used  # listé sous son propre nom même si la donnée vient du repli
    assert (macro["macro_IN_REPO_RATE"].dropna() == 6.5).all()


def test_build_macro_features_empty_when_store_has_no_matching_rows():
    from app.forecast.macro_context import build_macro_features
    dates = pd.bdate_range("2024-01-01", periods=10)
    macro, used = build_macro_features(_FakeStore([]), "USA", dates)
    assert macro.empty and used == []


def test_build_macro_features_adds_change_column():
    from app.forecast.macro_context import build_macro_features, MACRO_CHANGE_WINDOW_DAYS
    rows = [
        _macro_row("US_FEDFUNDS", "2023-06-01", "2023-06-05", 5.00),
        _macro_row("US_FEDFUNDS", "2023-10-01", "2023-10-05", 5.50),
    ]
    dates = pd.bdate_range("2023-06-05", "2023-12-01")
    macro, _ = build_macro_features(_FakeStore(rows), "USA", dates)
    assert "macro_US_FEDFUNDS_chg_63d" in macro.columns
    # suffisamment loin dans la fenêtre pour que la variation soit renseignée et non nulle
    late = macro["macro_US_FEDFUNDS_chg_63d"].dropna()
    assert not late.empty


# --------------------------------------------------------------------------- #
# run_forecast avec horizon="1m" : inclut le contexte macro
# --------------------------------------------------------------------------- #

def test_run_forecast_month_horizon_includes_macro(monkeypatch):
    import asyncio
    from app.forecast.pipeline import run_forecast

    bars = _synthetic_bars(1500, seed=13)

    class _FakeTicker:
        def __init__(self, symbol): pass
        def history(self, period, auto_adjust, interval=None): return bars
        options = ()  # pas d'options cotées pour ce test : on isole le contexte macro

    class _FakeYf:
        Ticker = _FakeTicker
    monkeypatch.setitem(__import__("sys").modules, "yfinance", _FakeYf)

    macro_rows = [_macro_row("US_FEDFUNDS", d.strftime("%Y-%m-%d"), d.strftime("%Y-%m-%d"), 5.0 + i * 0.01)
                  for i, d in enumerate(pd.bdate_range("2018-01-01", periods=1500))]
    store = _FakeStore(macro_rows)

    result = asyncio.run(run_forecast("TEST.PA", period="5y", horizon="1m", country="USA", store=store))

    assert result["ml_error"] is None
    assert result["ml_forecast"]["horizon_days"] == 21
    assert any(k.startswith("macro_US_FEDFUNDS") for k in result["ml_forecast"]["feature_importances"])
    assert "US_FEDFUNDS" in result["macro_codes_used"]


def test_run_forecast_week_horizon_has_no_macro_by_default(monkeypatch):
    """horizon="1w" (comportement par défaut, déjà en production) ne doit RIEN changer : pas de
    contexte macro, pas de nouveau paramètre requis — non-régression du Volet A d'origine."""
    import asyncio
    from app.forecast.pipeline import run_forecast

    bars = _synthetic_bars(1500, seed=14)

    class _FakeTicker:
        def __init__(self, symbol): pass
        def history(self, period, auto_adjust, interval=None): return bars
        options = ()

    class _FakeYf:
        Ticker = _FakeTicker
    monkeypatch.setitem(__import__("sys").modules, "yfinance", _FakeYf)

    result = asyncio.run(run_forecast("TEST.PA", period="5y"))
    assert result["ml_forecast"]["horizon_days"] == 5
    assert not any(k.startswith("macro_") for k in result["ml_forecast"]["feature_importances"])
    assert result.get("macro_codes_used", []) == []


# --------------------------------------------------------------------------- #
# run_forecast avec Kronos (modèle de fondation auto-hébergé, optionnel)
# --------------------------------------------------------------------------- #

def test_run_forecast_without_kronos_is_unaffected(monkeypatch):
    """use_kronos=False (par défaut) : non-régression — aucun appel réseau supplémentaire,
    `kronos`/`kronos_error` restent None."""
    import asyncio
    from app.forecast.pipeline import run_forecast

    bars = _synthetic_bars(1500, seed=15)

    class _FakeTicker:
        def __init__(self, symbol): pass
        def history(self, period, auto_adjust, interval=None): return bars
        options = ()

    class _FakeYf:
        Ticker = _FakeTicker
    monkeypatch.setitem(__import__("sys").modules, "yfinance", _FakeYf)

    result = asyncio.run(run_forecast("TEST.PA", period="5y"))
    assert result["kronos"] is None
    assert result["kronos_error"] is None


def test_run_forecast_with_ohlcv_cache_skips_second_network_call(monkeypatch, tmp_path):
    """Quand `ohlcv_cache` est fourni (comme le fait désormais api.py), l'historique est servi
    par le cache local : un second appel pour le même titre, le même jour, ne doit déclencher
    AUCUN nouvel appel à Yahoo Finance — c'est le même gain que pour `/ohlc`, appliqué ici au
    pipeline de prévision."""
    import asyncio

    from app.forecast.pipeline import run_forecast
    from app.ohlcv_cache import OhlcvCache

    n = 1500
    rng = np.random.default_rng(31)
    log_returns = rng.normal(0.0002, 0.015, n)
    close = 100 * np.exp(np.cumsum(log_returns))
    high = close * (1 + np.abs(rng.normal(0, 0.003, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.003, n)))
    volume = rng.integers(1_000_000, 5_000_000, n).astype(float)
    # Barres se terminant AUJOURD'HUI (pas 2018) : get_daily_bars_frame tronque la fenêtre
    # "5y" par rapport à la date du jour, donc l'historique synthétique doit la couvrir.
    idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    bars = pd.DataFrame({"Open": close, "High": high, "Low": low, "Close": close, "Volume": volume}, index=idx)

    calls = []

    class _FakeTicker:
        def __init__(self, symbol):
            pass

        def history(self, period=None, auto_adjust=True, interval=None, start=None):
            calls.append({"period": period, "start": start})
            return bars

        options = ()

    class _FakeYf:
        Ticker = _FakeTicker

    monkeypatch.setitem(__import__("sys").modules, "yfinance", _FakeYf)

    cache = OhlcvCache(tmp_path)
    try:
        first = asyncio.run(run_forecast("TEST.PA", period="5y", ohlcv_cache=cache))
        second = asyncio.run(run_forecast("TEST.PA", period="5y", ohlcv_cache=cache))
    finally:
        cache.close()

    assert len(calls) == 1  # le cache a servi le second appel sans retoucher le réseau
    assert first["n_bars"] == second["n_bars"]
    assert first["garch_error"] is None
    assert first["ml_error"] is None


def test_run_forecast_with_kronos_enabled(monkeypatch, tmp_path):
    """use_kronos=True + settings.kronos configuré : la prévision Kronos (mockée, aucun réseau
    réel) atterrit dans le résultat sans perturber le reste du calcul."""
    import asyncio

    import httpx
    import respx

    from app.config import load_settings
    from app.forecast.pipeline import run_forecast

    bars = _synthetic_bars(1500, seed=16)

    class _FakeTicker:
        def __init__(self, symbol): pass
        def history(self, period, auto_adjust, interval=None): return bars
        options = ()

    class _FakeYf:
        Ticker = _FakeTicker
    monkeypatch.setitem(__import__("sys").modules, "yfinance", _FakeYf)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("KRONOS_BASE_URL", "http://127.0.0.1:3021")
    settings = load_settings()

    with respx.mock(assert_all_called=True) as mock:
        mock.post("http://127.0.0.1:3021/api/forecast").mock(
            return_value=httpx.Response(200, json={
                "timestamps": ["2024-01-01T00:00:00"],
                "predictions": [{"open": 101.0, "high": 102.0, "low": 100.0, "close": 101.5}],
                "lookback": 400, "pred_len": 1, "last_known_close": 100.0,
            })
        )
        result = asyncio.run(run_forecast("TEST.PA", period="5y", use_kronos=True, settings=settings))

    assert result["kronos_error"] is None
    assert result["kronos"]["predictions"][0]["close"] == 101.5
    # le reste du calcul (GARCH, ML) n'est pas affecté par l'ajout de Kronos
    assert result["garch_error"] is None and result["ml_error"] is None


def test_run_forecast_with_kronos_enabled_but_unreachable(monkeypatch, tmp_path):
    """Kronos injoignable : le reste de la prévision (GARCH, ML, régime, options) doit quand
    même être renvoyé — une panne du service Kronos ne doit jamais faire échouer tout l'onglet
    Prévision."""
    import asyncio

    import httpx
    import respx

    from app.config import load_settings
    from app.forecast.pipeline import run_forecast

    bars = _synthetic_bars(1500, seed=17)

    class _FakeTicker:
        def __init__(self, symbol): pass
        def history(self, period, auto_adjust, interval=None): return bars
        options = ()

    class _FakeYf:
        Ticker = _FakeTicker
    monkeypatch.setitem(__import__("sys").modules, "yfinance", _FakeYf)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("KRONOS_BASE_URL", "http://127.0.0.1:3021")
    settings = load_settings()

    with respx.mock(assert_all_called=True) as mock:
        mock.post("http://127.0.0.1:3021/api/forecast").mock(side_effect=httpx.ConnectError("refused"))
        result = asyncio.run(run_forecast("TEST.PA", period="5y", use_kronos=True, settings=settings))

    assert result["kronos"] is None
    assert "ConnectError" in result["kronos_error"]
    assert result["garch_error"] is None and result["ml_error"] is None
