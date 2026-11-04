"""FMI — nouvelle API SDMX 3.0 (https://api.imf.org/external/sdmx/3.0).

Remplace l'ancien connecteur INSEE pour les indicateurs français (et, plus généralement,
n'importe quel pays couvert par le FMI — REF_AREA est un simple paramètre de la clé).

Spécification vérifiée directement depuis le fichier OpenAPI officiel fourni par l'utilisateur
(idata-sdmx-api-3-0.json, servers[0].url = https://api.imf.org/external/sdmx/3.0) :

    GET /data/{context}/{agencyID}/{resourceID}/{version}/{key}

Exemple officiel donné par la documentation elle-même (repris tel quel comme référence) :
    context=dataflow, agencyID=IMF.STA, resourceID=CPI, version=+, key=USA.CPI.*.IX.M
    -> https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.STA/CPI/+/USA.CPI.*.IX.M

Authentification : clé d'abonnement gratuite (portail développeur du FMI), transmise soit dans
l'en-tête `Ocp-Apim-Subscription-Key`, soit en paramètre `subscription-key` (les deux sont
acceptés d'après la spec ; ce connecteur utilise l'en-tête).

Format de réponse : SDMX-JSON, avec la particularité que tout est imbriqué sous une clé `data`
(`{"data": {"dataSets": [...], "structures": [...]}, "meta": {...}}`, vérifié sur l'exemple
officiel de la documentation). Les séries sont indexées par une clé positionnelle
(ex. "0:0:0:0:0:0"), à décoder à l'aide de `structures[0].dimensions.series` (ordre des
dimensions) ; les observations sont indexées de la même façon via
`structures[0].dimensions.observation[0].values` (généralement `TIME_PERIOD`).

`params` attendus dans l'IndicatorSpec :
    agency_id   : ex. "IMF.STA"
    resource_id : ex. "CPI" (identifiant du dataflow)
    version     : ex. "+" (dernière version)
    key         : clé SDMX, dimensions séparées par des points, ex. "FRA.CPI.*.IX.M"
                  (remplacer le premier segment par le code pays ISO3 suffit dans la plupart des
                  dataflows du FMI, qui placent REF_AREA en première position — à vérifier au cas
                  par cas via le navigateur de données du FMI si un dataflow renvoie une erreur).
"""
from __future__ import annotations

import re

import pandas as pd

from .base import Connector, IndicatorSpec
from ..schema import build_frame

_SDMX_MONTHLY = re.compile(r"^(\d{4})-M(\d{2})$")


def _fix_sdmx_period(value: str) -> str:
    """Convertit la notation SDMX "AAAA-Mxx" (mois) en "AAAA-xx", que pandas sait dater.

    Bug réel rencontré en production : `pandas.to_datetime("1955-M01")` interprète le "01"
    après le "M" comme des SECONDES plutôt que comme le mois (`1955-01-01 00:00:01`), car
    dateutil ne reconnaît pas cette notation ISO 8601 pourtant standard en SDMX. Les autres
    notations période du FMI ("1955-Q4", "1955" seul, "1955-01-05") sont déjà bien comprises
    par pandas et ne sont pas modifiées ici.
    """
    m = _SDMX_MONTHLY.match(value)
    return f"{m.group(1)}-{m.group(2)}" if m else value


class ImfFormatError(ValueError):
    pass


def _decode_sdmx_json(payload: dict) -> pd.DataFrame:
    """Décode une réponse SDMX-JSON du FMI en une liste de (date, valeur).

    Générique : ne suppose rien sur le nombre de dimensions ni leur nom, uniquement sur la forme
    documentée (dataSets/series/observations + structures/dimensions), donc réutilisable pour
    n'importe quel dataflow du FMI, pas seulement CPI.
    """
    data = payload.get("data", payload)  # tolère aussi une réponse non enveloppée dans "data"
    datasets = data.get("dataSets", [])
    structures = data.get("structures", [])
    if not datasets or not structures:
        raise ImfFormatError("réponse SDMX-JSON sans dataSets/structures : rien à décoder")

    struct = structures[datasets[0].get("structure", 0)]
    obs_dim = struct["dimensions"]["observation"][0]  # généralement TIME_PERIOD, une seule dimension
    time_values = [v["value"] for v in obs_dim["values"]]

    rows = []
    for series_key, series in datasets[0].get("series", {}).items():
        for obs_index, obs_array in series.get("observations", {}).items():
            idx = int(obs_index)
            if idx >= len(time_values) or not obs_array:
                continue
            raw_value = obs_array[0]
            if raw_value in (None, "", "NaN"):
                continue
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                continue
            rows.append((time_values[idx], value))
    return rows


class ImfConnector(Connector):
    name = "imf"

    async def fetch_raw(self, spec: IndicatorSpec) -> dict:
        src = self.client.settings.source("imf")
        agency_id, resource_id = spec.params["agency_id"], spec.params["resource_id"]
        version, key = spec.params.get("version", "+"), spec.params["key"]
        path = f"data/dataflow/{agency_id}/{resource_id}/{version}/{key}"
        headers = {"Ocp-Apim-Subscription-Key": src.extra["api_key"]}
        resp = await self.client.get(src, path, headers=headers)
        return resp.json()

    def normalize(self, raw: dict, spec: IndicatorSpec) -> pd.DataFrame:
        try:
            rows = _decode_sdmx_json(raw)
        except (KeyError, IndexError, TypeError) as exc:
            raise ImfFormatError(f"structure SDMX-JSON inattendue pour {spec.code} : {exc}") from exc

        if not rows:
            return build_frame(timestamp=[], country=spec.country, indicator_code=spec.code, value=[], frequency=spec.frequency, unit=spec.unit, source=self.name)

        dates, values = zip(*rows)
        fixed_dates = [_fix_sdmx_period(d) for d in dates]
        return build_frame(
            timestamp=fixed_dates,
            country=spec.country,
            indicator_code=spec.code,
            value=list(values),
            frequency=spec.frequency,
            unit=spec.unit,
            source=self.name,
            publication_lag_days=spec.publication_lag_days,
        )
