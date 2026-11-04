"""Tests des correctifs de sécurité : masquage des secrets, redirections, Retry-After, API
(authentification, en-têtes, Host, validation), confinement des fichiers manuels."""
import asyncio
import logging
import sys
import time

import httpx
import pytest
import respx

from app.config import load_settings
from app.httpclient import ApiClient, SourceUnavailable, UnsafeRedirect, parse_retry_after
from app.security import SecretRedactingFilter, check_basic_auth, redact_text, redact_url, register_secret


# --------------------------------------------------------------------------- #
# Masquage des secrets
# --------------------------------------------------------------------------- #
def test_redact_url_masks_secret_query_params():
    url = "https://api.stlouisfed.org/fred/series/observations?series_id=CPI&api_key=SECRET123&file_type=json"
    out = redact_url(url)
    assert "SECRET123" not in out
    assert "api_key=***" in out and "series_id=CPI" in out


def test_redact_url_masks_estat_appid_and_userinfo():
    out = redact_url("https://user:pw@api.e-stat.go.jp/rest/3.0/app/json/getStatsData?appId=XYZ987&statsDataId=1")
    assert "XYZ987" not in out and "pw@" not in out
    assert "statsDataId=1" in out


def test_registered_secret_is_masked_anywhere():
    register_secret("tres-secret-cle-42")
    assert "tres-secret-cle-42" not in redact_text("erreur avec la clé tres-secret-cle-42 dans le texte")


def test_log_filter_masks_secrets_in_messages_and_tracebacks():
    register_secret("cle-dans-une-trace-99")
    record = logging.LogRecord("x", logging.WARNING, __file__, 1, "GET %s", ("https://h/p?api_key=ABCDEF",), None)
    SecretRedactingFilter().filter(record)
    assert "ABCDEF" not in record.getMessage()

    try:
        raise RuntimeError("échec cle-dans-une-trace-99")
    except RuntimeError:
        rec2 = logging.LogRecord("x", logging.ERROR, __file__, 1, "boom", None, sys.exc_info())
    SecretRedactingFilter().filter(rec2)
    assert "cle-dans-une-trace-99" not in rec2.exc_text


# --------------------------------------------------------------------------- #
# Client HTTP
# --------------------------------------------------------------------------- #
@pytest.fixture()
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("FRED_API_KEY", "fredkey-abcdef")
    monkeypatch.setenv("HTTP_MAX_RETRIES", "1")
    return load_settings()


def test_parse_retry_after_seconds_date_and_cap():
    assert parse_retry_after("3") == 3.0
    assert parse_retry_after("99999") == 120.0  # borné
    assert parse_retry_after("garbage") is None
    assert parse_retry_after(None) is None
    now = time.time()
    http_date = time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime(now + 30))
    assert 25 <= parse_retry_after(http_date, now=now) <= 31  # date HTTP : faisait planter float()


@pytest.mark.asyncio
async def test_cross_host_redirect_is_refused(settings):
    src = settings.source("fred")
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://api.stlouisfed.org/fred/x").mock(
            return_value=httpx.Response(302, headers={"Location": "https://evil.example/steal"})
        )
        evil = mock.get("https://evil.example/steal").mock(return_value=httpx.Response(200))
        async with ApiClient(settings) as client:
            with pytest.raises(UnsafeRedirect):
                await client.get(src, "x", params={"api_key": "fredkey-abcdef"})
        assert not evil.called  # la clé n'a jamais été envoyée à l'autre domaine


@pytest.mark.asyncio
async def test_same_host_redirect_is_followed(settings):
    src = settings.source("fred")
    with respx.mock() as mock:
        mock.get("https://api.stlouisfed.org/fred/old").mock(
            return_value=httpx.Response(301, headers={"Location": "/fred/new"})
        )
        mock.get("https://api.stlouisfed.org/fred/new").mock(return_value=httpx.Response(200, json={"ok": 1}))
        async with ApiClient(settings) as client:
            resp = await client.get(src, "old")
        assert resp.json() == {"ok": 1}


@pytest.mark.asyncio
async def test_http_errors_do_not_leak_api_key(settings):
    src = settings.source("fred")
    with respx.mock() as mock:
        mock.get("https://api.stlouisfed.org/fred/x").mock(return_value=httpx.Response(400))
        async with ApiClient(settings) as client:
            with pytest.raises(httpx.HTTPStatusError) as ei:
                await client.get(src, "x", params={"api_key": "fredkey-abcdef"})
    assert "fredkey-abcdef" not in str(ei.value)


@pytest.mark.asyncio
async def test_exhausted_retries_message_is_redacted(settings, monkeypatch):
    real_sleep = asyncio.sleep

    async def no_wait(*_):
        await real_sleep(0)

    monkeypatch.setattr("app.httpclient.asyncio.sleep", no_wait)
    src = settings.source("fred")
    with respx.mock() as mock:
        mock.get("https://api.stlouisfed.org/fred/x").mock(return_value=httpx.Response(503))
        async with ApiClient(settings) as client:
            with pytest.raises(SourceUnavailable) as ei:
                await client.get(src, "x", params={"api_key": "fredkey-abcdef"})
    assert "fredkey-abcdef" not in str(ei.value)


def test_insecure_base_url_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("FRED_BASE_URL", "http://api.stlouisfed.org/fred")
    with pytest.raises(ValueError, match="https"):
        load_settings()


# --------------------------------------------------------------------------- #
# Fichiers déposés manuellement
# --------------------------------------------------------------------------- #
def test_safe_join_rejects_traversal(tmp_path):
    from app.connectors.base import safe_join

    assert safe_join(tmp_path, "rbi_cpi.csv") == (tmp_path / "rbi_cpi.csv").resolve()
    for bad in ("../.env", "/etc/passwd", "sub/../../x.csv"):
        with pytest.raises(ValueError):
            safe_join(tmp_path, bad)


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
def _fresh_api(monkeypatch, tmp_path, **env):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import importlib

    import app as app_pkg

    for mod in [m for m in sys.modules if m.startswith("app.api")]:
        del sys.modules[mod]
    if hasattr(app_pkg, "api"):
        delattr(app_pkg, "api")  # sinon `from app import api` renverrait l'ancien module
    return importlib.import_module("app.api")


def test_dashboard_has_strict_csp_and_security_headers(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    api = _fresh_api(monkeypatch, tmp_path)
    with TestClient(api.app) as c:
        r = c.get("/")
    csp = r.headers["content-security-policy"]
    assert "script-src 'sha256-" in csp and "unsafe-inline" not in csp.split("script-src")[1].split(";")[0]
    assert "frame-ancestors 'none'" in csp
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"


def test_untrusted_host_header_is_rejected(tmp_path, monkeypatch):
    """Protection DNS rebinding : une page malveillante qui ferait résoudre son domaine vers
    127.0.0.1 enverrait `Host: evil.example` — refusé."""
    from fastapi.testclient import TestClient

    api = _fresh_api(monkeypatch, tmp_path)
    with TestClient(api.app) as c:
        assert c.get("/health", headers={"host": "evil.example"}).status_code == 400
        assert c.get("/health", headers={"host": "127.0.0.1:8100"}).status_code == 200


def test_basic_auth_when_configured(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    api = _fresh_api(monkeypatch, tmp_path, API_USERNAME="louis", API_PASSWORD="un-mot-de-passe-long")
    with TestClient(api.app) as c:
        assert c.get("/health").status_code == 200  # sonde de vie ouverte
        r = c.get("/indicators")
        assert r.status_code == 401 and r.headers["www-authenticate"].startswith("Basic")
        assert c.get("/indicators", auth=("louis", "mauvais")).status_code == 401
        assert c.get("/indicators", auth=("louis", "un-mot-de-passe-long")).status_code == 200


def test_check_basic_auth_rejects_malformed():
    assert not check_basic_auth(None, "u", "p")
    assert not check_basic_auth("Bearer x", "u", "p")
    assert not check_basic_auth("Basic !!!", "u", "p")


def test_input_validation(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    api = _fresh_api(monkeypatch, tmp_path)
    with TestClient(api.app) as c:
        assert c.get("/series/..%2F..%2Fetc").status_code in (404, 422)
        assert c.get("/ohlc/DE_DAX?period=1d;rm").status_code == 422
        assert c.get("/forecast/DE_DAX?period=999y").status_code == 422
        too_many = ",".join(f"C{i}" for i in range(60))
        assert c.get(f"/panel?codes={too_many}").status_code == 422
        r = c.get("/portfolio?monte_carlo=true&mc_n_sims=10000&mc_horizon_days=2520")
        assert r.status_code == 422


def test_upstream_errors_are_generic(tmp_path, monkeypatch):
    """Le texte brut d'une exception tierce ne doit pas être renvoyé au client."""
    from fastapi.testclient import TestClient

    class _BoomTicker:
        def __init__(self, symbol):
            pass

        def history(self, **kwargs):
            raise RuntimeError("/home/louis/secret/path token=abcdef")

    class _FakeYf:
        Ticker = _BoomTicker

    monkeypatch.setitem(sys.modules, "yfinance", _FakeYf)
    api = _fresh_api(monkeypatch, tmp_path)
    with TestClient(api.app) as c:
        r = c.get("/ohlc/DE_DAX")
    assert r.status_code == 502
    assert "/home/louis" not in r.text and "abcdef" not in r.text


def test_public_bind_without_auth_is_refused(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("HOST", "0.0.0.0")
    monkeypatch.delenv("API_USERNAME", raising=False)
    monkeypatch.delenv("API_PASSWORD", raising=False)
    from app import serve

    monkeypatch.setattr(serve.uvicorn, "run", lambda *a, **k: pytest.fail("ne doit pas démarrer"))
    assert serve.main() == 2
