"""Tests du schéma unifié : construction, validation, dé-duplication."""
import pandas as pd
import pytest

from app.schema import COLUMNS, SchemaError, build_frame, concat, validate


def test_build_frame_has_all_columns_and_estimates_release_date():
    df = build_frame(
        timestamp=["2024-01-01", "2024-02-01"], country="USA", indicator_code="US_CPI",
        value=[300.1, 301.2], frequency="M", unit="indice", source="fred", publication_lag_days=15,
    )
    assert list(df.columns) == COLUMNS
    assert (df["release_date"] - df["timestamp"]).dt.days.tolist() == [15, 15]


def test_build_frame_rejects_bad_frequency():
    with pytest.raises(SchemaError):
        build_frame(timestamp=["2024-01-01"], country="USA", indicator_code="X", value=[1.0], frequency="Z", unit="u", source="s")


def test_build_frame_rejects_length_mismatch():
    with pytest.raises(SchemaError):
        build_frame(timestamp=["2024-01-01", "2024-02-01"], country="USA", indicator_code="X", value=[1.0], frequency="M", unit="u", source="s")


def test_validate_drops_nan_values():
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(["2024-01-01", "2024-02-01"]),
        "country": "USA", "indicator_code": "X", "value": [1.0, float("nan")],
        "frequency": "M", "unit": "u", "source": "s",
        "release_date": pd.to_datetime(["2024-01-15", "2024-02-15"]),
        "ingested_at": pd.Timestamp.now("UTC").tz_localize(None),
    })
    out = validate(df)
    assert len(out) == 1


def test_concat_deduplicates_on_source_country_indicator_timestamp():
    a = build_frame(timestamp=["2024-01-01"], country="USA", indicator_code="X", value=[1.0], frequency="M", unit="u", source="fred")
    b = build_frame(timestamp=["2024-01-01"], country="USA", indicator_code="X", value=[2.0], frequency="M", unit="u", source="fred")
    out = concat([a, b])
    assert len(out) == 1
    assert out.iloc[0]["value"] == 2.0  # keep="last"
