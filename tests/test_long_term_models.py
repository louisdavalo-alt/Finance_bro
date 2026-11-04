"""Tests des six modèles « long terme » non liés à une IA (`app/forecast/long_term/`) : CAPE de
Shiller, régression dividend yield, Gordon/DDM, prime de risque implicite, facteurs
value/profitabilité, cointégration/VECM — tous testés via leur fonction `fit_*` pure (sans appel
réseau, données injectées), plus le branchement complet dans `pipeline.run_forecast`.

Même discipline que `test_short_term_models.py`/`test_medium_term_models.py` : données
synthétiques, vérification de structure, rejet propre sur données insuffisantes."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.forecast.long_term.cape import fit_cape_forecast
from app.forecast.long_term.cointegration_vecm import fit_cointegration_vecm_forecast
from app.forecast.long_term.dividend_yield import fit_dividend_yield_forecast
from app.forecast.long_term.gordon_ddm import fit_gordon_ddm_forecast
from app.forecast.long_term.implied_erp import fit_implied_erp_forecast
from app.forecast.long_term.value_profitability import PROXY_TICKERS, fit_value_profitability_forecast


def _synthetic_close(n=900, seed=0, daily_vol=0.015, drift=0.0002) -> pd.Series:
    rng = np.random.default_rng(seed)
    log_returns = rng.normal(drift, daily_vol, n)
    close = 100 * np.exp(np.cumsum(log_returns))
    idx = pd.bdate_range("2021-01-01", periods=n)
    return pd.Series(close, index=idx)


def _fake_dividends(n_payments=16, seed=1) -> pd.Series:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2021-02-01", periods=n_payments, freq="63B", tz="America/New_York")
    return pd.Series(rng.uniform(0.3, 0.6, n_payments), index=idx)


# --------------------------------------------------------------------------- #
# CAPE (proxy P/E trailing)
# --------------------------------------------------------------------------- #

def test_cape_structure():
    result = fit_cape_forecast(25.0, horizon_days=21)
    assert result["sigma_pct"] > 0
    assert result["earnings_yield_pct"] == pytest.approx(4.0)
    assert isinstance(result["expected_return_pct"], float)


@pytest.mark.parametrize("pe", [None, 0, -5])
def test_cape_rejects_missing_or_invalid_pe(pe):
    with pytest.raises(ValueError):
        fit_cape_forecast(pe, horizon_days=21)


# --------------------------------------------------------------------------- #
# Régression dividend yield
# --------------------------------------------------------------------------- #

def test_dividend_yield_structure():
    close = _synthetic_close(900, seed=2)
    dividends = _fake_dividends(16, seed=3)
    result = fit_dividend_yield_forecast(close, dividends, horizon_days=21)
    assert result["sigma_pct"] > 0
    assert result["current_dividend_yield_pct"] > 0
    assert result["n_obs"] > 300


def test_dividend_yield_rejects_no_dividends():
    close = _synthetic_close(900, seed=4)
    with pytest.raises(ValueError):
        fit_dividend_yield_forecast(close, pd.Series(dtype=float), horizon_days=21)
    with pytest.raises(ValueError):
        fit_dividend_yield_forecast(close, None, horizon_days=21)


def test_dividend_yield_rejects_short_common_history():
    close = _synthetic_close(200, seed=5)
    dividends = _fake_dividends(3, seed=6)
    with pytest.raises(ValueError):
        fit_dividend_yield_forecast(close, dividends, horizon_days=21)


# --------------------------------------------------------------------------- #
# Gordon / DDM
# --------------------------------------------------------------------------- #

def test_gordon_ddm_structure():
    close = _synthetic_close(900, seed=7)
    dividends = _fake_dividends(16, seed=8)
    result = fit_gordon_ddm_forecast(close, dividends, horizon_days=21)
    assert result["sigma_pct"] > 0
    assert result["dividend_yield_pct"] > 0
    assert result["n_years_dividend_history"] >= 3


def test_gordon_ddm_rejects_no_dividends():
    close = _synthetic_close(900, seed=9)
    with pytest.raises(ValueError):
        fit_gordon_ddm_forecast(close, pd.Series(dtype=float), horizon_days=21)


def test_gordon_ddm_rejects_too_few_dividend_years():
    close = _synthetic_close(900, seed=10)
    dividends = _fake_dividends(2, seed=11)  # trop peu d'années distinctes
    with pytest.raises(ValueError):
        fit_gordon_ddm_forecast(close, dividends, horizon_days=21)


# --------------------------------------------------------------------------- #
# Prime de risque implicite (CAPM)
# --------------------------------------------------------------------------- #

def test_implied_erp_structure():
    stock_close = _synthetic_close(900, seed=12)
    market_close = _synthetic_close(900, seed=13)
    result = fit_implied_erp_forecast(stock_close, market_close, 22.0, 4.3, horizon_days=21)
    assert result["sigma_pct"] > 0
    assert result["risk_free_pct"] == 4.3
    assert isinstance(result["beta"], float)
    assert result["n_obs"] > 300


def test_implied_erp_rejects_missing_market_pe():
    stock_close = _synthetic_close(900, seed=14)
    market_close = _synthetic_close(900, seed=15)
    with pytest.raises(ValueError):
        fit_implied_erp_forecast(stock_close, market_close, None, 4.3, horizon_days=21)


def test_implied_erp_rejects_short_common_history():
    stock_close = _synthetic_close(100, seed=16)
    market_close = _synthetic_close(100, seed=17)
    with pytest.raises(ValueError):
        fit_implied_erp_forecast(stock_close, market_close, 22.0, 4.3, horizon_days=21)


# --------------------------------------------------------------------------- #
# Facteurs value/profitabilité (ETF proxys injectés)
# --------------------------------------------------------------------------- #

def test_value_profitability_structure():
    stock_close = _synthetic_close(900, seed=18)
    proxy_closes = {t: _synthetic_close(900, seed=200 + i) for i, t in enumerate(PROXY_TICKERS)}
    result = fit_value_profitability_forecast(stock_close, proxy_closes, horizon_days=21)
    assert result["sigma_pct"] > 0
    assert set(result["betas"].keys()) == {"value", "profitability"}
    assert result["n_obs"] > 300


def test_value_profitability_rejects_short_common_history():
    stock_close = _synthetic_close(100, seed=19)
    proxy_closes = {t: _synthetic_close(100, seed=300 + i) for i, t in enumerate(PROXY_TICKERS)}
    with pytest.raises(ValueError):
        fit_value_profitability_forecast(stock_close, proxy_closes, horizon_days=21)


# --------------------------------------------------------------------------- #
# Cointégration / VECM
# --------------------------------------------------------------------------- #

def test_cointegration_vecm_rejects_when_not_cointegrated():
    """Deux marches aléatoires indépendantes ne sont, presque sûrement, pas cointégrées : le
    modèle doit échouer explicitement plutôt que de forcer un VECM sans fondement."""
    stock_close = _synthetic_close(900, seed=20)
    market_close = _synthetic_close(900, seed=21)
    with pytest.raises(ValueError, match="cointégration"):
        fit_cointegration_vecm_forecast(stock_close, market_close, horizon_days=21)


def test_cointegration_vecm_succeeds_when_cointegrated_by_construction():
    """Construit une série dont le log-prix est une combinaison linéaire du log du marché plus
    un bruit stationnaire : par construction, cointégrée avec le marché."""
    market_close = _synthetic_close(900, seed=22)
    log_market = np.log(market_close)
    noise = pd.Series(np.random.default_rng(23).normal(0, 0.02, len(market_close)), index=market_close.index)
    stock_close = np.exp(1.05 * log_market + noise)

    result = fit_cointegration_vecm_forecast(stock_close, market_close, horizon_days=21)
    assert result["coint_pvalue"] < 0.05
    assert result["coint_rank"] >= 1
    assert result["sigma_pct"] > 0
    assert result["n_obs"] > 300


def test_cointegration_vecm_rejects_short_common_history():
    stock_close = _synthetic_close(100, seed=24)
    market_close = _synthetic_close(100, seed=25)
    with pytest.raises(ValueError):
        fit_cointegration_vecm_forecast(stock_close, market_close, horizon_days=21)


# --------------------------------------------------------------------------- #
# Branchement dans le pipeline : seulement à horizon "1m", toujours en tâches réseau
# --------------------------------------------------------------------------- #

def test_compute_never_populates_long_term_models_directly():
    """`_compute` (thread CPU) ne doit jamais remplir `long_term_models` : les 6 modèles sont
    tous des tâches réseau ajoutées par `run_forecast`, pas par `_compute` (voir docstring du
    module `long_term/__init__.py`)."""
    from app.forecast.pipeline import _compute

    rng = np.random.default_rng(26)
    n = 900
    close = 100 * np.exp(np.cumsum(rng.normal(0.0002, 0.015, n)))
    bars = pd.DataFrame(
        {"Open": close, "High": close * 1.01, "Low": close * 0.99, "Close": close, "Volume": 1_000_000.0},
        index=pd.bdate_range("2021-01-01", periods=n),
    )
    computed_1w = _compute(bars, horizon="1w", horizon_days=5, country=None, store=None)
    computed_1m = _compute(bars, horizon="1m", horizon_days=21, country=None, store=None)
    assert computed_1w["long_term_models"] == {} and computed_1w["long_term_errors"] == {}
    assert computed_1m["long_term_models"] == {} and computed_1m["long_term_errors"] == {}


def test_run_forecast_end_to_end_with_long_term_at_1m(monkeypatch):
    """Vérifie le branchement complet des 6 modèles long terme via `run_forecast`, avec
    `yfinance` simulé pour le titre, les ETF proxys, le marché, le taux sans risque et les
    dividendes — même mécanisme que les tests moyen terme."""
    import asyncio

    from app.forecast.pipeline import run_forecast
    from app.schemas import ForecastResponse

    rng = np.random.default_rng(27)
    n = 900
    close = 100 * np.exp(np.cumsum(rng.normal(0.0002, 0.015, n)))
    bars = pd.DataFrame(
        {"Open": close, "High": close * 1.01, "Low": close * 0.99, "Close": close, "Volume": 1_000_000.0},
        index=pd.bdate_range("2021-01-01", periods=n),
    )
    dividends = _fake_dividends(16, seed=28)
    earnings_dates = pd.DataFrame(
        {"EPS Estimate": [1.0] * 10, "Reported EPS": [1.05] * 10, "Surprise(%)": [0.05] * 10},
        index=pd.bdate_range("2021-02-01", periods=10, freq="63B", tz="America/New_York"),
    )

    class _FakeTicker:
        def __init__(self, symbol):
            self.symbol = symbol

        def history(self, period, auto_adjust, interval=None):
            return bars

        def get_earnings_dates(self, limit=40):
            return earnings_dates

        def get_info(self):
            return {"trailingPE": 22.0}

        @property
        def dividends(self):
            return dividends

        options = ()

    class _FakeYf:
        Ticker = _FakeTicker

    monkeypatch.setitem(__import__("sys").modules, "yfinance", _FakeYf)

    result = asyncio.run(run_forecast("TEST.PA", period="5y", horizon="1m"))
    result["indicator_code"] = "TEST.PA"
    validated = ForecastResponse(**result)  # lève si un champ manque ou a le mauvais type

    names = set(validated.long_term_models.keys()) | set(validated.long_term_errors.keys())
    assert names == {
        "cape",
        "dividend_yield",
        "gordon_ddm",
        "implied_erp",
        "value_profitability",
        "cointegration_vecm",
    }
    # à horizon "1w", aucun des 6 ne doit tourner du tout
    result_1w = asyncio.run(run_forecast("TEST.PA", period="5y", horizon="1w"))
    assert result_1w["long_term_models"] == {} and result_1w["long_term_errors"] == {}
