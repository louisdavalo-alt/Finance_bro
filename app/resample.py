"""Alignement temporel des séries pour en faire des features de ML/DL.

Le point délicat n'est pas le resampling en lui-même (pandas le fait très bien), mais le
**biais de look-ahead** : une observation datée "janvier 2026" pour le CPI américain n'est
en réalité connue que mi-février. Si on aligne naïvement sur `timestamp`, un modèle entraîné
sur données historiques "voit" une information qu'il n'aurait pas pu avoir en temps réel.

La fonction `align_panel` répond à ça avec un `merge_asof` sur `release_date` : à la date T du
panneau, seules les observations dont `release_date <= T` sont utilisées, quelle que soit la
période qu'elles décrivent.
"""
from __future__ import annotations

import pandas as pd

_FREQ_TO_PANDAS = {"D": "D", "W": "W", "M": "MS", "Q": "QS", "A": "AS"}


def make_calendar(start: str, end: str, freq: str) -> pd.DatetimeIndex:
    return pd.date_range(start=start, end=end, freq=_FREQ_TO_PANDAS[freq])


def align_panel(df: pd.DataFrame, *, target_freq: str, start: str | None = None, end: str | None = None) -> pd.DataFrame:
    """Construit un panneau large (une colonne par indicateur), sans biais de look-ahead.

    Pour chaque indicateur et chaque date du calendrier cible, on prend la dernière valeur
    dont `release_date` est antérieure ou égale à cette date (merge_asof, direction="backward").
    Les indicateurs plus lents que `target_freq` sont donc naturellement "étalés" (forward-fill
    borné par la publication), et les indicateurs plus rapides sont sous-échantillonnés à leur
    dernière valeur connue à la date du panneau.
    """
    if df.empty:
        return pd.DataFrame()

    start = start or df["timestamp"].min().strftime("%Y-%m-%d")
    end = end or df["release_date"].max().strftime("%Y-%m-%d")
    calendar = make_calendar(start, end, target_freq)
    calendar_df = pd.DataFrame({"__panel_date__": calendar})

    columns = []
    for code, g in df.groupby("indicator_code", observed=True):
        g = g.sort_values("release_date")[["release_date", "value"]].rename(columns={"value": code})
        merged = pd.merge_asof(calendar_df, g, left_on="__panel_date__", right_on="release_date", direction="backward")
        columns.append(merged.set_index("__panel_date__")[code])

    panel = pd.concat(columns, axis=1)
    panel.index.name = "date"
    return panel


def publication_lag_report(df: pd.DataFrame) -> pd.DataFrame:
    """Écart médian, par indicateur, entre `timestamp` (période décrite) et `release_date`
    (date de publication estimée). Utile pour vérifier que les délais déclarés dans
    `registry.py` sont réalistes avant de brancher le panneau sur un modèle."""
    if df.empty:
        return pd.DataFrame(columns=["indicator_code", "median_lag_days", "n_obs"])
    tmp = df.copy()
    tmp["lag_days"] = (tmp["release_date"] - tmp["timestamp"]).dt.days
    return (
        tmp.groupby("indicator_code", observed=True)["lag_days"]
        .agg(median_lag_days="median", n_obs="count")
        .reset_index()
    )
