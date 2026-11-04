"""Tests des correctifs de l'audit de sécurité / performance (novembre 2026) :

- validation stricte des champs persistés par POST /market-activate (XSS stockée via `country`) ;
- symboles Yahoo validés sur /market-lookup ;
- refus des requêtes intersites (page tierce qui appelle l'API locale) ;
- blocage des tentatives d'authentification répétées ;
- CSP par défaut sur les réponses JSON ;
- quota de tickers ajoutés ;
- agrégat unique pour /indicators et limitation des resynchronisations Yahoo ;
- validation de KRONOS_BASE_URL.

Toujours sans réseau : `yfinance` est simulé."""
import datetime as dt
import importlib
import re
import sys
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.security import AuthFailureLimiter, is_cross_site_request

ROOT = Path(__file__).resolve().parent.parent


def _fresh_api(monkeypatch, tmp_path, **env):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import app as app_pkg

    for mod in [m for m in sys.modules if m.startswith("app.api")]:
        del sys.modules[mod]
    if hasattr(app_pkg, "api"):
        delattr(app_pkg, "api")
    return importlib.import_module("app.api")


def _daily_bars(n: int = 5) -> pd.DataFrame:
    dates = pd.bdate_range(end=dt.date.today(), periods=n)
    closes = [100.0 + i for i in range(n)]
    return pd.DataFrame(
        {"Open": closes, "High": [c + 1 for c in closes], "Low": [c - 1 for c in closes],
         "Close": closes, "Volume": [1000.0] * n},
        index=dates,
    )


class _Counter:
    calls = 0


def _install_fake_yfinance(monkeypatch, bars=None):
    _Counter.calls = 0

    class _FakeTicker:
        def __init__(self, symbol):
            self.symbol = symbol

        def history(self, **kwargs):
            _Counter.calls += 1
            return bars if bars is not None else _daily_bars()

        def get_info(self):
            return {"longName": "Acme <b>SA</b>\x00"}

    class _FakeYf:
        Ticker = _FakeTicker

    monkeypatch.setitem(sys.modules, "yfinance", _FakeYf)


# --------------------------------------------------------------------------- #
# Validation des entrées persistées
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "body",
    [
        {"symbol": "ACME.PA", "country": '<img src=x onerror=alert(1)>'},
        {"symbol": "<script>"},
        {"symbol": "A" * 21},
        {"symbol": "ACME.PA", "name": "x" * 500},
        {"symbol": "ACME.PA", "unexpected": "field"},
        {"symbol": "ACME.PA", "code": "../../etc"},
    ],
)
def test_activate_rejects_malicious_or_oversized_fields(tmp_path, monkeypatch, body):
    _install_fake_yfinance(monkeypatch)
    api = _fresh_api(monkeypatch, tmp_path)
    with TestClient(api.app) as c:
        assert c.post("/market-activate", json=body).status_code == 422


def test_activate_normalizes_country_and_cleans_third_party_name(tmp_path, monkeypatch):
    _install_fake_yfinance(monkeypatch)
    api = _fresh_api(monkeypatch, tmp_path)
    with TestClient(api.app) as c:
        r = c.post("/market-activate", json={"symbol": " ACME.PA ", "country": "fra"})
        assert r.status_code == 200, r.text
        assert r.json()["country"] == "FRA"
    from app.ohlcv_cache import OhlcvCache

    rows = OhlcvCache(tmp_path).list_custom()
    assert rows[0]["symbol"] == "ACME.PA"
    assert "\x00" not in (rows[0]["name"] or "")


def test_market_lookup_rejects_invalid_symbol(tmp_path, monkeypatch):
    _install_fake_yfinance(monkeypatch)
    api = _fresh_api(monkeypatch, tmp_path)
    with TestClient(api.app) as c:
        assert c.get("/market-lookup/%3Cscript%3E").status_code == 422
        assert c.get("/market-lookup/a%20b/ohlc").status_code == 422


def test_custom_ticker_quota(tmp_path, monkeypatch):
    _install_fake_yfinance(monkeypatch)
    api = _fresh_api(monkeypatch, tmp_path, API_MAX_CUSTOM_INDICATORS="1")
    with TestClient(api.app) as c:
        assert c.post("/market-activate", json={"symbol": "ACME.PA"}).status_code == 200
        r = c.post("/market-activate", json={"symbol": "OTHER.PA"})
        assert r.status_code == 409 and "limite" in r.json()["detail"]


# --------------------------------------------------------------------------- #
# Requêtes intersites
# --------------------------------------------------------------------------- #
def test_cross_site_requests_are_refused(tmp_path, monkeypatch):
    api = _fresh_api(monkeypatch, tmp_path)
    with TestClient(api.app) as c:
        assert c.get("/indicators", headers={"sec-fetch-site": "cross-site"}).status_code == 403
        assert c.get("/indicators", headers={"sec-fetch-site": "same-origin"}).status_code == 200
        assert c.get("/indicators").status_code == 200  # curl / scripts : pas d'en-tête Sec-Fetch
        r = c.post("/market-activate", json={"symbol": "ACME.PA"}, headers={"origin": "https://evil.example"})
        assert r.status_code == 403


def test_is_cross_site_request_rules():
    hosts = ["127.0.0.1", "localhost", "[::1]"]
    assert is_cross_site_request("GET", {"sec-fetch-site": "cross-site"}, hosts)
    assert not is_cross_site_request("GET", {"sec-fetch-site": "none"}, hosts)
    assert not is_cross_site_request("POST", {"origin": "http://localhost:5173"}, hosts)  # proxy Vite
    assert not is_cross_site_request("POST", {"origin": "http://[::1]:8100"}, hosts)
    assert is_cross_site_request("POST", {"origin": "null"}, hosts)
    assert is_cross_site_request("POST", {"origin": "http://attacker.test"}, hosts)
    assert not is_cross_site_request("GET", {"origin": "http://attacker.test"}, hosts)


# --------------------------------------------------------------------------- #
# Authentification
# --------------------------------------------------------------------------- #
def test_repeated_auth_failures_are_blocked(tmp_path, monkeypatch):
    api = _fresh_api(
        monkeypatch, tmp_path,
        API_USERNAME="louis", API_PASSWORD="un-mot-de-passe-long", API_AUTH_MAX_FAILURES="3",
    )
    with TestClient(api.app) as c:
        for _ in range(5):  # requêtes sans identifiants : invite du navigateur, pas des échecs
            assert c.get("/indicators").status_code == 401
        for _ in range(3):
            assert c.get("/indicators", auth=("louis", "faux")).status_code == 401
        r = c.get("/indicators", auth=("louis", "un-mot-de-passe-long"))
        assert r.status_code == 429 and int(r.headers["retry-after"]) > 0
        assert c.get("/health").status_code == 200  # sonde de vie toujours ouverte


def test_auth_failure_limiter_window_and_reset():
    lim = AuthFailureLimiter(max_failures=2, window_s=10)
    now = [0.0]
    lim._time = lambda: now[0]
    lim.record_failure("ip")
    assert lim.blocked_for("ip") == 0
    lim.record_failure("ip")
    assert lim.blocked_for("ip") > 0
    now[0] = 11.0  # fenêtre écoulée
    assert lim.blocked_for("ip") == 0


def test_trivial_password_is_refused(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("API_USERNAME", "administrateur")
    monkeypatch.setenv("API_PASSWORD", "administrateur")
    from app import serve

    monkeypatch.setattr(serve.uvicorn, "run", lambda *a, **k: pytest.fail("ne doit pas démarrer"))
    assert serve.main() == 2


# --------------------------------------------------------------------------- #
# En-têtes et tableau de bord
# --------------------------------------------------------------------------- #
def test_json_responses_get_restrictive_csp(tmp_path, monkeypatch):
    api = _fresh_api(monkeypatch, tmp_path)
    with TestClient(api.app) as c:
        csp = c.get("/indicators").headers["content-security-policy"]
        assert "default-src 'none'" in csp and "frame-ancestors 'none'" in csp
        assert "script-src 'sha256-" in c.get("/").headers["content-security-policy"]


def test_dashboard_escapes_country_values():
    """Les valeurs de pays (désormais aussi saisies via /market-activate) passent par `esc()`."""
    html = (ROOT / "app" / "static" / "dashboard.html").read_text(encoding="utf-8")
    assert 'data-country="${c}"' not in html
    assert not re.search(r"<span>\$\{nameFn\(k\)\}</span>", html)


# --------------------------------------------------------------------------- #
# Performance
# --------------------------------------------------------------------------- #
def test_ohlcv_stats_single_query(tmp_path):
    from app.ohlcv_cache import OhlcvCache

    cache = OhlcvCache(tmp_path)
    bars = pd.DataFrame({
        "date": [dt.date(2026, 1, 2), dt.date(2026, 1, 5)],
        "open": [1.0, 2.0], "high": [1.0, 2.0], "low": [1.0, 2.0], "close": [1.0, 2.0], "volume": [0.0, 0.0],
    })
    cache.upsert("AAA", bars)
    assert cache.stats(["AAA", "BBB"]) == {"AAA": (2, "2026-01-05")}
    assert cache.stats([]) == {}


def test_daily_sync_is_throttled_when_cache_is_behind_today(tmp_path, monkeypatch):
    """Dernière barre antérieure à aujourd'hui (week-end, avant l'ouverture) : l'ancien code
    réinterrogeait Yahoo à CHAQUE appel. Désormais, une seule fois par fenêtre MIN_RESYNC_S."""
    from app import marketdata
    from app.ohlcv_cache import OhlcvCache

    stale = _daily_bars(5)
    stale.index = stale.index - pd.Timedelta(days=7)
    _install_fake_yfinance(monkeypatch, bars=stale)
    cache = OhlcvCache(tmp_path)
    marketdata._sync_cache_sync("ACME", cache)  # backfill initial
    marketdata._sync_cache_sync("ACME", cache)
    marketdata._sync_cache_sync("ACME", cache)
    assert _Counter.calls == 1
    monkeypatch.setattr(marketdata, "MIN_RESYNC_S", 0)
    marketdata._sync_cache_sync("ACME", cache)
    assert _Counter.calls == 2


def test_indicators_merges_multi_source_rows(tmp_path, monkeypatch):
    api = _fresh_api(monkeypatch, tmp_path)
    frame = pd.DataFrame([
        {"indicator_code": "CN_GDP", "country": "CHN", "source": "nbs_china", "frequency": "A", "unit": "x",
         "n_obs": 3, "last_timestamp": pd.Timestamp("2020-01-01"), "last_ingested": None},
        {"indicator_code": "CN_GDP", "country": "CHN", "source": "worldbank", "frequency": "A", "unit": "x",
         "n_obs": 4, "last_timestamp": pd.Timestamp("2024-01-01"), "last_ingested": None},
    ])
    with TestClient(api.app):
        monkeypatch.setattr(api.store, "list_indicators", lambda: frame)
        stats = api._collected_stats()
    assert stats["CN_GDP"]["n_obs"] == 7
    assert stats["CN_GDP"]["last_timestamp"] == pd.Timestamp("2024-01-01")


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("bad", ["file:///etc/passwd", "ftp://host/x", "http://user:pw@127.0.0.1:3021", "127.0.0.1:3021"])
def test_kronos_base_url_is_validated(monkeypatch, tmp_path, bad):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("KRONOS_BASE_URL", bad)
    from app.config import load_settings

    with pytest.raises(ValueError):
        load_settings()


def test_kronos_base_url_accepts_internal_http(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("KRONOS_BASE_URL", "http://127.0.0.1:3021")
    from app.config import load_settings

    assert load_settings().kronos.enabled
