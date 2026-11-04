"""Endpoint `/ensemble/{code}` (prévision d'ensemble pondérée par backtest, voir
`app/forecast/weighting.py`) : validation du contrat (`EnsembleResponse`), codes d'erreur, et
absence d'appel réseau (historique déjà dans le cache OHLCV)."""
import datetime as dt
import sys

import numpy as np
import pandas as pd
import pytest


@pytest.fixture()
def client_and_api(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import importlib

    import app as app_pkg

    for mod in [m for m in sys.modules if m.startswith("app.api")]:
        del sys.modules[mod]
    if hasattr(app_pkg, "api"):
        delattr(app_pkg, "api")
    from fastapi.testclient import TestClient

    api_module = importlib.import_module("app.api")
    with TestClient(api_module.app) as c:
        yield c, api_module


def _seed(api_module, symbol: str, n: int, seed: int = 0) -> None:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end=dt.date.today(), periods=n)  # jusqu'à aujourd'hui : aucun réseau
    close = 100 * np.exp(np.cumsum(rng.normal(0.0002, 0.015, n)))
    api_module.ohlcv_cache.upsert(
        symbol,
        pd.DataFrame(
            {
                "date": [d.date() for d in dates], "open": close, "high": close * 1.01,
                "low": close * 0.99, "close": close, "volume": 1_000_000.0,
            }
        ),
    )


def test_ensemble_returns_schema_valid_payload(client_and_api):
    client, api_module = client_and_api
    symbol = api_module._market_spec("INDEX_SP500").params["symbol"]
    _seed(api_module, symbol, n=560, seed=1)

    resp = client.get("/ensemble/INDEX_SP500", params={"horizon": "1m", "method": "hedge"})
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["indicator_code"] == "INDEX_SP500"
    assert body["method"] == "hedge"
    assert body["combined"]["sigma_pct"] > 0
    assert body["backtest_n_test_points"] >= 5
    assert "baseline_naif" in body["backtest_models"]
    assert sum(body["weights"].values()) == pytest.approx(1.0)


def test_ensemble_insufficient_history_is_422_not_502(client_and_api):
    client, api_module = client_and_api
    symbol = api_module._market_spec("INDEX_SP500").params["symbol"]
    _seed(api_module, symbol, n=300, seed=2)

    resp = client.get("/ensemble/INDEX_SP500", params={"horizon": "1m"})
    assert resp.status_code == 422
    assert "insuffisant" in resp.json()["detail"]


def test_ensemble_rejects_invalid_params(client_and_api):
    client, _ = client_and_api
    assert client.get("/ensemble/INDEX_SP500", params={"method": "stacking"}).status_code == 422
    assert client.get("/ensemble/INDEX_SP500", params={"horizon": "1y"}).status_code == 422
