"""Vérifie la construction des requêtes (URL, paramètres, en-têtes) sans réseau réel,
via `respx` (mock du transport httpx). Complète les tests de `normalize()` : ici on
vérifie que `fetch_raw()` interroge le bon endpoint avec les bons paramètres.
"""
import httpx
import pandas as pd
import pytest
import respx

from app.cache import Store
from app.config import load_settings
from app.connectors.base import IndicatorSpec
from app.connectors.ecb import EcbConnector
from app.connectors.fred import FredConnector
from app.connectors.worldbank import WorldBankConnector
from app.httpclient import ApiClient


@pytest.fixture()
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("FRED_API_KEY", "abc123")
    return load_settings()


@pytest.mark.asyncio
async def test_fred_fetch_raw_calls_documented_endpoint(settings, tmp_path):
    store = Store(settings.data_dir)
    with respx.mock(assert_all_called=True) as mock:
        route = mock.get("https://api.stlouisfed.org/fred/series/observations").mock(
            return_value=httpx.Response(200, json={"observations": []})
        )
        async with ApiClient(settings) as client:
            conn = FredConnector(client, store, settings.cache_ttl_s)
            spec = IndicatorSpec("US_FEDFUNDS", "USA", "fred", "M", "%", {"series_id": "FEDFUNDS"})
            await conn.fetch_raw(spec)
        called = route.calls.last.request.url
        assert called.params["series_id"] == "FEDFUNDS"
        assert called.params["api_key"] == "abc123"
        assert called.params["file_type"] == "json"
    store.close()


@pytest.mark.asyncio
async def test_ecb_fetch_raw_builds_dataflow_key_path(settings):
    store = Store(settings.data_dir)
    with respx.mock(assert_all_called=True) as mock:
        route = mock.get(url__regex=r"https://data-api\.ecb\.europa\.eu/service/data/FM/.*").mock(
            return_value=httpx.Response(200, text="TIME_PERIOD,OBS_VALUE\n")
        )
        async with ApiClient(settings) as client:
            conn = EcbConnector(client, store, settings.cache_ttl_s)
            spec = IndicatorSpec("EA_DFR", "EA", "ecb", "D", "%", {"dataflow": "FM", "key": "D.U2.EUR.4F.KR.DFR.LEV"})
            await conn.fetch_raw(spec)
        assert route.calls.last.request.url.params["format"] == "csvdata"
    store.close()


@pytest.mark.asyncio
async def test_worldbank_fetch_raw_uses_iso3_and_indicator_in_path(settings):
    store = Store(settings.data_dir)
    with respx.mock(assert_all_called=True) as mock:
        route = mock.get(url__regex=r"https://api\.worldbank\.org/v2/country/CHN/indicator/NY\.GDP\.MKTP\.KD\.ZG").mock(
            return_value=httpx.Response(200, json=[{}, []])
        )
        async with ApiClient(settings) as client:
            conn = WorldBankConnector(client, store, settings.cache_ttl_s)
            spec = IndicatorSpec("CN_GDP", "CHN", "worldbank", "A", "%", {"iso3": "CHN", "indicator": "NY.GDP.MKTP.KD.ZG"})
            await conn.fetch_raw(spec)
        assert route.calls.last.request.url.params["format"] == "json"
    store.close()


@pytest.mark.asyncio
async def test_get_raw_uses_cache_on_second_call(settings):
    """Le deuxième appel à `get_raw` pour le même indicateur ne doit PAS retoucher le réseau
    (cache DuckDB) tant que le TTL n'est pas expiré."""
    store = Store(settings.data_dir)
    with respx.mock() as mock:
        route = mock.get("https://api.stlouisfed.org/fred/series/observations").mock(
            return_value=httpx.Response(200, json={"observations": []})
        )
        async with ApiClient(settings) as client:
            conn = FredConnector(client, store, settings.cache_ttl_s)
            spec = IndicatorSpec("US_FEDFUNDS", "USA", "fred", "M", "%", {"series_id": "FEDFUNDS"})
            await conn.get_raw(spec)
            await conn.get_raw(spec)
        assert route.call_count == 1
    store.close()


@pytest.mark.asyncio
async def test_imf_fetch_raw_builds_path_and_auth_header(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("IMF_API_KEY", "secret-key-123")
    from app.config import load_settings
    from app.connectors.imf import ImfConnector

    settings = load_settings()
    store = Store(settings.data_dir)
    with respx.mock(assert_all_called=True) as mock:
        route = mock.get(
            "https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.STA/CPI/+/FRA.CPI.*.IX.M"
        ).mock(return_value=httpx.Response(200, json={"data": {"dataSets": [], "structures": []}}))
        async with ApiClient(settings) as client:
            conn = ImfConnector(client, store, settings.cache_ttl_s)
            spec = IndicatorSpec("FR_CPI", "FRA", "imf", "M", "indice", {"agency_id": "IMF.STA", "resource_id": "CPI", "version": "+", "key": "FRA.CPI.*.IX.M"})
            await conn.fetch_raw(spec)
        assert route.calls.last.request.headers["Ocp-Apim-Subscription-Key"] == "secret-key-123"
    store.close()


@pytest.mark.asyncio
async def test_yfinance_fetch_raw_calls_ticker_history_in_thread(monkeypatch, tmp_path):
    """`fetch_raw` ne passe pas par ApiClient/httpx (yfinance gère son propre réseau) : on
    vérifie donc que `_fetch_history_sync` reçoit le bon ticker et la bonne période, en
    remplaçant yfinance.Ticker par un faux objet — aucun réseau réel nécessaire."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.config import load_settings
    from app.connectors import yfin as yfin_module

    calls = []

    class _FakeTicker:
        def __init__(self, symbol):
            calls.append(symbol)

        def history(self, period, auto_adjust):
            idx = pd.to_datetime(["2024-01-02", "2024-01-03"])
            return pd.DataFrame({"Close": [100.0, 101.5]}, index=idx)

    class _FakeYf:
        Ticker = _FakeTicker

    monkeypatch.setitem(__import__("sys").modules, "yfinance", _FakeYf)

    settings = load_settings()
    store = Store(settings.data_dir)
    async with ApiClient(settings) as client:
        conn = yfin_module.YFinanceConnector(client, store, settings.cache_ttl_s)
        spec = IndicatorSpec("DE_DAX", "DEU", "yfinance", "D", "points d'indice", {"symbol": "^GDAXI", "period": "5y"})
        raw = await conn.fetch_raw(spec)
    assert calls == ["^GDAXI"]
    assert raw["values"] == [100.0, 101.5]
    store.close()
