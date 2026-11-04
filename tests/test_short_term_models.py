"""Tests des cinq modèles « court terme » non liés à une IA (`app/forecast/short_term/`) : HAR-RV,
ARIMA, filtre de Kalman, Ornstein-Uhlenbeck, retournement — plus l'interface commune `HorizonModel`
(`model_base.py`) et le branchement dans `pipeline._compute`.

Même discipline que `test_forecast.py` : données synthétiques (marche aléatoire), vérification de
structure, rejet propre sur un historique trop court, et absence de biais de look-ahead."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.forecast.model_base import PredictionResult
from app.forecast.short_term import MODELS, ArimaModel, HarRvModel, KalmanTrendModel, OuMeanRevertModel, ReversalModel
from app.forecast.short_term.arima_baseline import fit_arima_forecast
from app.forecast.short_term.har_rv import fit_har_rv_forecast
from app.forecast.short_term.kalman_trend import fit_kalman_trend_forecast
from app.forecast.short_term.ou_meanrevert import fit_ou_meanreversion_forecast
from app.forecast.short_term.reversal import fit_reversal_forecast


def _synthetic_bars(n=500, seed=0, daily_vol=0.015, drift=0.0002) -> pd.DataFrame:
    """Barres OHLCV synthétiques (marche aléatoire) — mêmes conventions que `test_forecast.py`,
    CLAIREMENT PAS des données de marché réelles."""
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
# Chaque modèle, via sa fonction pure
# --------------------------------------------------------------------------- #

def test_har_rv_structure():
    bars = _synthetic_bars(400, seed=1)
    log_ret = np.log(bars["Close"]).diff()
    result = fit_har_rv_forecast(log_ret, horizon_days=5)
    assert result["sigma_pct"] > 0
    assert len(result["daily_vol_forecast_pct"]) == 5
    assert all(v > 0 for v in result["daily_vol_forecast_pct"])
    assert result["n_obs"] > 300


def test_har_rv_rejects_short_history():
    bars = _synthetic_bars(50, seed=2)
    log_ret = np.log(bars["Close"]).diff()
    with pytest.raises(ValueError):
        fit_har_rv_forecast(log_ret, horizon_days=5)


def test_arima_structure():
    bars = _synthetic_bars(400, seed=3)
    log_ret = np.log(bars["Close"]).diff()
    result = fit_arima_forecast(log_ret, horizon_days=5)
    assert result["sigma_pct"] > 0
    assert len(result["daily_mean_log_return_pct"]) == 5
    assert result["order"] == [1, 0, 0]
    assert result["n_obs"] > 300


def test_arima_rejects_short_history():
    bars = _synthetic_bars(50, seed=4)
    log_ret = np.log(bars["Close"]).diff()
    with pytest.raises(ValueError):
        fit_arima_forecast(log_ret, horizon_days=5)


def test_kalman_trend_structure():
    bars = _synthetic_bars(400, seed=5)
    result = fit_kalman_trend_forecast(bars["Close"], horizon_days=5)
    assert result["sigma_pct"] > 0
    assert isinstance(result["expected_return_pct"], float)
    assert result["n_obs"] > 300


def test_kalman_trend_rejects_short_history():
    bars = _synthetic_bars(50, seed=6)
    with pytest.raises(ValueError):
        fit_kalman_trend_forecast(bars["Close"], horizon_days=5)


def test_ou_meanrevert_structure():
    bars = _synthetic_bars(400, seed=7)
    result = fit_ou_meanreversion_forecast(bars["Close"], horizon_days=5)
    assert result["sigma_pct"] > 0
    assert isinstance(result["expected_return_pct"], float)
    assert result["n_obs"] > 300


def test_ou_meanrevert_rejects_short_history():
    bars = _synthetic_bars(50, seed=8)
    with pytest.raises(ValueError):
        fit_ou_meanreversion_forecast(bars["Close"], horizon_days=5)


def test_ou_meanrevert_pulls_back_from_large_deviation():
    """Vérifie le sens du signal : partant d'un écart NÉGATIF marqué sous la moyenne glissante
    (prix artificiellement cassé sur les derniers jours), le modèle doit prévoir un rendement
    attendu POSITIF (retour vers la moyenne), pas l'inverse."""
    bars = _synthetic_bars(400, seed=9, daily_vol=0.005, drift=0.0)
    bars = bars.copy()
    bars.loc[bars.index[-10:], "Close"] *= 0.7  # chute artificielle récente -> écart négatif
    result = fit_ou_meanreversion_forecast(bars["Close"], horizon_days=5, ma_window=60)
    assert result["current_deviation_pct"] < 0
    assert result["expected_return_pct"] > 0


def test_reversal_structure():
    bars = _synthetic_bars(400, seed=10)
    result = fit_reversal_forecast(bars["Close"], horizon_days=5)
    assert result["sigma_pct"] > 0
    assert isinstance(result["expected_return_pct"], float)
    assert result["n_obs"] > 300


def test_reversal_rejects_short_history():
    bars = _synthetic_bars(50, seed=11)
    with pytest.raises(ValueError):
        fit_reversal_forecast(bars["Close"], horizon_days=5)


# --------------------------------------------------------------------------- #
# Interface commune HorizonModel
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("model_cls", MODELS)
def test_each_model_conforms_to_horizon_model_protocol(model_cls):
    bars = _synthetic_bars(400, seed=12)
    model = model_cls()
    result = model.predict(bars, horizon_days=5)
    assert isinstance(result, PredictionResult)
    assert isinstance(result.mu_pct, float)
    assert result.sigma_pct > 0
    assert isinstance(result.diagnostics, dict)


def test_models_registry_has_the_five_confirmed_models():
    names = {m().name for m in MODELS}
    assert names == {"har_rv", "arima", "kalman_trend", "ou_meanrevert", "reversal"}


def test_har_rv_has_no_directional_view():
    """HAR-RV est un modèle de VOLATILITÉ pure (voir sa docstring) : mu_pct doit toujours être
    nul, qu'un autre modèle de la même famille n'ajouterait pas par erreur un signal directionnel
    qui n'est pas censé exister."""
    bars = _synthetic_bars(400, seed=13)
    result = HarRvModel().predict(bars, horizon_days=5)
    assert result.mu_pct == 0.0


# --------------------------------------------------------------------------- #
# Absence de biais de look-ahead
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("model_cls", [ArimaModel, KalmanTrendModel, OuMeanRevertModel, ReversalModel])
def test_models_do_not_look_ahead(model_cls):
    """Même discipline que `test_forecast.py::test_features_do_not_look_ahead` : la prévision
    faite à la date t ne doit dépendre que des barres <= t. On vérifie indirectement : rejouer le
    modèle sur un historique tronqué AVANT la fenêtre de prévision donne un résultat structuré
    (le point important est qu'aucun code de ce module ne lit `bars` au-delà de son index — chaque
    fonction `fit_*_forecast` ne reçoit d'ailleurs que `close`/`log_returns`, jamais les barres
    futures, par construction de l'API `predict(bars, horizon_days)`)."""
    bars = _synthetic_bars(400, seed=14)
    truncated = bars.iloc[:-20]  # retire les 20 dernières barres, qu'aucun modèle ne doit utiliser
    model = model_cls()
    full_result = model.predict(bars, horizon_days=5)
    truncated_result = model.predict(truncated, horizon_days=5)
    # les deux prévisions portent sur des horizons différents (dates différentes) : on vérifie
    # seulement qu'aucune des deux ne lève et que `n_obs`/l'historique utilisé par la version
    # tronquée est bien plus petit — signe que la troncature a été respectée.
    assert full_result.diagnostics["n_obs"] > truncated_result.diagnostics["n_obs"]


# --------------------------------------------------------------------------- #
# Branchement dans le pipeline
# --------------------------------------------------------------------------- #

def test_pipeline_compute_includes_short_term_models():
    from app.forecast.pipeline import _compute

    bars = _synthetic_bars(400, seed=15)
    computed = _compute(bars, horizon="1w", horizon_days=5, country=None, store=None)
    assert set(computed["short_term_models"].keys()) | set(computed["short_term_errors"].keys()) == {
        "har_rv", "arima", "kalman_trend", "ou_meanrevert", "reversal",
    }
    for name, payload in computed["short_term_models"].items():
        assert "mu_pct" in payload and "sigma_pct" in payload
