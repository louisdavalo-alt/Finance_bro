"""Recherche libre de tickers auprès de Yahoo Finance — pour trouver une action qui n'est PAS
dans le catalogue déclaratif de `registry.py` (voir `POST /market-search` et `/market-lookup` dans
`api.py`). Contrairement aux autres fonctions de ce projet qui appellent `yfinance.Ticker(...)`,
celle-ci utilise `yfinance.Search(...)`, qui interroge le même point d'accès que la barre de
recherche du site Yahoo Finance (`/v1/finance/search`) — aucune garantie de stabilité, comme pour
le reste de `yfinance` (voir `connectors/yfin.py`).
"""
from __future__ import annotations

import asyncio

from .connectors.yfin import YFinanceNotInstalled


def _search_sync(query: str, max_results: int) -> list[dict]:
    try:
        import yfinance as yf
    except ImportError as exc:  # pragma: no cover - dépend de l'environnement d'exécution
        raise YFinanceNotInstalled("le paquet 'yfinance' n'est pas installé : `pip install yfinance`") from exc

    result = yf.Search(query, max_results=max_results, news_count=0, lists_count=0, include_cb=False)
    out = []
    for q in result.quotes:
        symbol = q.get("symbol")
        if not symbol:
            continue
        out.append(
            {
                "symbol": symbol,
                "name": q.get("shortname") or q.get("longname") or symbol,
                "exchange": q.get("exchange") or q.get("exchDisp"),
                "type": q.get("quoteType") or q.get("typeDisp"),
            }
        )
    return out


async def search_symbols(query: str, max_results: int = 8) -> list[dict]:
    return await asyncio.to_thread(_search_sync, query, max_results)
