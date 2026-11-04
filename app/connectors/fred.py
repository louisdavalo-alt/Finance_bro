"""FRED (Federal Reserve Bank of St. Louis) — https://fred.stlouisfed.org

API JSON classique, clé gratuite obligatoire (FRED_API_KEY). Endpoint utilisé :
GET /series/observations?series_id=...&api_key=...&file_type=json

`params.series_id` attendu dans l'IndicatorSpec, ex. FEDFUNDS, DGS10, CPIAUCSL, UNRATE, WALCL.
"""
from __future__ import annotations

import pandas as pd

from .base import Connector, IndicatorSpec
from ..schema import build_frame


class FredConnector(Connector):
    name = "fred"

    async def fetch_raw(self, spec: IndicatorSpec) -> dict:
        src = self.client.settings.source("fred")
        series_id = spec.params["series_id"]
        resp = await self.client.get(
            src,
            "series/observations",
            params={
                "series_id": series_id,
                "api_key": src.extra["api_key"],
                "file_type": "json",
            },
        )
        return resp.json()

    def normalize(self, raw: dict, spec: IndicatorSpec) -> pd.DataFrame:
        obs = raw.get("observations", [])
        rows = [(o["date"], o["value"]) for o in obs if o.get("value") not in (None, ".", "")]
        if not rows:
            return build_frame(timestamp=[], country=spec.country, indicator_code=spec.code, value=[], frequency=spec.frequency, unit=spec.unit, source=self.name)
        dates, values = zip(*rows)
        return build_frame(
            timestamp=dates,
            country=spec.country,
            indicator_code=spec.code,
            value=[float(v) for v in values],
            frequency=spec.frequency,
            unit=spec.unit,
            source=self.name,
            publication_lag_days=spec.publication_lag_days,
        )
