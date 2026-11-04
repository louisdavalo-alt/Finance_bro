"""Tests de l'alignement temporel : c'est ici que le biais de look-ahead se joue."""
import pandas as pd

from app.resample import align_panel, publication_lag_report
from app.schema import build_frame, concat


def _series(code, timestamps, values, lag_days):
    return build_frame(
        timestamp=timestamps, country="USA", indicator_code=code, value=values,
        frequency="M", unit="u", source="fred", publication_lag_days=lag_days,
    )


def test_align_panel_never_exposes_value_before_release_date():
    # CPI de janvier connu seulement mi-février (lag 45 j) ; taux Fed connu le jour même.
    cpi = _series("CPI", ["2024-01-01", "2024-02-01"], [300.0, 301.0], lag_days=45)
    fedfunds = _series("FEDFUNDS", ["2024-01-01", "2024-02-01", "2024-03-01"], [5.25, 5.25, 5.5], lag_days=0)
    df = concat([cpi, fedfunds])

    panel = align_panel(df, target_freq="M", start="2024-01-01", end="2024-03-01")

    # Au 1er février, le CPI de janvier (release ~15 février) n'est PAS encore connu.
    assert pd.isna(panel.loc["2024-02-01", "CPI"])
    # Au 1er mars, le CPI de janvier (release ~15 février) est connu, mais pas celui de février.
    assert panel.loc["2024-03-01", "CPI"] == 300.0
    # Fed funds sans délai : connu dès le mois courant.
    assert panel.loc["2024-02-01", "FEDFUNDS"] == 5.25


def test_align_panel_forward_fills_slower_series_once_released():
    gdp = _series("GDP", ["2024-01-01"], [2.1], lag_days=45)  # trimestriel, mais testé en mensuel ici
    panel = align_panel(gdp, target_freq="M", start="2024-01-01", end="2024-04-01")
    assert pd.isna(panel.loc["2024-02-01", "GDP"])
    assert panel.loc["2024-03-01", "GDP"] == 2.1
    assert panel.loc["2024-04-01", "GDP"] == 2.1  # toujours la dernière valeur connue


def test_publication_lag_report_matches_declared_lag():
    cpi = _series("CPI", ["2024-01-01", "2024-02-01"], [300.0, 301.0], lag_days=15)
    report = publication_lag_report(cpi)
    row = report[report["indicator_code"] == "CPI"].iloc[0]
    assert row["median_lag_days"] == 15
    assert row["n_obs"] == 2
