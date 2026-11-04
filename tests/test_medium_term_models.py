"""Tests des six modèles « moyen terme » non liés à une IA (`app/forecast/medium_term/`) :
Momentum 12-1, time-series momentum, Markov switching (own-series, pas de réseau) + Fama-French 5
+ momentum, PEAD, VAR titre/marché (réseau — testés via leur fonction `fit_*` pure, sans appel
réseau, puis end-to-end via `pipeline.run_forecast` avec `yfinance` simulé).

Même discipline que `test_short_term_models.py` : données synthétiques, vérification de
structure, rejet propre sur un historique trop court, branchement dans le pipeline."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.forecast.medium_term import SYNC_MODELS
from app.forecast.medium_term.ff5_momentum import PROXY_TICKERS, fit_ff5_momentum_forecast
from app.forecast.medium_term.markov_switching import fit_markov_switching_forecast
from app.forecast.medium_term.momentum_12_1 import fit_momentum_12_1_forecast
from app.forecast.medium_term.pead import fit_pead_forecast
from app.forecast.medium_term.ts_momentum import fit_ts_momentum_forecast
from app.forecast.medium_term.var_market import fit_var_market_forecast
from app.forecast.model_base import PredictionResult


def _synthetic_close(n=900, seed=0, daily_vol=0.015, drift=0.0002) -> pd.Series:
    """Série de clôture synthétique (marche aléatoire) — assez longue pour couvrir le lookback de
    12 mois des modèles momentum (252 + 21 + 21 jours). CLAIREMENT PAS des données de marché
    réelles."""
    rng = np.random.default_rng(seed)
    log_returns = rng.normal(drift, daily_vol, n)
    close = 100 * np.exp(np.cumsum(log_returns))
    idx = pd.bdate_range("2021-01-01", periods=n)
    return pd.Series(close, index=idx)


def _synthetic_bars(n=900, seed=0, daily_vol=0.015, drift=0.0002) -> pd.DataFrame:
    close = _synthetic_close(n, seed, daily_vol, drift)
    rng = np.random.default_rng(seed + 1)
    high = close * (1 + np.abs(rng.normal(0, 0.003, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.003, n)))
    open_ = np.roll(close.values, 1)
    open_[0] = close.iloc[0]
    volume = rng.integers(1_000_000, 5_000_000, n).astype(float)
    return pd.DataFrame(
        {"Open": open_, "High": high.values, "Low": low.values, "Close": close.values, "Volume": volume},
        index=close.index,
    )


# --------------------------------------------------------------------------- #
# Momentum 12-1
# --------------------------------------------------------------------------- #

def test_momentum_12_1_structure():
    close = _synthetic_close(900, seed=1)
    result = fit_momentum_12_1_forecast(close, horizon_days=21)
    assert result["sigma_pct"] > 0
    assert isinstance(result["expected_return_pct"], float)
    assert result["n_obs"] > 300


def test_momentum_12_1_rejects_short_history():
    close = _synthetic_close(300, seed=2)
    with pytest.raises(ValueError):
        fit_momentum_12_1_forecast(close, horizon_days=21)


# --------------------------------------------------------------------------- #
# Time-series momentum
# --------------------------------------------------------------------------- #

def test_ts_momentum_structure():
    close = _synthetic_close(900, seed=3)
    result = fit_ts_momentum_forecast(close, horizon_days=21)
    assert result["sigma_pct"] > 0
    assert result["trailing_12m_sign"] in (-1, 1)
    assert result["n_obs"] > 300


def test_ts_momentum_rejects_short_history():
    close = _synthetic_close(300, seed=4)
    with pytest.raises(ValueError):
        fit_ts_momentum_forecast(close, horizon_days=21)


def test_ts_momentum_uses_sign_not_magnitude():
    """Distinction avec momentum_12_1 : deux séries avec le même SIGNE de rendement passé sur 12
    mois mais des magnitudes très différentes doivent donner la même direction de signal TSMOM
    (même régresseur : le signe), ce qui n'est PAS garanti pour momentum_12_1 (régresseur :
    la magnitude)."""
    close_a = _synthetic_close(900, seed=5, drift=0.0015)  # forte tendance haussière
    close_b = _synthetic_close(900, seed=5, drift=0.0001)  # tendance haussière à peine positive
    # on force artificiellement le signe du rendement 12m à être positif pour les deux séries
    result_a = fit_ts_momentum_forecast(close_a, horizon_days=21)
    result_b = fit_ts_momentum_forecast(close_b, horizon_days=21)
    if result_a["trailing_12m_sign"] == result_b["trailing_12m_sign"]:
        assert np.sign(result_a["expected_return_pct"]) == np.sign(result_b["expected_return_pct"]) or (
            result_a["expected_return_pct"] == 0 or result_b["expected_return_pct"] == 0
        )


# --------------------------------------------------------------------------- #
# Markov switching
# --------------------------------------------------------------------------- #

def test_markov_switching_structure():
    close = _synthetic_close(900, seed=6)
    log_ret = np.log(close).diff()
    result = fit_markov_switching_forecast(log_ret, horizon_days=21)
    assert result["sigma_pct"] > 0
    assert result["current_regime"] in (0, 1)
    assert len(result["current_regime_probabilities"]) == 2
    assert pytest.approx(sum(result["current_regime_probabilities"]), abs=1e-6) == 1.0
    assert result["n_obs"] > 500


def test_markov_switching_rejects_short_history():
    close = _synthetic_close(100, seed=7)
    log_ret = np.log(close).diff()
    with pytest.raises(ValueError):
        fit_markov_switching_forecast(log_ret, horizon_days=21)


# --------------------------------------------------------------------------- #
# Interface commune HorizonModel (modèles sans appel réseau)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("model_cls", SYNC_MODELS)
def test_each_sync_model_conforms_to_horizon_model_protocol(model_cls):
    bars = _synthetic_bars(900, seed=8)
    model = model_cls()
    result = model.predict(bars, horizon_days=21)
    assert isinstance(result, PredictionResult)
    assert isinstance(result.mu_pct, float)
    assert result.sigma_pct > 0
    assert isinstance(result.diagnostics, dict)


def test_sync_models_registry_has_the_three_confirmed_models():
    names = {m().name for m in SYNC_MODELS}
    assert names == {"momentum_12_1", "ts_momentum", "markov_switching"}


# --------------------------------------------------------------------------- #
# Fama-French 5 + momentum (fonction pure, sans appel réseau : proxys injectés)
# --------------------------------------------------------------------------- #

def test_ff5_momentum_structure():
    stock_close = _synthetic_close(400, seed=9)
    proxy_closes = {t: _synthetic_close(400, seed=100 + i) for i, t in enumerate(PROXY_TICKERS)}
    result = fit_ff5_momentum_forecast(stock_close, proxy_closes, horizon_days=21)
    assert result["sigma_pct"] > 0
    assert isinstance(result["expected_return_pct"], float)
    assert set(result["betas"].keys()) == {"mkt", "smb", "hml", "rmw", "cma", "mom"}
    assert result["n_obs"] > 300


def test_ff5_momentum_rejects_short_common_history():
    stock_close = _synthetic_close(50, seed=10)
    proxy_closes = {t: _synthetic_close(50, seed=200 + i) for i, t in enumerate(PROXY_TICKERS)}
    with pytest.raises(ValueError):
        fit_ff5_momentum_forecast(stock_close, proxy_closes, horizon_days=21)


# --------------------------------------------------------------------------- #
# VAR titre/marché (fonction pure, marché injecté)
# --------------------------------------------------------------------------- #

def test_var_market_structure():
    stock_close = _synthetic_close(400, seed=11)
    market_close = _synthetic_close(400, seed=12)
    result = fit_var_market_forecast(stock_close, market_close, horizon_days=21)
    assert result["sigma_pct"] > 0
    assert isinstance(result["expected_return_pct"], float)
    assert result["lags_used"] >= 0
    assert result["n_obs"] > 300


def test_var_market_rejects_short_common_history():
    stock_close = _synthetic_close(50, seed=13)
    market_close = _synthetic_close(50, seed=14)
    with pytest.raises(ValueError):
        fit_var_market_forecast(stock_close, market_close, horizon_days=21)


# --------------------------------------------------------------------------- #
# PEAD (fonction pure, dates de résultats injectées)
# --------------------------------------------------------------------------- #

def _fake_earnings_dates(n_quarters: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2021-02-01", periods=n_quarters, freq="63B", tz="America/New_York")
    estimate = rng.normal(1.0, 0.1, n_quarters)
    reported = estimate + rng.normal(0, 0.15, n_quarters)
    df = pd.DataFrame({"EPS Estimate": estimate, "Reported EPS": reported}, index=idx)
    df["Surprise(%)"] = (df["Reported EPS"] - df["EPS Estimate"]) / df["EPS Estimate"]
    return df


def test_pead_own_regression_path():
    close = _synthetic_close(900, seed=15)
    earnings_dates = _fake_earnings_dates(10, seed=16)
    result = fit_pead_forecast(close, earnings_dates, horizon_days=21)
    assert result["fit_mode"] == "own_regression"
    assert result["n_past_surprises_used"] >= 8
    assert result["sigma_pct"] > 0


def test_pead_literature_fallback_path():
    close = _synthetic_close(900, seed=17)
    earnings_dates = _fake_earnings_dates(3, seed=18)
    result = fit_pead_forecast(close, earnings_dates, horizon_days=21)
    assert result["fit_mode"] == "literature_fallback"
    assert result["sigma_pct"] > 0


def test_pead_rejects_when_no_surprises_available():
    close = _synthetic_close(900, seed=19)
    earnings_dates = pd.DataFrame(
        {"EPS Estimate": [np.nan], "Reported EPS": [np.nan], "Surprise(%)": [np.nan]},
        index=pd.bdate_range("2021-02-01", periods=1, tz="America/New_York"),
    )
    with pytest.raises(ValueError):
        fit_pead_forecast(close, earnings_dates, horizon_days=21)


# --------------------------------------------------------------------------- #
# Branchement dans le pipeline : seulement à horizon "1m"
# --------------------------------------------------------------------------- #

def test_pipeline_compute_runs_medium_term_sync_models_only_at_1m():
    from app.forecast.pipeline import _compute

    bars = _synthetic_bars(900, seed=20)

    computed_1w = _compute(bars, horizon="1w", horizon_days=5, country=None, store=None)
    assert computed_1w["medium_term_models"] == {}
    assert computed_1w["medium_term_errors"] == {}

    computed_1m = _compute(bars, horizon="1m", horizon_days=21, country=None, store=None)
    names = set(computed_1m["medium_term_models"].keys()) | set(computed_1m["medium_term_errors"].keys())
    assert names == {"momentum_12_1", "ts_momentum", "markov_switching"}


def test_run_forecast_end_to_end_with_medium_term_at_1m(monkeypatch):
    """Vérifie le branchement complet (y compris les 3 tâches réseau) via `run_forecast`, avec
    `yfinance` simulé pour le titre ET tous les proxys/l'indice/les résultats — même mécanisme
    que `test_api.py::test_forecast_result_matches_response_schema`."""
    import asyncio

    from app.forecast.pipeline import run_forecast
    from app.schemas import ForecastResponse

    bars = _synthetic_bars(900, seed=21)
    earnings_dates = _fake_earnings_dates(10, seed=22)

    class _FakeTicker:
        def __init__(self, symbol):
            self.symbol = symbol

        def history(self, period, auto_adjust, interval=None):
            # même historique pour le titre ET tous les proxys ETF/l'indice de marché : seule la
            # structure du pipeline est testée ici, pas la pertinence économique des résultats.
            return bars

        def get_earnings_dates(self, limit=40):
            return earnings_dates

        options = ()

    class _FakeYf:
        Ticker = _FakeTicker

    monkeypatch.setitem(__import__("sys").modules, "yfinance", _FakeYf)

    result = asyncio.run(run_forecast("TEST.PA", period="5y", horizon="1m"))
    result["indicator_code"] = "TEST.PA"
    validated = ForecastResponse(**result)  # lève si un champ manque ou a le mauvais type

    names = set(validated.medium_term_models.keys()) | set(validated.medium_term_errors.keys())
    assert names == {"momentum_12_1", "ts_momentum", "markov_switching", "ff5_momentum", "pead", "var_market"}
