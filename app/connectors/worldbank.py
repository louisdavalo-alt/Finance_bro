"""Banque mondiale — https://api.worldbank.org (API publique, sans clé, très stable).

Sert de repli pour les indicateurs chinois et indiens quand la source officielle
(NBS Chine, RBI, MOSPI) n'est pas accessible en JSON de façon fiable. Fréquence annuelle
uniquement pour la plupart des séries macro — à combiner avec des sources plus fraîches
(PMI, taux directeur) plutôt qu'à utiliser seule pour du suivi rapproché.

`params` attendus dans l'IndicatorSpec :
    iso3          : code pays ISO3, ex. "CHN", "IND"
    indicator     : code Banque mondiale, ex. "NY.GDP.MKTP.KD.ZG" (croissance du PIB),
                    "FP.CPI.TOTL.ZG" (inflation), "NV.IND.MANF.ZS" (industrie manufacturière, % PIB)
"""
from __future__ import annotations

import pandas as pd

from .base import Connector, IndicatorSpec
from ..schema import build_frame


class WorldBankConnector(Connector):
    name = "worldbank"

    async def fetch_raw(self, spec: IndicatorSpec) -> list:
        src = self.client.settings.source("worldbank")
        iso3, indicator = spec.params["iso3"], spec.params["indicator"]
        resp = await self.client.get(
            src, f"country/{iso3}/indicator/{indicator}", params={"format": "json", "per_page": 1000}
        )
        return resp.json()

    def normalize(self, raw: list, spec: IndicatorSpec) -> pd.DataFrame:
        if not isinstance(raw, list) or len(raw) < 2 or not raw[1]:
            return build_frame(timestamp=[], country=spec.country, indicator_code=spec.code, value=[], frequency=spec.frequency, unit=spec.unit, source=self.name)
        rows = [(r["date"], r["value"]) for r in raw[1] if r.get("value") is not None]
        if not rows:
            return build_frame(timestamp=[], country=spec.country, indicator_code=spec.code, value=[], frequency=spec.frequency, unit=spec.unit, source=self.name)
        years, values = zip(*rows)
        return build_frame(
            timestamp=[f"{y}-12-31" for y in years],  # série annuelle : on date au 31/12 de l'année de référence
            country=spec.country,
            indicator_code=spec.code,
            value=[float(v) for v in values],
            frequency="A",
            unit=spec.unit,
            source=self.name,
            publication_lag_days=spec.publication_lag_days,
        )
