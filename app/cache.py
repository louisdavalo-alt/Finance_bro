"""Cache local et entrepôt de séries, sur DuckDB (aucun serveur à administrer).

Deux classes, deux rôles :

- `Store` (pipeline, ÉCRITURE) — fichier `data/macro.duckdb`, deux tables :
  - `raw_cache`   : réponse brute par (source, clé de requête), avec expiration (TTL) par fréquence.
  - `observations`: le schéma unifié (voir schema.py), avec upsert idempotent.
  Après chaque upsert, les séries MODIFIÉES sont exportées en Parquet (`data/parquet/<code>.parquet`),
  de façon ATOMIQUE (écriture dans un fichier temporaire puis `os.replace`).

- `ParquetReader` (API, LECTURE SEULE) — lit uniquement ces exports Parquet, via une base DuckDB
  EN MÉMOIRE. L'API n'ouvre donc plus jamais `macro.duckdb` : c'est ce qui supprime le « piège du
  verrou DuckDB » (README, section 6) — le pipeline planifié par cron peut écrire pendant que
  l'API tourne, sans `Conflicting lock is held`. Grâce à l'écriture atomique, l'API voit toujours
  soit l'ancienne version complète d'une série, soit la nouvelle, jamais un fichier à moitié écrit.

DuckDB suffit largement pour un usage personnel. Si le pipeline tourne un jour sur plusieurs
machines en parallèle, remplacer `raw_cache` par Redis (mêmes clés, TTL natif) sans toucher
au reste du code : c'est la seule classe qui référence le stockage brut.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import tempfile
import threading
from pathlib import Path

import duckdb
import pandas as pd

from .schema import COLUMNS, empty_frame

# Un code d'indicateur sert de nom de fichier Parquet : on refuse tout ce qui pourrait sortir du
# répertoire (`/`, `..`) ou poser problème sur un système de fichiers.
SAFE_CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,99}$")
_SELECT_COLUMNS = ", ".join(COLUMNS)


def is_safe_code(code: str) -> bool:
    return bool(SAFE_CODE_RE.match(code)) and ".." not in code


def parquet_path(parquet_dir: Path, code: str) -> Path:
    if not is_safe_code(code):
        raise ValueError(f"code d'indicateur invalide pour un nom de fichier : {code!r}")
    return parquet_dir / f"{code}.parquet"


def _select_list(columns: list[str] | None) -> str:
    if not columns:
        return _SELECT_COLUMNS
    unknown = set(columns) - set(COLUMNS)
    if unknown:
        raise ValueError(f"colonnes inconnues : {sorted(unknown)}")
    return ", ".join(columns)


def _sql_str(value: str) -> str:
    """Littéral SQL pour un chemin de fichier (COPY n'accepte pas de paramètre pour la cible)."""
    return str(value).replace("'", "''")


class Store:
    def __init__(self, data_dir: Path):
        data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = data_dir / "macro.duckdb"
        self.parquet_dir = data_dir / "parquet"
        self.parquet_dir.mkdir(parents=True, exist_ok=True)
        self._con = duckdb.connect(str(self.db_path))
        self._lock = threading.RLock()  # une connexion DuckDB n'est pas sûre entre threads
        self._init_schema()

    def _init_schema(self) -> None:
        self._con.execute(
            """
            CREATE TABLE IF NOT EXISTS raw_cache (
                source TEXT, cache_key TEXT, fetched_at TIMESTAMP, expires_at TIMESTAMP, payload TEXT,
                PRIMARY KEY (source, cache_key)
            )
            """
        )
        self._con.execute(
            """
            CREATE TABLE IF NOT EXISTS observations (
                timestamp TIMESTAMP, country TEXT, indicator_code TEXT, value DOUBLE,
                frequency TEXT, unit TEXT, source TEXT, release_date TIMESTAMP, ingested_at TIMESTAMP,
                PRIMARY KEY (source, country, indicator_code, timestamp)
            )
            """
        )

    # ------------------------------------------------------------------ #
    # Cache brut
    # ------------------------------------------------------------------ #
    def cache_get(self, source: str, cache_key: str) -> dict | list | None:
        with self._lock:
            row = self._con.execute(
                "SELECT payload FROM raw_cache WHERE source = ? AND cache_key = ? AND expires_at > ?",
                [source, cache_key, dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)],
            ).fetchone()
        return json.loads(row[0]) if row else None

    def cache_set(self, source: str, cache_key: str, payload, ttl_seconds: int) -> None:
        now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        expires = now + dt.timedelta(seconds=ttl_seconds)
        with self._lock:
            self._con.execute(
                "INSERT OR REPLACE INTO raw_cache VALUES (?,?,?,?,?)",
                [source, cache_key, now, expires, json.dumps(payload, default=str)],
            )

    def purge_expired_cache(self) -> int:
        """Supprime les entrées de cache expirées (appelé en fin de pipeline)."""
        now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        with self._lock:
            n = self._con.execute("SELECT count(*) FROM raw_cache WHERE expires_at <= ?", [now]).fetchone()[0]
            if n:
                self._con.execute("DELETE FROM raw_cache WHERE expires_at <= ?", [now])
        return int(n)

    # ------------------------------------------------------------------ #
    # Observations normalisées
    # ------------------------------------------------------------------ #
    def upsert_observations(self, df: pd.DataFrame) -> int:
        """Upsert idempotent, puis export Parquet des seules séries qui ont réellement changé
        (valeur, date de publication ou unité modifiée, nouvelle observation) ou dont l'export
        Parquet manque. Avant : chaque exécution horaire ré-écrivait les ~700 fichiers Parquet,
        même quand toutes les réponses venaient du cache et que rien n'avait bougé."""
        if df.empty:
            return 0
        new = df[COLUMNS]
        with self._lock:
            self._con.register("df_new", new)
            try:
                changed = {
                    r[0]
                    for r in self._con.execute(
                        """
                        SELECT DISTINCT n.indicator_code
                        FROM df_new n
                        LEFT JOIN observations o
                          ON o.source = n.source AND o.country = n.country
                         AND o.indicator_code = n.indicator_code AND o.timestamp = n.timestamp
                        WHERE o.indicator_code IS NULL
                           OR o.value IS DISTINCT FROM n.value
                           OR o.release_date IS DISTINCT FROM n.release_date
                           OR o.unit IS DISTINCT FROM n.unit
                        """
                    ).fetchall()
                }
                self._con.execute(
                    f"""
                    INSERT INTO observations
                    SELECT {_SELECT_COLUMNS} FROM df_new
                    ON CONFLICT (source, country, indicator_code, timestamp)
                    DO UPDATE SET value = excluded.value, release_date = excluded.release_date,
                                  ingested_at = excluded.ingested_at, unit = excluded.unit
                    """
                )
            finally:
                self._con.unregister("df_new")

        all_codes = {str(c) for c in new["indicator_code"].unique()}
        missing = {c for c in all_codes if is_safe_code(c) and not parquet_path(self.parquet_dir, c).is_file()}
        self._write_parquet(sorted(changed | missing))
        return len(df)

    def _write_parquet(self, codes: list[str]) -> None:
        """Un fichier par code, ré-écrit à partir de l'état complet en base (source de vérité =
        DuckDB, Parquet = export). Écrit directement par DuckDB (`COPY ... TO`), sans aller-retour
        par pandas, dans un fichier temporaire renommé ensuite (`os.replace`, atomique)."""
        for code in codes:
            if not is_safe_code(code):
                continue
            final = parquet_path(self.parquet_dir, code)
            fd, tmp = tempfile.mkstemp(prefix=f".{code}.", suffix=".tmp", dir=self.parquet_dir)
            os.close(fd)
            try:
                with self._lock:
                    self._con.execute(
                        f"COPY (SELECT {_SELECT_COLUMNS} FROM observations WHERE indicator_code = ? ORDER BY timestamp) "
                        f"TO '{_sql_str(tmp)}' (FORMAT parquet)",
                        [code],
                    )
                os.replace(tmp, final)
            except BaseException:
                try:
                    os.unlink(tmp)
                except FileNotFoundError:
                    pass
                raise

    def export_all_parquet(self) -> int:
        """Ré-exporte toutes les séries en base (utile après une restauration de `macro.duckdb`)."""
        with self._lock:
            codes = [r[0] for r in self._con.execute("SELECT DISTINCT indicator_code FROM observations").fetchall()]
        self._write_parquet(codes)
        return len(codes)

    def read_series(self, indicator_code: str) -> pd.DataFrame:
        with self._lock:
            return self._con.execute(
                f"SELECT {_SELECT_COLUMNS} FROM observations WHERE indicator_code = ? ORDER BY timestamp", [indicator_code]
            ).fetchdf()

    def read_panel(self, indicator_codes: list[str] | None = None, columns: list[str] | None = None) -> pd.DataFrame:
        """`columns` : sous-ensemble de colonnes à lire (par défaut toutes) — le portefeuille n'a
        besoin que de (timestamp, indicator_code, value), inutile de charger le reste."""
        select = _select_list(columns)
        with self._lock:
            if indicator_codes:
                return self._con.execute(
                    f"SELECT {select} FROM observations WHERE indicator_code IN (SELECT unnest(?)) "
                    "ORDER BY indicator_code, timestamp",
                    [list(indicator_codes)],
                ).fetchdf()
            return self._con.execute(f"SELECT {select} FROM observations ORDER BY indicator_code, timestamp").fetchdf()

    def list_indicators(self) -> pd.DataFrame:
        with self._lock:
            return self._con.execute(
                """
                SELECT indicator_code, country, source, frequency, unit,
                       count(*) AS n_obs, max(timestamp) AS last_timestamp, max(ingested_at) AS last_ingested
                FROM observations GROUP BY 1,2,3,4,5 ORDER BY 1
                """
            ).fetchdf()

    def close(self) -> None:
        with self._lock:
            self._con.close()


class ParquetReader:
    """Lecture seule des exports Parquet, pour l'API — même interface de lecture que `Store`
    (`read_series`, `read_panel`, `list_indicators`), sans jamais toucher au fichier DuckDB du
    pipeline. Sûr entre threads : un curseur DuckDB par thread (une connexion DuckDB unique
    n'est pas utilisable simultanément depuis plusieurs threads, or FastAPI exécute les
    endpoints synchrones dans un pool de threads).

    Les agrégats sur l'ensemble du catalogue (`list_indicators`, `lag_report`) sont mis en cache
    et invalidés dès que le contenu du répertoire change (mtime du répertoire, modifié par chaque
    `os.replace` du pipeline)."""

    def __init__(self, data_dir: Path):
        self.parquet_dir = Path(data_dir) / "parquet"
        self.parquet_dir.mkdir(parents=True, exist_ok=True)
        self._con = duckdb.connect(":memory:")
        self._local = threading.local()
        self._cursor_lock = threading.Lock()
        self._agg_cache: dict[str, tuple[int, pd.DataFrame]] = {}
        self._agg_lock = threading.Lock()

    def _cur(self) -> duckdb.DuckDBPyConnection:
        cur = getattr(self._local, "cur", None)
        if cur is None:
            with self._cursor_lock:
                cur = self._con.cursor()
            self._local.cur = cur
        return cur

    def _version(self) -> int:
        try:
            return self.parquet_dir.stat().st_mtime_ns
        except FileNotFoundError:
            return 0

    def _files(self, codes: list[str] | None) -> list[str]:
        if codes is None:
            return sorted(str(p) for p in self.parquet_dir.glob("*.parquet"))
        out = []
        for code in dict.fromkeys(codes):  # dédoublonne en gardant l'ordre
            if not is_safe_code(code):
                continue
            path = parquet_path(self.parquet_dir, code)
            if path.is_file():
                out.append(str(path))
        return out

    def _query(self, sql_tail: str, files: list[str], select: str = _SELECT_COLUMNS) -> pd.DataFrame | None:
        if not files:
            return None
        try:
            return self._cur().execute(
                f"SELECT {select} FROM read_parquet(?, union_by_name = true) {sql_tail}", [files]
            ).fetchdf()
        except duckdb.IOException:
            # Fichier remplacé/supprimé entre le listage et la lecture : une seconde tentative suffit.
            files = [f for f in files if os.path.exists(f)]
            if not files:
                return None
            return self._cur().execute(
                f"SELECT {select} FROM read_parquet(?, union_by_name = true) {sql_tail}", [files]
            ).fetchdf()

    def read_series(self, indicator_code: str) -> pd.DataFrame:
        df = self._query("ORDER BY timestamp", self._files([indicator_code]))
        return df if df is not None else empty_frame()

    def read_series_records(self, indicator_code: str) -> list[dict]:
        """Série prête à sérialiser en JSON (dates en texte), construite directement par DuckDB —
        évite la conversion pandas (`astype(str)` + `to_dict`) qui dominait le temps de `/series`."""
        files = self._files([indicator_code])
        if not files:
            return []
        select = ", ".join(
            f"CAST({c} AS VARCHAR) AS {c}" if c in ("timestamp", "release_date", "ingested_at") else c for c in COLUMNS
        )
        rows = self._cur().execute(f"SELECT {select} FROM read_parquet(?, union_by_name = true) ORDER BY timestamp", [files]).fetchall()
        # Même rendu que l'ancien `astype(str)` de pandas : une colonne dont TOUTES les valeurs
        # tombent à minuit s'affiche en date seule ("2024-01-01"), sinon en date + heure.
        cols = list(zip(*rows)) if rows else [[] for _ in COLUMNS]
        cols = [list(c) for c in cols]
        for i, name in enumerate(COLUMNS):
            if name in ("timestamp", "release_date", "ingested_at"):
                vals = cols[i]
                if all(v is None or v.endswith(" 00:00:00") for v in vals):
                    cols[i] = [None if v is None else v[:-9] for v in vals]
        return [dict(zip(COLUMNS, row)) for row in zip(*cols)]

    def read_panel(self, indicator_codes: list[str] | None = None, columns: list[str] | None = None) -> pd.DataFrame:
        df = self._query(
            "ORDER BY indicator_code, timestamp",
            self._files(list(indicator_codes) if indicator_codes else None),
            select=_select_list(columns),
        )
        if df is None:
            empty = empty_frame()
            return empty[columns] if columns else empty
        return df

    def _cached_aggregate(self, name: str, compute) -> pd.DataFrame:
        version = self._version()
        with self._agg_lock:
            hit = self._agg_cache.get(name)
            if hit is not None and hit[0] == version:
                return hit[1]
        result = compute()
        with self._agg_lock:
            self._agg_cache[name] = (version, result)
        return result

    def list_indicators(self) -> pd.DataFrame:
        def compute():
            df = self._query(
                "GROUP BY 1,2,3,4,5 ORDER BY 1",
                self._files(None),
                select="indicator_code, country, source, frequency, unit, count(*) AS n_obs, "
                       "max(timestamp) AS last_timestamp, max(ingested_at) AS last_ingested",
            )
            if df is None:
                return pd.DataFrame(columns=["indicator_code", "country", "source", "frequency", "unit", "n_obs", "last_timestamp", "last_ingested"])
            return df
        return self._cached_aggregate("list_indicators", compute)

    def lag_report(self) -> pd.DataFrame:
        """Équivalent SQL de `resample.publication_lag_report`, sans charger toute la base en
        mémoire (l'ancien endpoint lisait l'intégralité des observations dans pandas à chaque appel)."""
        def compute():
            df = self._query(
                "GROUP BY 1 ORDER BY 1",
                self._files(None),
                select="indicator_code, median(date_diff('day', timestamp, release_date))::DOUBLE AS median_lag_days, "
                       "count(*) AS n_obs",
            )
            if df is None:
                return pd.DataFrame(columns=["indicator_code", "median_lag_days", "n_obs"])
            return df
        return self._cached_aggregate("lag_report", compute)

    def close(self) -> None:
        self._con.close()
