"""Méta-pondération (`app/forecast/weighting.py`, étape 3 de l'architecture : « Pondération
simple, puis Hedge ») : garde-fou « poids nul si la baseline n'est pas battue » dans les deux
schémas, comportement de Hedge sur des pertes synthétiques contrôlées, et combinaison de
prévisions en un ensemble mu_pct/sigma_pct."""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from app.forecast.weighting import (
    BASELINE_NAME,
    combine_predictions,
    hedge_weights,
    naive_weights,
    run_weighted_ensemble_forecast,
)
from app.ohlcv_cache import OhlcvCache


# --------------------------------------------------------------------------- #
# naive_weights : 1/erreur récente + garde-fou "baseline non battue"
# --------------------------------------------------------------------------- #

def test_naive_weights_proportional_to_inverse_crps():
    models = {
        BASELINE_NAME: {"crps_pct": 2.0},
        "good": {"crps_pct": 1.0},
        "better": {"crps_pct": 0.5},
    }
    weights = naive_weights(models)
    assert weights[BASELINE_NAME] == 0.0
    assert weights["better"] > weights["good"] > 0.0
    assert weights["good"] + weights["better"] == pytest.approx(1.0)


def test_naive_weights_zero_for_model_not_beating_baseline():
    models = {
        BASELINE_NAME: {"crps_pct": 1.0},
        "worse": {"crps_pct": 1.5},
        "tied": {"crps_pct": 1.0},
        "better": {"crps_pct": 0.5},
    }
    weights = naive_weights(models)
    assert weights["worse"] == 0.0
    assert weights["tied"] == 0.0  # égalité = pas "battue" -> poids nul
    assert weights["better"] == pytest.approx(1.0)


def test_naive_weights_all_fallback_to_baseline_when_nobody_beats_it():
    models = {BASELINE_NAME: {"crps_pct": 1.0}, "a": {"crps_pct": 2.0}, "b": {"crps_pct": 3.0}}
    weights = naive_weights(models)
    assert weights[BASELINE_NAME] == 1.0
    assert weights["a"] == 0.0 and weights["b"] == 0.0


def test_naive_weights_requires_baseline_present():
    with pytest.raises(ValueError):
        naive_weights({"a": {"crps_pct": 1.0}})


# --------------------------------------------------------------------------- #
# hedge_weights : poids exponentiels, gestion des points manqués, garde-fou final
# --------------------------------------------------------------------------- #

def test_hedge_favors_consistently_better_model():
    crps_series = {
        BASELINE_NAME: [1.0] * 20,
        "good": [0.2] * 20,
        "bad": [2.0] * 20,
    }
    weights = hedge_weights(crps_series, eta=0.5)
    assert weights["good"] > 0.0
    assert weights["bad"] == 0.0  # pire que la baseline sur toute la période -> poids nul
    assert weights[BASELINE_NAME] == 0.0
    assert weights["good"] == pytest.approx(1.0)


def test_hedge_missing_point_uses_worst_loss_of_the_day():
    """Un modèle absent à un point (`None`) hérite de la PIRE perte du jour, pas d'une perte
    neutre — vérifié en comparant deux modèles identiques sauf qu'un des deux est `None`
    (donc pénalisé par le pire tiers) sur un point où un troisième modèle fait très mal."""
    crps_series = {
        BASELINE_NAME: [1.0, 1.0, 1.0],
        "always_present": [0.5, 0.5, 0.5],
        "missing_once": [0.5, None, 0.5],
        "spikes_once": [0.5, 10.0, 0.5],  # fournit le "pire du jour" au point 1
    }
    weights = hedge_weights(crps_series, eta=0.5)
    # `missing_once` a hérité de 10.0 au point manqué, exactement comme `spikes_once` a réellement
    # subi 10.0 -> leurs poids finaux doivent être égaux (même perte cumulée).
    assert weights["missing_once"] == pytest.approx(weights["spikes_once"])
    assert weights["always_present"] > weights["missing_once"]


def test_hedge_requires_baseline_present():
    with pytest.raises(ValueError):
        hedge_weights({"a": [1.0, 2.0]})


def test_hedge_rejects_empty_series():
    with pytest.raises(ValueError):
        hedge_weights({BASELINE_NAME: []})


def test_hedge_weights_sum_to_one_or_all_baseline():
    crps_series = {
        BASELINE_NAME: [1.0, 0.9, 1.1, 1.0],
        "a": [0.8, 0.7, 0.9, 0.85],
        "b": [1.2, 1.3, 1.1, 1.25],
    }
    weights = hedge_weights(crps_series)
    total = sum(weights.values())
    assert total == pytest.approx(1.0) or total == pytest.approx(0.0)


# --------------------------------------------------------------------------- #
# combine_predictions
# --------------------------------------------------------------------------- #

def test_combine_predictions_weighted_average_of_mu():
    weights = {"a": 0.25, "b": 0.75, BASELINE_NAME: 0.0}
    predictions = {
        "a": {"mu_pct": 2.0, "sigma_pct": 1.0},
        "b": {"mu_pct": 0.0, "sigma_pct": 1.0},
        BASELINE_NAME: {"mu_pct": 0.0, "sigma_pct": 5.0},
    }
    combined = combine_predictions(weights, predictions)
    assert combined["mu_pct"] == pytest.approx(0.25 * 2.0 + 0.75 * 0.0)
    assert BASELINE_NAME not in combined["weights_used"]  # poids nul -> exclu du mélange


def test_combine_predictions_sigma_grows_with_disagreement():
    """Deux modèles de même mu_pct : sigma combiné = simple moyenne des variances. Mêmes poids
    mais mu_pct TRÈS différents : sigma combiné doit être strictement plus grand (désaccord)."""
    agree = combine_predictions(
        {"a": 0.5, "b": 0.5},
        {"a": {"mu_pct": 1.0, "sigma_pct": 2.0}, "b": {"mu_pct": 1.0, "sigma_pct": 2.0}},
    )
    disagree = combine_predictions(
        {"a": 0.5, "b": 0.5},
        {"a": {"mu_pct": -5.0, "sigma_pct": 2.0}, "b": {"mu_pct": 5.0, "sigma_pct": 2.0}},
    )
    assert disagree["sigma_pct"] > agree["sigma_pct"]
    assert agree["sigma_pct"] == pytest.approx(2.0)  # pas de désaccord -> juste la dispersion intra


def test_combine_predictions_raises_when_no_weighted_model_has_a_prediction():
    with pytest.raises(ValueError):
        combine_predictions({"a": 1.0}, {"b": {"mu_pct": 0.0, "sigma_pct": 1.0}})


# --------------------------------------------------------------------------- #
# run_weighted_ensemble_forecast : bout en bout
# --------------------------------------------------------------------------- #

@pytest.fixture()
def cache(tmp_path):
    c = OhlcvCache(tmp_path)
    yield c
    c.close()


def _seed_cache_ending_today(cache: OhlcvCache, symbol: str, n: int = 600, seed: int = 0) -> None:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end=dt.date.today(), periods=n)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0002, 0.015, n)))
    df = pd.DataFrame(
        {
            "date": [d.date() for d in dates], "open": close, "high": close * 1.01,
            "low": close * 0.99, "close": close, "volume": 1_000_000.0,
        }
    )
    cache.upsert(symbol, df)


@pytest.mark.asyncio
async def test_run_weighted_ensemble_forecast_hedge_and_naive(cache):
    _seed_cache_ending_today(cache, "FULLENS", n=600, seed=11)

    for method in ("naive", "hedge"):
        result = await run_weighted_ensemble_forecast("FULLENS", "1m", cache, method=method)
        assert result["method"] == method
        assert result["backtest_n_test_points"] >= 5
        assert isinstance(result["combined"]["mu_pct"], float)
        assert result["combined"]["sigma_pct"] > 0
        assert sum(result["weights"].values()) == pytest.approx(1.0) or sum(result["weights"].values()) == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_run_weighted_ensemble_forecast_rejects_bad_method(cache):
    _seed_cache_ending_today(cache, "BADMETHOD", n=600, seed=12)
    with pytest.raises(ValueError, match="méthode"):
        await run_weighted_ensemble_forecast("BADMETHOD", "1m", cache, method="stacking")
