"""Chine — National Bureau of Statistics (data.stats.gov.cn).

⚠️ Le NBS ne publie pas de documentation d'API publique stable. L'endpoint `easyquery.htm`
utilisé ici est celui exploité par plusieurs bibliothèques tierces non officielles (ex.
`rstatscn`), par rétro-ingénierie du site web — il peut changer ou être bloqué sans préavis,
en particulier depuis un serveur hébergé hors de Chine. C'est pourquoi chaque indicateur
chinois de `registry.py` déclare un `fallback` vers un indicateur Banque mondiale équivalent :
voir `pipeline.py`, qui bascule automatiquement dessus si ce connecteur échoue.

`params` attendus dans l'IndicatorSpec :
    zb : code indicateur NBS ("zhibiao"), ex. "A01030101" (PIB) — à retrouver sur
         https://data.stats.gov.cn en inspectant les requêtes réseau de la page de recherche.
    db : base NBS, ex. "hgyd" (mensuel), "hgjd" (trimestriel), "hgnd" (annuel)
"""
from __future__ import annotations

import json

import pandas as pd

from .base import Connector, IndicatorSpec
from ..schema import build_frame


class NbsChinaConnector(Connector):
    name = "nbs_china"

    async def fetch_raw(self, spec: IndicatorSpec) -> dict:
        src = self.client.settings.source("nbs_china")
        params = {
            "m": "QueryData",
            "dbcode": spec.params.get("db", "hgyd"),
            "rowcode": "zb",
            "colcode": "sj",
            "wds": "[]",
            "dfwds": json.dumps([{"wdcode": "zb", "valuecode": spec.params["zb"]}]),
        }
        resp = await self.client.get(src, "", params=params)
        return resp.json()

    def normalize(self, raw: dict, spec: IndicatorSpec) -> pd.DataFrame:
        # Structure observée (non garantie) : raw["returndata"]["datanodes"] = [{"data": {"data": v}, "wds": [{"valuecode": "202401"}]}]
        try:
            nodes = raw["returndata"]["datanodes"]
        except (KeyError, TypeError):
            return build_frame(timestamp=[], country=spec.country, indicator_code=spec.code, value=[], frequency=spec.frequency, unit=spec.unit, source=self.name)

        dates, values = [], []
        for node in nodes:
            val = node.get("data", {}).get("data")
            if val is None:
                continue
            period = next((w["valuecode"] for w in node.get("wds", []) if w.get("wdcode") == "sj"), None)
            if not period:
                continue
            dates.append(period)
            values.append(float(val))
        if not dates:
            return build_frame(timestamp=[], country=spec.country, indicator_code=spec.code, value=[], frequency=spec.frequency, unit=spec.unit, source=self.name)
        return build_frame(
            timestamp=pd.to_datetime(dates, format="%Y%m", errors="coerce"),
            country=spec.country,
            indicator_code=spec.code,
            value=values,
            frequency=spec.frequency,
            unit=spec.unit,
            source=self.name,
            publication_lag_days=spec.publication_lag_days,
        )
