"""Tests de `app/forecast/kronos_client.py` — construction du CSV envoyé et appel HTTP au point
d'accès `/api/forecast` (mocké via `respx`, aucun appel réseau réel), sur le même principe que
`test_httpclient_urls.py` pour les autres sources."""
from __future__ import annotations

import httpx
import numpy as np
import pandas as pd
import pytest
import respx

from app.config import KronosSettings, load_settings
from app.forecast.kronos_client import KronosNotConfigured, KronosUnavailable, _build_csv, kronos_forecast


def _synthetic_bars(n=500, seed=0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    idx = pd.bdate_range("2023-01-01", periods=n)
    return pd.DataFrame(
        {"Open": close, "High": close * 1.01, "Low": close * 0.99, "Close": close, "Volume": 1_000_000.0},
        index=idx,
    )


@pytest.fixture()
def settings_with_kronos(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("KRONOS_BASE_URL", "http://127.0.0.1:3021")
    monkeypatch.setenv("KRONOS_LOOKBACK", "400")
    monkeypatch.setenv("KRONOS_PRED_LEN", "10")
    return load_settings()


def test_kronos_disabled_without_base_url(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("KRONOS_BASE_URL", raising=False)
    settings = load_settings()
    assert settings.kronos.enabled is False


def test_build_csv_uses_lowercase_columns_and_lookback_window():
    bars = _synthetic_bars(500)
    csv_bytes = _build_csv(bars, lookback=400)
    df = pd.read_csv(pd.io.common.BytesIO(csv_bytes))
    assert list(df.columns) == ["timestamps", "open", "high", "low", "close"]
    assert len(df) == 400
    # les 400 DERNIÈRES barres, pas les 400 premières — sinon la "prévision" serait un backtest
    assert pd.Timestamp(df["timestamps"].iloc[-1]) == bars.index[-1]


def test_build_csv_rejects_insufficient_history():
    bars = _synthetic_bars(100)
    with pytest.raises(ValueError, match="historique insuffisant"):
        _build_csv(bars, lookback=400)


@pytest.mark.asyncio
async def test_kronos_forecast_not_configured_without_base_url(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("KRONOS_BASE_URL", raising=False)
    settings = load_settings()
    with pytest.raises(KronosNotConfigured):
        await kronos_forecast(_synthetic_bars(500), settings)


@pytest.mark.asyncio
async def test_kronos_forecast_calls_dedicated_endpoint_with_params(settings_with_kronos):
    bars = _synthetic_bars(500)
    with respx.mock(assert_all_called=True) as mock:
        route = mock.post("http://127.0.0.1:3021/api/forecast").mock(
            return_value=httpx.Response(200, json={
                "timestamps": ["2024-01-01T00:00:00"],
                "predictions": [{"open": 101.0, "high": 102.0, "low": 100.0, "close": 101.5}],
                "lookback": 400, "pred_len": 10, "last_known_close": 100.0,
            })
        )
        result = await kronos_forecast(bars, settings_with_kronos)
    called = route.calls.last.request
    assert called.url.params["lookback"] == "400"
    assert called.url.params["pred_len"] == "10"
    assert called.headers["content-type"] == "text/csv"
    assert result["lookback"] == 400
    assert result["predictions"][0]["close"] == 101.5


@pytest.mark.asyncio
async def test_kronos_forecast_raises_on_http_error(settings_with_kronos):
    bars = _synthetic_bars(500)
    with respx.mock(assert_all_called=True) as mock:
        mock.post("http://127.0.0.1:3021/api/forecast").mock(
            return_value=httpx.Response(503, json={"error": "modèle non chargé"})
        )
        with pytest.raises(KronosUnavailable, match="modèle non chargé"):
            await kronos_forecast(bars, settings_with_kronos)


@pytest.mark.asyncio
async def test_kronos_forecast_raises_on_network_error(settings_with_kronos):
    bars = _synthetic_bars(500)
    with respx.mock(assert_all_called=True) as mock:
        mock.post("http://127.0.0.1:3021/api/forecast").mock(side_effect=httpx.ConnectError("refused"))
        with pytest.raises(KronosUnavailable, match="ConnectError"):
            await kronos_forecast(bars, settings_with_kronos)
