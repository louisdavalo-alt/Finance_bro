"""ECB Data Portal — https://data-api.ecb.europa.eu (ex-SDW, redirection fermée le 1er octobre 2025).

API SDMX 2.1 REST, publique, sans clé. On utilise `format=csvdata` (plus simple à parser que
le JSON SDMX imbriqué) : GET /data/{dataflow}/{key}?format=csvdata&startPeriod=...

`params` attendus dans l'IndicatorSpec :
    dataflow : ex. "FM" (taux BCE), "BSI" (agrégats monétaires M3), "YC" (courbe des taux souverains)
    key      : clé de série SDMX, ex. "D.U2.EUR.4F.KR.MRR_FR.LEV" (taux de refinancement)
    start_period : optionnel, ex. "2015-01"

Quelques clés utiles (à ajuster si la structure du dataflow change) :
    Taux de la BCE (facilité de dépôt) : dataflow=FM,  key=B.U2.EUR.4F.KR.DFR.LEV
    Masse monétaire M3 (zone euro)     : dataflow=BSI, key=M.U2.Y.V.M30.X.I.U2.2300.Z01.E
    Rendement souverain 10 ans (zone euro, AAA) : dataflow=YC, key=B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y
"""
from __future__ import annotations

import io

import pandas as pd

from .base import Connector, IndicatorSpec
from ..schema import build_frame


class EcbConnector(Connector):
    name = "ecb"

    async def fetch_raw(self, spec: IndicatorSpec) -> str:
        src = self.client.settings.source("ecb")
        dataflow, key = spec.params["dataflow"], spec.params["key"]
        params = {"format": "csvdata"}
        if spec.params.get("start_period"):
            params["startPeriod"] = spec.params["start_period"]
        resp = await self.client.get(src, f"data/{dataflow}/{key}", params=params)
        return resp.text

    def normalize(self, raw: str, spec: IndicatorSpec) -> pd.DataFrame:
        df = pd.read_csv(io.StringIO(raw))
        if df.empty or "TIME_PERIOD" not in df.columns or "OBS_VALUE" not in df.columns:
            return build_frame(timestamp=[], country=spec.country, indicator_code=spec.code, value=[], frequency=spec.frequency, unit=spec.unit, source=self.name)
        df = df.dropna(subset=["OBS_VALUE"])
        return build_frame(
            timestamp=df["TIME_PERIOD"],
            country=spec.country,
            indicator_code=spec.code,
            value=df["OBS_VALUE"].astype(float),
            frequency=spec.frequency,
            unit=spec.unit,
            source=self.name,
            publication_lag_days=spec.publication_lag_days,
        )
