"""Tests d'intégration du pipeline : bascule sur le repli, résilience aux échecs,
écriture effective dans DuckDB. Connecteurs mockés (aucun réseau)."""
import pandas as pd
import pytest

from app.cache import Store
from app.config import load_settings
from app.connectors.base import Connector, IndicatorSpec
from app.pipeline import run_one
from app.schema import build_frame


class _NullStore:
    """Cache toujours vide : suffisant pour tester `run_one` sans DuckDB."""

    def cache_get(self, source, key):
        return None

    def cache_set(self, source, key, payload, ttl):
        pass


class _FailingConnector(Connector):
    name = "boom"

    async def fetch_raw(self, spec):
        raise RuntimeError("source indisponible")

    def normalize(self, raw, spec):
        raise AssertionError("ne doit jamais être appelé")


class _WorkingConnector(Connector):
    name = "ok"

    async def fetch_raw(self, spec):
        return {}

    def normalize(self, raw, spec):
        return build_frame(timestamp=["2024-01-01"], country=spec.country, indicator_code=spec.code, value=[1.0], frequency=spec.frequency, unit=spec.unit, source=self.name)


@pytest.mark.asyncio
async def test_run_one_falls_back_when_primary_connector_fails():
    fallback_spec = IndicatorSpec("X_WB", "CHN", "ok", "A", "%", {})
    primary_spec = IndicatorSpec("X", "CHN", "boom", "M", "%", {}, fallback=fallback_spec)
    connectors = {"boom": _FailingConnector(None, _NullStore(), {}), "ok": _WorkingConnector(None, _NullStore(), {})}

    df = await run_one(connectors, primary_spec)

    assert not df.empty
    assert df.iloc[0]["indicator_code"] == "X_WB"  # bien le code du repli, pas le code primaire
    assert df.iloc[0]["source"] == "ok"


@pytest.mark.asyncio
async def test_run_one_returns_empty_without_fallback():
    spec = IndicatorSpec("X", "CHN", "boom", "M", "%", {})  # pas de fallback
    connectors = {"boom": _FailingConnector(None, _NullStore(), {})}
    df = await run_one(connectors, spec)
    assert df.empty


@pytest.mark.asyncio
async def test_run_one_writes_through_store(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    settings = load_settings()
    store = Store(settings.data_dir)
    spec = IndicatorSpec("X", "USA", "ok", "M", "%", {})
    connectors = {"ok": _WorkingConnector(None, store, {})}
    df = await run_one(connectors, spec)
    n = store.upsert_observations(df)
    assert n == 1
    assert not store.read_series("X").empty
    store.close()
