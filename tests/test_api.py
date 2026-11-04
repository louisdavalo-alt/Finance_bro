"""Tests de l'API de consultation (FastAPI), à partir de données déjà en base."""
import sys

import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import importlib

    import app as app_pkg

    for mod in [m for m in sys.modules if m.startswith("app.api")]:
        del sys.modules[mod]
    if hasattr(app_pkg, "api"):
        delattr(app_pkg, "api")  # sinon `from app import api` renvoie l'ancien module (autre DATA_DIR)
    from fastapi.testclient import TestClient

    api_module = importlib.import_module("app.api")

    with TestClient(api_module.app) as c:
        # insère une observation via le Store du PIPELINE (écriture DuckDB + export Parquet),
        # pendant que l'API tourne : c'est précisément le cas qui provoquait autrefois le
        # « Conflicting lock is held » (l'API garde désormais ses mains hors de macro.duckdb).
        from app.cache import Store
        from app.schema import build_frame

        df = build_frame(timestamp=["2024-01-01", "2024-02-01"], country="USA", indicator_code="US_CPI", value=[300.0, 301.0], frequency="M", unit="indice", source="fred", publication_lag_days=15)
        writer = Store(tmp_path)
        try:
            writer.upsert_observations(df)
        finally:
            writer.close()
        yield c


def test_health(client):
    assert client.get("/health").json() == {"ok": True}


def test_indicators_lists_catalog_with_collected_stats(client):
    rows = client.get("/indicators").json()
    by_code = {r["code"]: r for r in rows}
    assert "US_CPI" in by_code
    assert by_code["US_CPI"]["n_obs"] == 2
    # Un indicateur jamais collecté (ex. chinois, sans clé dans ce test) apparaît avec n_obs=0.
    assert any(r["n_obs"] == 0 for r in rows)


def test_series_returns_404_when_empty(client):
    assert client.get("/series/DOES_NOT_EXIST").status_code == 404


def test_series_returns_observations(client):
    rows = client.get("/series/US_CPI").json()
    assert [r["value"] for r in rows] == [300.0, 301.0]


def test_panel_aligns_without_lookahead(client):
    out = client.get("/panel", params={"codes": "US_CPI", "freq": "M"}).json()
    rows = {r["date"]: r["US_CPI"] for r in out["rows"]}
    assert rows["2024-01-01"] is None  # pas encore publié
    assert rows["2024-02-01"] == 300.0  # janvier connu (lag 15j)


def test_lag_report(client):
    report = client.get("/lag-report").json()
    row = next(r for r in report if r["indicator_code"] == "US_CPI")
    assert row["median_lag_days"] == 15


def test_ohlc_rejects_non_yfinance_indicator(client):
    """US_CPI est un indicateur macro (connecteur fred) : pas de notion d'O/H/L/C/V."""
    resp = client.get("/ohlc/US_CPI")
    assert resp.status_code == 400


def test_ohlc_returns_404_for_unknown_code(client):
    resp = client.get("/ohlc/CODE_INEXISTANT")
    assert resp.status_code == 404


def test_ohlc_returns_bars_for_yfinance_indicator(client, monkeypatch):
    """DE_DAX est un indicateur de marché (yfinance) : on simule yfinance.Ticker pour vérifier
    que l'endpoint transforme correctement son DataFrame OHLCV en JSON, sans réseau réel.

    L'historique est désormais servi par le cache OHLCV local (voir ohlcv_cache.py/marketdata.py),
    qui tronque la réponse à la fenêtre `period` demandée (2y par défaut) à partir d'AUJOURD'HUI :
    les dates simulées doivent donc être récentes, pas des dates fixes du passé, sinon elles
    tombent hors de cette fenêtre au fil du temps."""
    import datetime as dt

    import pandas as pd

    today = dt.date.today()
    d1 = (today - dt.timedelta(days=2)).isoformat()
    d2 = (today - dt.timedelta(days=1)).isoformat()

    class _FakeTicker:
        def __init__(self, symbol):
            self.symbol = symbol

        def history(self, period=None, auto_adjust=True, interval=None, start=None):
            idx = pd.to_datetime([d1, d2])
            return pd.DataFrame(
                {"Open": [100.0, 101.0], "High": [105.0, 106.0], "Low": [99.0, 100.5],
                 "Close": [104.0, 105.5], "Volume": [1000, 1200]},
                index=idx,
            )

    class _FakeYf:
        Ticker = _FakeTicker

    monkeypatch.setitem(__import__("sys").modules, "yfinance", _FakeYf)

    resp = client.get("/ohlc/DE_DAX")
    assert resp.status_code == 200
    bars = resp.json()
    assert len(bars) == 2
    assert bars[0] == {"date": d1, "open": 100.0, "high": 105.0, "low": 99.0, "close": 104.0, "volume": 1000.0}


class _FakeFastInfo:
    market_cap = 5_000_000_000.0
    currency = "EUR"


def _install_fake_yfinance(monkeypatch):
    """yfinance simulé : historique quotidien + une séance intraday (3 barres de 5 minutes)."""
    import pandas as pd

    class _FakeTicker:
        fast_info = _FakeFastInfo()

        def __init__(self, symbol):
            self.symbol = symbol

        def history(self, period, auto_adjust, interval=None):
            if interval == "5m":
                idx = pd.to_datetime(["2024-01-03 09:00", "2024-01-03 09:05", "2024-01-03 09:10"])
                return pd.DataFrame(
                    {"Open": [100.0, 101.0, 102.0], "High": [101.0, 103.0, 102.5],
                     "Low": [99.5, 100.5, 101.0], "Close": [101.0, 102.0, 101.5],
                     "Volume": [10, 20, 30]}, index=idx)
            idx = pd.to_datetime(["2023-06-01", "2024-01-02", "2024-01-03"])
            return pd.DataFrame(
                {"Open": [95.0, 99.0, 100.0], "High": [120.0, 105.0, 103.0],
                 "Low": [90.0, 98.0, 100.5], "Close": [110.0, 100.0, 101.5],
                 "Volume": [500, 600, 60]}, index=idx)

    class _FakeYf:
        Ticker = _FakeTicker

    monkeypatch.setitem(__import__("sys").modules, "yfinance", _FakeYf)


def test_quote_rejects_macro_and_unknown(client):
    assert client.get("/quote/US_CPI").status_code == 400
    assert client.get("/quote/CODE_INEXISTANT").status_code == 404


def test_quote_summary_values(client, monkeypatch):
    _install_fake_yfinance(monkeypatch)
    resp = client.get("/quote/DE_DAX")
    assert resp.status_code == 200
    q = resp.json()
    assert q["intraday"] is True
    assert q["last"] == 101.5 and q["last_time"] == "2024-01-03 09:10"
    assert q["open"] == 100.0
    assert q["high"] == 103.0 and q["high_time"] == "09:05"
    assert q["low"] == 99.5 and q["low_time"] == "09:00"
    assert q["volume"] == 60
    assert q["turnover"] == pytest.approx(101 * 10 + 102 * 20 + 101.5 * 30)
    # VWAP = somme(prix typique x volume) / volume total, prix typique = (H+L+C)/3
    tp = [(101 + 99.5 + 101) / 3, (103 + 100.5 + 102) / 3, (102.5 + 101 + 101.5) / 3]
    assert q["vwap"] == pytest.approx((tp[0] * 10 + tp[1] * 20 + tp[2] * 30) / 60)
    # clôture de la veille = dernière clôture quotidienne STRICTEMENT avant le jour de séance
    assert q["previous_close"] == 100.0
    assert q["change"] == pytest.approx(1.5) and q["change_pct"] == pytest.approx(1.5)
    assert q["week52_high"] == 120.0 and q["week52_low"] == 90.0
    assert q["market_cap"] == 5_000_000_000.0
    assert q["currency"] == "EUR" and q["symbol"] == "^GDAXI"


def test_chart_ranges(client, monkeypatch):
    _install_fake_yfinance(monkeypatch)
    intraday = client.get("/chart/DE_DAX?range=1D").json()
    assert intraday[0]["date"] == "2024-01-03 09:00"  # heure conservée en intraday
    daily = client.get("/chart/DE_DAX?range=5Y").json()
    assert daily[0]["date"] == "2023-06-01"  # date seule (sans heure) pour les périodes quotidiennes
    assert client.get("/chart/DE_DAX?range=NOPE").status_code == 422
    assert client.get("/chart/US_CPI?range=1D").status_code == 400


def test_chart_daily_range_uses_ohlcv_cache_and_skips_second_network_call(tmp_path, monkeypatch):
    """1M/3M/1Y/5Y/YTD passent désormais par le cache OHLCV local (voir quote.py) quand un cache
    est fourni : un second appel pour le même symbole/plage, le même jour, ne doit faire AUCUN
    nouvel appel réseau. Testé directement sur `fetch_chart` (pas via l'API) pour isoler ce
    cache-ci du cache mémoire à TTL de `/chart` (`LiveCache`), qui masquerait sinon la même
    chose pour une raison différente."""
    import asyncio
    import datetime as dt

    import pandas as pd

    from app.ohlcv_cache import OhlcvCache
    from app.quote import fetch_chart

    today = dt.date.today()
    calls = []

    class _FakeTicker:
        def __init__(self, symbol):
            self.symbol = symbol

        def history(self, period=None, auto_adjust=True, interval=None, start=None):
            calls.append({"period": period, "start": start})
            idx = pd.to_datetime([today.isoformat()])  # barre d'aujourd'hui : cache déjà à jour
            return pd.DataFrame(
                {"Open": [100.0], "High": [101.0], "Low": [99.0], "Close": [100.5], "Volume": [10]}, index=idx)

    class _FakeYf:
        Ticker = _FakeTicker

    monkeypatch.setitem(__import__("sys").modules, "yfinance", _FakeYf)

    cache = OhlcvCache(tmp_path)
    try:
        first = asyncio.run(fetch_chart("DE_DAX", "5Y", cache))
        second = asyncio.run(fetch_chart("DE_DAX", "5Y", cache))
    finally:
        cache.close()

    assert len(calls) == 1  # mis en cache localement, pas redemandé
    assert first == second

    # Sans cache fourni (comportement par défaut), chaque appel reste direct.
    calls.clear()
    asyncio.run(fetch_chart("DE_DAX", "5Y"))
    asyncio.run(fetch_chart("DE_DAX", "5Y"))
    assert len(calls) == 2


# --------------------------------------------------------------------------- #
# Schémas de réponse (app/schemas.py) — /forecast et /portfolio ne passent pas
# par `client` ci-dessus (nécessiteraient tout le registre + historique réel) : on valide donc le
# CONTRAT entre le dict réellement renvoyé par le pipeline et le modèle Pydantic qui décrit
# l'endpoint (c'est précisément ce que FastAPI validerait à l'exécution via `response_model`).
# --------------------------------------------------------------------------- #

def test_forecast_result_matches_response_schema(monkeypatch):
    import asyncio

    import numpy as np
    import pandas as pd

    from app.forecast.pipeline import run_forecast
    from app.schemas import ForecastResponse

    n = 1500
    rng = np.random.default_rng(21)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0002, 0.015, n)))
    bars = pd.DataFrame(
        {"Open": close, "High": close * 1.01, "Low": close * 0.99, "Close": close, "Volume": 1_000_000.0},
        index=pd.bdate_range("2018-01-01", periods=n),
    )
    calls = pd.DataFrame({"strike": [95, 100, 105], "volume": [10, 20, 5], "openInterest": [10, 20, 5], "impliedVolatility": [0.3, 0.25, 0.22]})
    puts = pd.DataFrame({"strike": [95, 100, 105], "volume": [8, 15, 12], "openInterest": [8, 15, 12], "impliedVolatility": [0.28, 0.24, 0.20]})

    class _FakeTicker:
        def __init__(self, symbol): pass
        def history(self, period, auto_adjust, interval=None): return bars
        options = ("2026-10-17",)
        def option_chain(self, exp): return type("Chain", (), {"calls": calls, "puts": puts})()
        class fast_info:
            last_price = 100.0

    class _FakeYf:
        Ticker = _FakeTicker
    monkeypatch.setitem(__import__("sys").modules, "yfinance", _FakeYf)

    result = asyncio.run(run_forecast("TEST.PA", period="5y"))
    result["indicator_code"] = "TEST.PA"
    validated = ForecastResponse(**result)  # lève si un champ manque ou a le mauvais type
    assert validated.ml_forecast is not None
    assert validated.options is not None


def test_portfolio_result_matches_response_schema():
    import numpy as np
    import pandas as pd

    from app.portfolio.pipeline import build_portfolio
    from app.schemas import PortfolioResponse

    class _FakeStore:
        def __init__(self, codes_and_vol, n=400, seed=0):
            rng = np.random.default_rng(seed)
            dates = pd.bdate_range("2023-01-01", periods=n)
            rows = []
            for code, vol in codes_and_vol.items():
                prices = 100 * np.exp(np.cumsum(rng.normal(0.0003, vol, n)))
                for d, p in zip(dates, prices):
                    rows.append({"timestamp": d, "country": "USA", "indicator_code": code, "value": p,
                                 "frequency": "D", "unit": "USD", "source": "test", "release_date": d, "ingested_at": d})
            self._df = pd.DataFrame(rows)

        def read_panel(self, codes, columns=None):
            out = self._df[self._df["indicator_code"].isin(codes)]
            return (out[columns] if columns else out).copy()

    codes = ["USA_APPLE", "USA_JOHNSON_JOHNSON", "USA_EXXONMOBIL", "USA_DUKE_ENERGY", "USA_WALMART", "USA_NIKE"]
    store = _FakeStore({c: v for c, v in zip(codes, [0.015, 0.008, 0.012, 0.006, 0.009, 0.011])})
    result = build_portfolio(store, countries=["USA"], sectors=None, risk_level="faible", min_names=3,
                              monte_carlo=True, mc_horizon_days=60, mc_n_sims=200)
    validated = PortfolioResponse(**result)  # lève si un champ manque ou a le mauvais type
    assert len(validated.holdings) >= 3
    assert validated.monte_carlo is not None
