"""Recherche libre de tickers hors catalogue (`/market-search`, `/market-lookup`) et ajout à la
bibliothèque active (`POST /market-activate`) — voir `app/market_search.py`, l'extension de
`OhlcvCache` (table `custom_indicators`) et les nouveaux endpoints dans `app/api.py`.

Toujours sans réseau réel (Yahoo Finance bloqué dans cet environnement) : `yfinance` est simulé,
comme dans `test_api.py`."""
import datetime as dt
import sys

import pandas as pd
import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
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
        yield c


def _install_fake_yfinance(monkeypatch, *, search_quotes=None, history_bars=None, info=None):
    """Simule `yfinance.Search`, `yfinance.Ticker(...).history(...)` et `.get_info()`.
    `history_bars` : DataFrame renvoyé pour n'importe quel symbole/période (assez pour ces tests,
    qui portent sur un seul ticker à la fois)."""
    search_quotes = search_quotes if search_quotes is not None else []
    info = info or {}

    class _FakeSearch:
        def __init__(self, query, **kwargs):
            self.query = query
            self.quotes = search_quotes

    class _FakeTicker:
        def __init__(self, symbol):
            self.symbol = symbol

        def history(self, period=None, auto_adjust=True, interval=None, start=None):
            return history_bars if history_bars is not None else pd.DataFrame()

        def get_info(self):
            return info

    class _FakeYf:
        Search = _FakeSearch
        Ticker = _FakeTicker

    monkeypatch.setitem(sys.modules, "yfinance", _FakeYf)


def _daily_bars(n: int = 5, start_close: float = 100.0) -> pd.DataFrame:
    today = dt.date.today()
    dates = pd.bdate_range(end=today, periods=n)
    closes = [start_close + i for i in range(n)]
    return pd.DataFrame(
        {
            "Open": closes, "High": [c + 1 for c in closes], "Low": [c - 1 for c in closes],
            "Close": closes, "Volume": [1000.0 + i for i in range(n)],
        },
        index=dates,
    )


# --------------------------------------------------------------------------- #
# /market-search
# --------------------------------------------------------------------------- #
def test_market_search_flags_already_tracked_symbol(client, monkeypatch):
    _install_fake_yfinance(
        monkeypatch,
        search_quotes=[
            {"symbol": "^GDAXI", "shortname": "DAX", "exchange": "FRA", "quoteType": "INDEX"},
            {"symbol": "ACME.PA", "shortname": "Acme SA", "exchange": "PAR", "quoteType": "EQUITY"},
            {"shortname": "sans symbole, ignoré"},
        ],
    )
    resp = client.get("/market-search", params={"q": "dax"})
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 2  # le résultat sans "symbol" est filtré
    by_symbol = {r["symbol"]: r for r in rows}
    # ^GDAXI est le symbole de DE_DAX dans registry.py : déjà suivi.
    assert by_symbol["^GDAXI"]["already_tracked"] is True
    assert by_symbol["^GDAXI"]["code"] == "DE_DAX"
    assert by_symbol["ACME.PA"]["already_tracked"] is False
    assert by_symbol["ACME.PA"]["code"] is None
    assert by_symbol["ACME.PA"]["name"] == "Acme SA"


def test_market_search_requires_query(client):
    assert client.get("/market-search").status_code == 422


# --------------------------------------------------------------------------- #
# /market-lookup
# --------------------------------------------------------------------------- #
def test_market_lookup_returns_live_preview_without_persisting(client, monkeypatch, tmp_path):
    bars = _daily_bars()
    _install_fake_yfinance(monkeypatch, history_bars=bars)

    resp = client.get("/market-lookup/ACME.PA")
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "ACME.PA"
    assert data["already_tracked"] is False
    assert data["last"] == pytest.approx(bars["Close"].iloc[-1])

    # "juste observer" : rien n'est écrit dans le cache disque.
    from app.ohlcv_cache import OhlcvCache

    cache = OhlcvCache(tmp_path)
    try:
        assert cache.last_date("ACME.PA") is None
        assert cache.list_custom() == []
    finally:
        cache.close()


def test_market_lookup_ohlc_returns_bars_without_persisting(client, monkeypatch, tmp_path):
    bars = _daily_bars(n=4)
    _install_fake_yfinance(monkeypatch, history_bars=bars)

    resp = client.get("/market-lookup/ACME.PA/ohlc", params={"period": "6mo"})
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 4

    from app.ohlcv_cache import OhlcvCache

    cache = OhlcvCache(tmp_path)
    try:
        assert cache.last_date("ACME.PA") is None  # toujours rien en cache disque
    finally:
        cache.close()


def test_market_lookup_404_when_symbol_unknown(client, monkeypatch):
    _install_fake_yfinance(monkeypatch, history_bars=pd.DataFrame())
    assert client.get("/market-lookup/DOES_NOT_EXIST").status_code == 404


# --------------------------------------------------------------------------- #
# POST /market-activate
# --------------------------------------------------------------------------- #
def test_activate_persists_backfills_and_appears_in_indicators(client, monkeypatch, tmp_path):
    bars = _daily_bars(n=6, start_close=50.0)
    _install_fake_yfinance(monkeypatch, history_bars=bars, info={"longName": "Acme Corporation"})

    resp = client.post("/market-activate", json={"symbol": "ACME.PA", "name": "Acme SA"})
    assert resp.status_code == 200
    created = resp.json()
    # "." est un caractère valide pour un code (CODE_PATTERN) : pas remplacé par l'auto-dérivation.
    assert created["code"] == "YF_ACME.PA"
    assert created["connector"] == "yfinance"
    assert created["n_obs"] == 6
    assert created["last_timestamp"] == bars.index[-1].date().isoformat()

    # Apparaît tout de suite dans le catalogue, sans attendre le pipeline cron.
    rows = client.get("/indicators").json()
    by_code = {r["code"]: r for r in rows}
    assert "YF_ACME.PA" in by_code
    assert by_code["YF_ACME.PA"]["n_obs"] == 6

    # Son historique est bien dans le cache disque (ajouté dès l'activation).
    from app.ohlcv_cache import OhlcvCache

    cache = OhlcvCache(tmp_path)
    try:
        assert cache.last_date("ACME.PA") == bars.index[-1].date()
        custom = {c["code"]: c for c in cache.list_custom()}
        assert custom["YF_ACME.PA"]["symbol"] == "ACME.PA"
        assert custom["YF_ACME.PA"]["name"] == "Acme SA"  # nom transmis par le corps de la requête
    finally:
        cache.close()

    # /ohlc fonctionne désormais pour ce nouveau code comme pour n'importe quel indicateur.
    assert client.get("/ohlc/YF_ACME.PA").status_code == 200


def test_activate_rejects_symbol_already_tracked(client, monkeypatch):
    _install_fake_yfinance(monkeypatch, history_bars=_daily_bars())
    # ^GDAXI est déjà DE_DAX dans le catalogue statique.
    resp = client.post("/market-activate", json={"symbol": "^GDAXI"})
    assert resp.status_code == 409


def test_activate_rejects_duplicate_explicit_code(client, monkeypatch):
    _install_fake_yfinance(monkeypatch, history_bars=_daily_bars())
    first = client.post("/market-activate", json={"symbol": "ACME.PA", "code": "MY_ACME"})
    assert first.status_code == 200
    second = client.post("/market-activate", json={"symbol": "OTHER.PA", "code": "MY_ACME"})
    assert second.status_code == 409


def test_activate_rejects_invalid_code(client, monkeypatch):
    _install_fake_yfinance(monkeypatch, history_bars=_daily_bars())
    resp = client.post("/market-activate", json={"symbol": "ACME.PA", "code": "not a valid code!"})
    assert resp.status_code == 422


def test_activate_returns_404_for_unknown_symbol(client, monkeypatch):
    _install_fake_yfinance(monkeypatch, history_bars=pd.DataFrame())
    resp = client.post("/market-activate", json={"symbol": "GHOST.XX"})
    assert resp.status_code == 404


def test_activate_persists_across_api_restart(tmp_path, monkeypatch):
    """Un ticker activé reste connu après un redémarrage du processus API (table
    `custom_indicators` dans ohlcv_cache.duckdb, rechargée par `lifespan()`)."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import importlib

    import app as app_pkg

    def _fresh_client():
        for mod in [m for m in sys.modules if m.startswith("app.api")]:
            del sys.modules[mod]
        if hasattr(app_pkg, "api"):
            delattr(app_pkg, "api")
        from fastapi.testclient import TestClient

        return TestClient(importlib.import_module("app.api").app)

    bars = _daily_bars(n=3)
    _install_fake_yfinance(monkeypatch, history_bars=bars, info={"longName": "Acme Corporation"})

    with _fresh_client() as c1:
        resp = c1.post("/market-activate", json={"symbol": "ACME.PA"})
        assert resp.status_code == 200
        code = resp.json()["code"]

    with _fresh_client() as c2:
        rows = c2.get("/indicators").json()
        assert any(r["code"] == code for r in rows)
        assert client_ohlc_ok(c2, code)


def client_ohlc_ok(client, code: str) -> bool:
    return client.get(f"/ohlc/{code}").status_code == 200
