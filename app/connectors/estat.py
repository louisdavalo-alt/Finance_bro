"""e-Stat — portail des statistiques officielles du Japon (https://www.e-stat.go.jp).

API JSON officielle : GET /rest/3.0/app/json/getStatsData?appId=...&statsDataId=...
Clé gratuite (ESTAT_APP_ID) à obtenir sur https://www.e-stat.go.jp/mypage/user/preregister.

Particularité e-Stat : chaque observation porte un code temporel (`@time`) propre à la table,
dont le libellé humain (ex. "2024年04月") est donné séparément dans les métadonnées
(`CLASS_INF.CLASS_OBJ` où `@id == "time"`). Ce connecteur reconstruit la date à partir de ce
libellé pour les motifs les plus courants (mensuel "AAAA年MM月", trimestriel "AAAA年MM月期",
annuel "AAAA年") ; un motif non reconnu est laissé de côté (log, pas d'exception) plutôt que
de produire une date fausse.

`params` attendus dans l'IndicatorSpec :
    stats_data_id : identifiant de la table (ex. "0003348423")
    query_params  : dict optionnel de filtres supplémentaires (cdCat01, cdArea, ...)
"""
from __future__ import annotations

import logging
import re

import pandas as pd

from .base import Connector, IndicatorSpec
from ..schema import build_frame

log = logging.getLogger("connectors.estat")

_MONTHLY = re.compile(r"(\d{4})年(\d{1,2})月(?!期)")
_QUARTERLY_PERIOD = re.compile(r"(\d{4})年(\d{1,2})月期")
_ANNUAL = re.compile(r"^(\d{4})年$")


def _parse_time_label(label: str) -> pd.Timestamp | None:
    label = label.strip()
    if m := _QUARTERLY_PERIOD.match(label):
        return pd.Timestamp(year=int(m.group(1)), month=int(m.group(2)), day=1)
    if m := _MONTHLY.match(label):
        return pd.Timestamp(year=int(m.group(1)), month=int(m.group(2)), day=1)
    if m := _ANNUAL.match(label):
        return pd.Timestamp(year=int(m.group(1)), month=1, day=1)
    return None


class EstatConnector(Connector):
    name = "estat"

    async def fetch_raw(self, spec: IndicatorSpec) -> dict:
        src = self.client.settings.source("estat")
        params = {"appId": src.extra["app_id"], "statsDataId": spec.params["stats_data_id"]}
        params.update(spec.params.get("query_params", {}))
        resp = await self.client.get(src, "getStatsData", params=params)
        return resp.json()

    def normalize(self, raw: dict, spec: IndicatorSpec) -> pd.DataFrame:
        try:
            stat = raw["GET_STATS_DATA"]["STATISTICAL_DATA"]
        except KeyError:
            return build_frame(timestamp=[], country=spec.country, indicator_code=spec.code, value=[], frequency=spec.frequency, unit=spec.unit, source=self.name)

        time_labels: dict[str, str] = {}
        class_objs = stat.get("CLASS_INF", {}).get("CLASS_OBJ", [])
        if isinstance(class_objs, dict):
            class_objs = [class_objs]
        for obj in class_objs:
            if obj.get("@id") == "time":
                classes = obj.get("CLASS", [])
                if isinstance(classes, dict):
                    classes = [classes]
                time_labels = {c["@code"]: c["@name"] for c in classes}

        values = stat.get("DATA_INF", {}).get("VALUE", [])
        if isinstance(values, dict):
            values = [values]

        dates, vals = [], []
        for v in values:
            raw_val = v.get("$")
            if raw_val in (None, "", "-", "***"):
                continue
            label = time_labels.get(v.get("@time"), v.get("@time", ""))
            ts = _parse_time_label(label)
            if ts is None:
                log.debug("libellé temporel e-Stat non reconnu, observation ignorée : %r", label)
                continue
            try:
                vals.append(float(raw_val))
            except ValueError:
                continue
            dates.append(ts)

        if not dates:
            return build_frame(timestamp=[], country=spec.country, indicator_code=spec.code, value=[], frequency=spec.frequency, unit=spec.unit, source=self.name)
        return build_frame(
            timestamp=dates,
            country=spec.country,
            indicator_code=spec.code,
            value=vals,
            frequency=spec.frequency,
            unit=spec.unit,
            source=self.name,
            publication_lag_days=spec.publication_lag_days,
        )
