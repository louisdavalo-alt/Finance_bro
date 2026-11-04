"""Yahoo Finance (bibliothèque `yfinance`) — données de MARCHÉ, pas des statistiques d'État.

⚠️ Ceci n'est PAS un substitut aux séries macro officielles (indice de production, inflation,
balance commerciale...) : Yahoo Finance ne publie aucune statistique gouvernementale. Cette
source sert à compléter le catalogue avec des indicateurs de marché — indices boursiers, taux de
change — qui ont leur propre valeur informative pour un usage de trading/analyse, sans prétendre
remplacer un indice officiel.

`yfinance` n'est pas une API officielle : Yahoo a fermé la sienne en 2017. La bibliothèque imite
l'empreinte TLS d'un navigateur (Chrome, via `curl_cffi`) pour accéder aux points d'accès internes
du site — sans clé, mais aussi sans garantie de stabilité : Yahoo peut changer ses pages ou
bloquer un pattern de requêtes à tout moment. Contrairement aux autres connecteurs de ce projet
(qui appellent une API HTTP directement), celui-ci délègue tout le réseau et l'authentification
(cookies, jeton "crumb") à la bibliothèque elle-même via `yfinance.Ticker(...).history(...)`,
appelée dans un thread séparé (`asyncio.to_thread`) puisqu'elle est synchrone.

`params` attendus dans l'IndicatorSpec :
    symbol : ticker Yahoo Finance, ex. "^GDAXI" (indice DAX), "EURUSD=X" (taux de change)
    field  : colonne à extraire du DataFrame renvoyé par `Ticker.history()`, par défaut "Close"
    period : fenêtre historique, ex. "max", "10y" (par défaut "max")

Exemples de tickers utiles (à adapter/étendre selon les besoins) :
    Indices actions   : ^GSPC (S&P 500), ^GDAXI (DAX), ^FCHI (CAC 40), ^N225 (Nikkei 225),
                        ^HSI (Hang Seng), ^BSESN (Sensex)
    Taux de change    : EURUSD=X, USDJPY=X, USDCNY=X, USDINR=X
    Rendements souverains US (proxy) : ^TNX (10 ans, en points de %, à diviser par 10)
"""
from __future__ import annotations

import asyncio
import logging

import pandas as pd

from .base import Connector, IndicatorSpec
from ..schema import build_frame

log = logging.getLogger("connectors.yfin")


class YFinanceNotInstalled(ImportError):
    pass


def _fetch_history_sync(
    symbol: str,
    period: str | None = None,
    interval: str | None = None,
    start=None,
) -> pd.DataFrame:
    """Fonction synchrone, exécutée dans un thread (yfinance ne fournit pas d'API async).
    `interval` (ex. "5m", "30m", "1wk") n'est transmis à yfinance que s'il est fourni : le
    comportement historique (barres quotidiennes) reste donc strictement inchangé.

    `start` (une `datetime.date`, ou tout ce que yfinance accepte pour ce paramètre) remplace
    `period` quand il est fourni — utilisé par `marketdata.py` pour ne redemander que les jours
    manquants depuis la dernière barre déjà en cache, au lieu de retélécharger tout l'historique.
    Au moins l'un des deux doit être fourni."""
    try:
        import yfinance as yf
    except ImportError as exc:  # pragma: no cover - dépend de l'environnement d'exécution
        raise YFinanceNotInstalled(
            "le paquet 'yfinance' n'est pas installé : `pip install yfinance`"
        ) from exc
    kwargs = {"auto_adjust": False}
    if start is not None:
        kwargs["start"] = start
    elif period:
        kwargs["period"] = period
    else:
        raise ValueError("_fetch_history_sync: 'period' ou 'start' doit être fourni")
    if interval:
        kwargs["interval"] = interval
    return yf.Ticker(symbol).history(**kwargs)


class YFinanceConnector(Connector):
    name = "yfinance"

    def cache_key(self, spec: IndicatorSpec) -> str:
        return spec.code

    async def fetch_raw(self, spec: IndicatorSpec) -> dict:
        # Pas d'appel HTTP via ApiClient ici : yfinance gère son propre client réseau
        # (curl_cffi). On respecte quand même le seau à jetons de la source, par cohérence
        # avec les autres connecteurs et pour éviter d'enchaîner les appels trop vite.
        bucket = self.client.rate_limiter(self.client.settings.source("yfinance"))
        await bucket.acquire()

        symbol = spec.params["symbol"]
        period = spec.params.get("period", "max")
        df = await asyncio.to_thread(_fetch_history_sync, symbol, period)
        if df.empty:
            return {"dates": [], "values": []}
        field = spec.params.get("field", "Close")
        if field not in df.columns:
            raise KeyError(f"colonne {field!r} absente de l'historique {symbol} (colonnes : {list(df.columns)})")
        series = df[field].dropna()
        return {"dates": [d.strftime("%Y-%m-%d") for d in series.index], "values": series.tolist()}

    def normalize(self, raw: dict, spec: IndicatorSpec) -> pd.DataFrame:
        if not raw.get("dates"):
            return build_frame(timestamp=[], country=spec.country, indicator_code=spec.code, value=[], frequency=spec.frequency, unit=spec.unit, source=self.name)
        return build_frame(
            timestamp=raw["dates"],
            country=spec.country,
            indicator_code=spec.code,
            value=raw["values"],
            frequency=spec.frequency,
            unit=spec.unit,
            source=self.name,
            # Cours de bourse : connu le jour même (marché déjà clos à la clôture).
            publication_lag_days=spec.publication_lag_days,
        )
