"""Schéma unifié de toutes les séries, quelle que soit la source.

Colonnes obligatoires (demandées) : timestamp, country, indicator_code, value, frequency, unit
Colonnes ajoutées, nécessaires pour l'alignement sans biais de look-ahead et la traçabilité :
    source          - connecteur d'origine (fred, ecb, imf, estat, boj, worldbank, nbs_china, manual, yfinance)
    release_date    - date à laquelle la donnée était réellement connue/publiée (peut être postérieure à `timestamp`)
    ingested_at     - horodatage de la collecte par ce pipeline
"""
from __future__ import annotations

import datetime as dt
from typing import Iterable

import pandas as pd

COLUMNS = [
    "timestamp",
    "country",
    "indicator_code",
    "value",
    "frequency",
    "unit",
    "source",
    "release_date",
    "ingested_at",
]

VALID_FREQUENCIES = {"D", "W", "M", "Q", "A"}

DTYPES = {
    "timestamp": "datetime64[ns]",
    "country": "string",
    "indicator_code": "string",
    "value": "float64",
    "frequency": "string",
    "unit": "string",
    "source": "string",
    "release_date": "datetime64[ns]",
    "ingested_at": "datetime64[ns]",
}


class SchemaError(ValueError):
    pass


def empty_frame() -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype=DTYPES[c]) for c in COLUMNS})


def build_frame(
    *,
    timestamp: Iterable,
    country: str,
    indicator_code: str,
    value: Iterable,
    frequency: str,
    unit: str,
    source: str,
    release_date: Iterable | None = None,
    publication_lag_days: int = 0,
) -> pd.DataFrame:
    """Construit un DataFrame conforme au schéma à partir de séries parallèles.

    Si `release_date` n'est pas fourni par la source (le cas le plus fréquent), il est
    estimé comme `timestamp + publication_lag_days` : c'est cette date estimée qui sera
    utilisée par `resample.align_panel` pour ne jamais exposer une valeur avant qu'elle
    n'ait été réellement publiable, et donc éviter le biais de look-ahead.
    """
    if frequency not in VALID_FREQUENCIES:
        raise SchemaError(f"fréquence inconnue : {frequency!r} (attendu parmi {sorted(VALID_FREQUENCIES)})")

    ts = pd.to_datetime(pd.Series(list(timestamp)))
    val = pd.Series(list(value), dtype="float64")
    if len(ts) != len(val):
        raise SchemaError(f"timestamp ({len(ts)}) et value ({len(val)}) de longueurs différentes")

    if release_date is not None:
        rel = pd.to_datetime(pd.Series(list(release_date)))
        if len(rel) != len(ts):
            raise SchemaError("release_date de longueur différente de timestamp")
    else:
        rel = ts + pd.Timedelta(days=publication_lag_days)

    now = pd.Timestamp(dt.datetime.now(dt.timezone.utc)).tz_localize(None)
    df = pd.DataFrame(
        {
            "timestamp": ts,
            "country": country,
            "indicator_code": indicator_code,
            "value": val,
            "frequency": frequency,
            "unit": unit,
            "source": source,
            "release_date": rel,
            "ingested_at": now,
        }
    )
    return validate(df)


def validate(df: pd.DataFrame) -> pd.DataFrame:
    missing = set(COLUMNS) - set(df.columns)
    if missing:
        raise SchemaError(f"colonnes manquantes : {sorted(missing)}")
    df = df[COLUMNS].copy()

    bad_freq = set(df["frequency"].unique()) - VALID_FREQUENCIES
    if bad_freq:
        raise SchemaError(f"fréquences invalides : {bad_freq}")

    if df["value"].isna().all() and len(df):
        raise SchemaError("toutes les valeurs sont NaN")

    for col in ("timestamp", "release_date", "ingested_at"):
        df[col] = pd.to_datetime(df[col])
    for col in ("country", "indicator_code", "frequency", "unit", "source"):
        df[col] = df[col].astype("string")

    df = df.dropna(subset=["timestamp", "value"])
    df = df.sort_values(["indicator_code", "timestamp"]).reset_index(drop=True)
    return df


def concat(frames: Iterable[pd.DataFrame]) -> pd.DataFrame:
    frames = [f for f in frames if f is not None and len(f)]
    if not frames:
        return empty_frame()
    df = pd.concat(frames, ignore_index=True)
    df = df.drop_duplicates(subset=["source", "country", "indicator_code", "timestamp"], keep="last")
    return validate(df)
