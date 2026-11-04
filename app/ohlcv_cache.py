"""Cache local des barres OHLCV quotidiennes (Open/High/Low/Close/Volume), par symbole.

Voir `marketdata.py` pour la logique de récupération incrémentale qui alimente ce cache : au lieu
de redemander tout l'historique à Yahoo Finance à chaque ouverture d'un graphique, on ne
redemande que les jours manquants depuis la dernière barre déjà connue.

Fichier DuckDB séparé de `data/macro.duckdb` (voir `cache.py`) : celui-ci est écrit directement
par le processus API, à la demande, jamais par le pipeline cron — rien d'autre n'ouvre ce
fichier, donc pas de risque du conflit de verrou DuckDB déjà résolu ailleurs entre pipeline et
API (`Store` vs `ParquetReader`).
"""
from __future__ import annotations

import datetime as dt
import threading
from pathlib import Path

import duckdb
import pandas as pd


class OhlcvCache:
    """Une connexion DuckDB n'est pas sûre entre threads (le processus API tourne dans un
    threadpool) : `self._lock` protège donc chaque appel, comme dans `cache.Store`."""

    def __init__(self, data_dir: Path):
        data_dir = Path(data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = data_dir / "ohlcv_cache.duckdb"
        self._lock = threading.RLock()
        # Synchronisation incrémentale avec Yahoo (voir marketdata.py) : un verrou par symbole
        # (deux vues ouvertes en même temps ne téléchargent pas deux fois le même historique) et
        # l'heure de la dernière synchronisation, pour ne pas réinterroger Yahoo à chaque appel
        # quand la dernière barre reste antérieure à aujourd'hui (week-end, jour férié, avant
        # l'ouverture) — cas où l'ancien test « last >= today » ne court-circuitait jamais.
        self.sync_guard = threading.Lock()
        self.sync_locks: dict[str, threading.Lock] = {}
        self.last_sync: dict[str, float] = {}
        self._con = duckdb.connect(str(self.db_path))
        with self._lock:
            self._con.execute(
                """
                CREATE TABLE IF NOT EXISTS bars (
                    symbol TEXT NOT NULL,
                    date DATE NOT NULL,
                    open DOUBLE,
                    high DOUBLE,
                    low DOUBLE,
                    close DOUBLE,
                    volume DOUBLE,
                    PRIMARY KEY (symbol, date)
                )
                """
            )
            # Tickers ajoutés à la volée par un utilisateur (recherche libre, hors du catalogue
            # déclaratif de `registry.py`) qui a choisi de les "ajouter à la bibliothèque active"
            # plutôt que de juste les observer — voir `POST /market-activate` dans `api.py`. Même
            # fichier que `bars` : écrit uniquement par le processus API, jamais par le pipeline
            # cron, donc aucun risque de conflit de verrou DuckDB (voir l'en-tête du module).
            self._con.execute(
                """
                CREATE TABLE IF NOT EXISTS custom_indicators (
                    code TEXT PRIMARY KEY,
                    country TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    name TEXT,
                    unit TEXT,
                    added_at TIMESTAMP NOT NULL
                )
                """
            )

    def last_date(self, symbol: str) -> dt.date | None:
        """Dernière date déjà en cache pour `symbol`, ou `None` si rien n'est encore connu."""
        with self._lock:
            row = self._con.execute(
                "SELECT max(date) FROM bars WHERE symbol = ?", [symbol]
            ).fetchone()
        return row[0] if row and row[0] is not None else None

    def upsert(self, symbol: str, bars: pd.DataFrame) -> None:
        """`bars` : colonnes (date, open, high, low, close, volume), `date` en `datetime.date`.
        Une barre déjà présente (ex. la dernière séance, re-téléchargée pour capter une mise à
        jour tardive) est remplacée, jamais dupliquée."""
        if bars.empty:
            return
        payload = bars.assign(symbol=symbol)[
            ["symbol", "date", "open", "high", "low", "close", "volume"]
        ]
        with self._lock:
            self._con.register("ohlcv_cache_upsert_df", payload)
            try:
                self._con.execute(
                    """
                    INSERT INTO bars SELECT * FROM ohlcv_cache_upsert_df
                    ON CONFLICT (symbol, date) DO UPDATE SET
                        open = excluded.open,
                        high = excluded.high,
                        low = excluded.low,
                        close = excluded.close,
                        volume = excluded.volume
                    """
                )
            finally:
                self._con.unregister("ohlcv_cache_upsert_df")

    def read(self, symbol: str, start: dt.date | None = None, end: dt.date | None = None) -> list[dict]:
        """Barres `{date, open, high, low, close, volume}` triées du plus ancien au plus
        récent, `date` au format ISO (`YYYY-MM-DD`). `end` (inclus) est la borne « point-in-time » :
        une date de marché est connue le jour même (pas de délai de publication à gérer ici, à la
        différence des séries macro de `cache.Store`/`release_date`), donc `date <= end` suffit à
        garantir qu'aucune barre future ne fuite dans un calcul fait « comme si on était à `end` »
        (voir `app/forecast/feature_store.py`, qui est le seul appelant prévu pour `end` — les
        usages existants, affichage de graphique, ne passent jamais cet argument)."""
        clauses = ["symbol = ?"]
        params: list = [symbol]
        if start is not None:
            clauses.append("date >= ?")
            params.append(start)
        if end is not None:
            clauses.append("date <= ?")
            params.append(end)
        with self._lock:
            rows = self._con.execute(
                f"SELECT date, open, high, low, close, volume FROM bars "
                f"WHERE {' AND '.join(clauses)} ORDER BY date",
                params,
            ).fetchall()
        return [
            {
                "date": d.isoformat(),
                "open": o,
                "high": h,
                "low": low,
                "close": c,
                "volume": v,
            }
            for d, o, h, low, c, v in rows
        ]

    def stats(self, symbols: list[str]) -> dict[str, tuple[int, str | None]]:
        """`{symbol: (nombre de barres, dernière date ISO)}` en UNE requête agrégée — `/indicators`
        lisait auparavant l'historique complet de chaque ticker ajouté juste pour le compter."""
        if not symbols:
            return {}
        with self._lock:
            rows = self._con.execute(
                "SELECT symbol, count(*), max(date) FROM bars WHERE symbol IN (SELECT unnest(?)) GROUP BY symbol",
                [list(symbols)],
            ).fetchall()
        return {s: (int(n), d.isoformat() if d is not None else None) for s, n, d in rows}

    # ------------------------------------------------------------------ #
    # Tickers ajoutés à la volée ("bibliothèque active" — voir docstring du module)
    # ------------------------------------------------------------------ #
    def add_custom(self, code: str, country: str, symbol: str, name: str | None, unit: str | None) -> None:
        with self._lock:
            self._con.execute(
                """
                INSERT INTO custom_indicators VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (code) DO UPDATE SET
                    country = excluded.country, symbol = excluded.symbol,
                    name = excluded.name, unit = excluded.unit
                """,
                [code, country, symbol, name, unit, dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)],
            )

    def list_custom(self) -> list[dict]:
        """Tous les tickers ajoutés à la volée, pour reconstruire l'index en mémoire de l'API au
        démarrage (voir `lifespan()` dans `api.py`) — le cache des barres (`bars`) survit déjà au
        redémarrage, seule la déclaration (code -> symbole) doit être rechargée."""
        with self._lock:
            rows = self._con.execute(
                "SELECT code, country, symbol, name, unit FROM custom_indicators ORDER BY added_at"
            ).fetchall()
        return [{"code": c, "country": co, "symbol": s, "name": n, "unit": u} for c, co, s, n, u in rows]

    def close(self) -> None:
        with self._lock:
            self._con.close()
