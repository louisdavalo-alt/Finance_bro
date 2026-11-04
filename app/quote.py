"""Fiche de cotation et graphiques à la demande (tableau de bord). Alimente deux endpoints :

- `/quote/{code}` : résumé "à l'instant" (dernier cours, séance en cours...) — appel DIRECT et
  EN DIRECT à `yfinance` à chaque requête, jamais mis en cache ni stocké : une cotation figée
  serait trompeuse.
- `/chart/{code}` : barres de prix. Les plages intraday (1D/5D) et hebdomadaire (MAX) restent en
  appel direct, pour la même raison ou parce que leur granularité ne correspond pas à celle du
  cache. Les plages quotidiennes (1M/3M/1Y/5Y/YTD) sont servies par le cache OHLCV local partagé
  avec `/ohlc` et `/forecast` (voir `marketdata.py`/`ohlcv_cache.py`) quand il est fourni.

Ce que Yahoo permet de reproduire fidèlement : dernier cours, ouverture, plus haut / plus bas de
la séance (avec leur heure), volume, clôture de la veille, extrêmes sur 52 semaines,
capitalisation.

Ce qui est APPROXIMATIF (calculé ici à partir de barres de 5 minutes, pas de l'ensemble des
transactions) : le VWAP et les capitaux échangés.

Ce que Yahoo ne fournit pas du tout : nombre de transactions, seuils de réservation de cours,
clôture de valorisation — notions propres à Euronext, volontairement absentes de la réponse.

⚠️ Non testé en conditions réelles dans l'environnement de développement (Yahoo Finance bloqué
par son pare-feu) : le calcul est vérifié sur des données simulées (tests/test_api.py).
"""
from __future__ import annotations

import asyncio
import math

import pandas as pd

from .connectors.yfin import YFinanceNotInstalled, _fetch_history_sync
from .marketdata import get_daily_bars
from .ohlcv_cache import OhlcvCache

# Période affichée -> (période yfinance, intervalle yfinance)
RANGES: dict[str, tuple[str, str]] = {
    "1D": ("1d", "5m"),
    "5D": ("5d", "30m"),
    "1M": ("1mo", "1d"),
    "3M": ("3mo", "1d"),
    "1Y": ("1y", "1d"),
    "5Y": ("5y", "1d"),
    "YTD": ("ytd", "1d"),
    "MAX": ("max", "1wk"),
}
INTRADAY_RANGES = {"1D", "5D"}
# Plages à granularité quotidienne : servies par le cache OHLCV local (voir marketdata.py), au
# même titre que /ohlc et /forecast — leur `période` (côté yfinance) coïncide exactement avec les
# fenêtres que le cache sait trancher localement. MAX reste en appel direct : il utilise des
# barres HEBDOMADAIRES ("1wk"), une granularité différente de celle stockée dans le cache.
DAILY_CACHEABLE_RANGES = {"1M", "3M", "1Y", "5Y", "YTD"}
RANGE_PATTERN = "^(" + "|".join(RANGES) + ")$"


def _num(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) or math.isinf(v) else v


def frame_to_bars(df: pd.DataFrame, intraday: bool) -> list[dict]:
    """DataFrame yfinance -> liste de barres {date, open, high, low, close, volume}."""
    if df is None or df.empty:
        return []
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    fmt = "%Y-%m-%d %H:%M" if intraday else "%Y-%m-%d"
    out = []
    for ts, row in df.iterrows():
        out.append({
            "date": ts.strftime(fmt),
            "open": float(row["Open"]), "high": float(row["High"]),
            "low": float(row["Low"]), "close": float(row["Close"]),
            "volume": _num(row.get("Volume")),
        })
    return out


async def fetch_chart(symbol: str, range_key: str, cache: OhlcvCache | None = None) -> list[dict]:
    """Barres de la période demandée (intraday pour 1D/5D, quotidiennes/hebdomadaires sinon).
    Pour les plages quotidiennes (1M/3M/1Y/5Y/YTD), si `cache` est fourni, l'historique est servi
    par le cache OHLCV local — même forme de barre que `frame_to_bars`, donc remplacement direct."""
    period, interval = RANGES[range_key]
    if cache is not None and range_key in DAILY_CACHEABLE_RANGES:
        return await get_daily_bars(symbol, period, cache)
    df = await asyncio.to_thread(_fetch_history_sync, symbol, period, interval)
    return frame_to_bars(df, range_key in INTRADAY_RANGES)


def _summary_sync(symbol: str) -> dict | None:
    try:
        import yfinance as yf
    except ImportError as exc:  # pragma: no cover
        raise YFinanceNotInstalled("le paquet 'yfinance' n'est pas installé : `pip install yfinance`") from exc

    ticker = yf.Ticker(symbol)
    daily = ticker.history(period="1y", auto_adjust=False)
    # Un symbole inconnu de Yahoo Finance renvoie un DataFrame vide SANS colonnes — `dropna`
    # avec `subset=` lèverait alors `KeyError` plutôt que de signaler simplement "pas de donnée"
    # (voir /market-lookup, qui expose directement ce cas pour un symbole saisi librement, pas
    # seulement ceux déjà validés du catalogue).
    if daily is None or daily.empty:
        return None
    daily = daily.dropna(subset=["Open", "High", "Low", "Close"])
    if daily.empty:
        return None
    try:
        intra = ticker.history(period="1d", interval="5m", auto_adjust=False)
        intra = intra.dropna(subset=["Open", "High", "Low", "Close"]) if intra is not None else intra
    except Exception:  # l'intraday est un bonus : sans lui, on retombe sur la dernière barre quotidienne
        intra = None

    out: dict = {"intraday": bool(intra is not None and not intra.empty)}

    if out["intraday"]:
        last_ts = intra.index[-1]
        session_day = last_ts.date()
        vol = intra["Volume"].fillna(0)
        total_vol = float(vol.sum())
        hi_ts, lo_ts = intra["High"].idxmax(), intra["Low"].idxmin()
        out.update(
            last=float(intra["Close"].iloc[-1]),
            last_time=last_ts.strftime("%Y-%m-%d %H:%M"),
            open=float(intra["Open"].iloc[0]),
            high=float(intra["High"].max()), high_time=hi_ts.strftime("%H:%M"),
            low=float(intra["Low"].min()), low_time=lo_ts.strftime("%H:%M"),
            volume=total_vol,
            turnover=float((intra["Close"] * vol).sum()) if total_vol else None,
            vwap=float((((intra["High"] + intra["Low"] + intra["Close"]) / 3) * vol).sum() / total_vol) if total_vol else None,
        )
    else:
        last_row = daily.iloc[-1]
        session_day = daily.index[-1].date()
        out.update(
            last=float(last_row["Close"]), last_time=daily.index[-1].strftime("%Y-%m-%d"),
            open=float(last_row["Open"]),
            high=float(last_row["High"]), high_time=None,
            low=float(last_row["Low"]), low_time=None,
            volume=_num(last_row.get("Volume")), turnover=None, vwap=None,
        )

    before = daily[[d.date() < session_day for d in daily.index]]
    prev = float(before["Close"].iloc[-1]) if not before.empty else None
    out["previous_close"] = prev
    out["change"] = (out["last"] - prev) if prev is not None else None
    out["change_pct"] = ((out["last"] - prev) / prev * 100) if prev else None

    cutoff = daily.index[-1] - pd.Timedelta(days=365)
    window = daily[daily.index >= cutoff]
    out["week52_high"] = float(window["High"].max())
    out["week52_low"] = float(window["Low"].min())

    market_cap, currency = None, None
    try:
        fi = ticker.fast_info
        market_cap = _num(getattr(fi, "market_cap", None))
        currency = getattr(fi, "currency", None)
    except Exception:
        pass
    out["market_cap"] = market_cap
    out["currency"] = currency
    return out


async def fetch_quote_summary(symbol: str) -> dict | None:
    """Résumé de cotation, ou None si Yahoo ne renvoie aucune donnée pour ce ticker."""
    return await asyncio.to_thread(_summary_sync, symbol)


def _name_sync(symbol: str) -> str | None:
    """Nom lisible d'un symbole (ex. "Apple Inc."), au prix d'un appel Yahoo plus complet
    (`get_info()`) que `_summary_sync` — utilisé seulement pour l'ajout d'un ticker hors
    catalogue (`POST /market-activate`) quand le nom n'est pas déjà connu (ex. via
    `/market-search`), jamais sur le chemin `/quote` habituel pour ne pas le ralentir."""
    try:
        import yfinance as yf
    except ImportError:  # pragma: no cover - dépend de l'environnement d'exécution
        return None
    try:
        info = yf.Ticker(symbol).get_info()
    except Exception:  # noqa: BLE001 - best-effort, un nom manquant n'est pas bloquant
        return None
    return info.get("longName") or info.get("shortName")


async def fetch_symbol_name(symbol: str) -> str | None:
    return await asyncio.to_thread(_name_sync, symbol)
