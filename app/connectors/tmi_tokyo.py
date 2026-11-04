"""CPI de Tokyo (préfecture/municipalité) — fichier CSV du portail statistique métropolitain.

Format observé sur `tmi2025c.csv` (fourni par l'utilisateur, encodage Shift-JIS avec repli
UTF-8) : un tableau "large" avec une colonne par catégorie de dépense, contrairement au format
e-Stat (une ligne par observation) ou au format BOJ (une colonne par série, 9 lignes d'en-tête).
Ni e-Stat ni la table `statsDataId` devinée initialement pour ce CPI ne se sont révélés valides
(erreur `STATUS: 300`, "l'ID n'existe pas" — vérifié le 26/09/2026) : ce connecteur remplace
cette tentative par un fichier déposé manuellement, sur le même principe que RBI/MOSPI/BOJ.

Structure exacte des 6 lignes d'en-tête, avant les données :
    ligne 1 : noms de catégories en japonais
    ligne 2 : "Group/Item", puis noms de catégories en anglais
    ligne 3 : "Group/Item code", puis les codes (utilisés pour retrouver la bonne colonne)
    ligne 4 : numéro de série (ignoré)
    ligne 5 : poids (souvent vide)
    ligne 6 : poids pour 10 000 (souvent vide)
    ligne 7+ : données, une ligne par mois — "AAAAMM,valeur1,valeur2,..."

`params` attendus dans l'IndicatorSpec :
    filename : nom du fichier dans data/manual/tmi/, ex. "tmi2025c.csv"
    code     : code de catégorie à extraire (ex. "0901" pour "tous postes, CVS")
"""
from __future__ import annotations

import csv
import io

import pandas as pd

from .base import Connector, IndicatorSpec, safe_join
from ..schema import build_frame

HEADER_LINES = 6
CODE_ROW = 2  # "Group/Item code" (index 0-based)


class TmiTokyoFileNotFound(FileNotFoundError):
    pass


class TmiTokyoFormatError(ValueError):
    pass


def _decode(raw_bytes: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "shift_jis", "cp932"):
        try:
            return raw_bytes.decode(enc)
        except UnicodeDecodeError:
            continue
    raise TmiTokyoFormatError("impossible de décoder le fichier (essayé utf-8/shift_jis/cp932)")


class TmiTokyoConnector(Connector):
    name = "tmi_tokyo"

    def cache_key(self, spec: IndicatorSpec) -> str:
        return spec.code

    async def get_raw(self, spec: IndicatorSpec):
        return await self.fetch_raw(spec)  # fichier local : pas de mise en cache réseau

    async def fetch_raw(self, spec: IndicatorSpec) -> str:
        src = self.client.settings.source("tmi_tokyo")
        path = safe_join(src.base_url, spec.params["filename"])
        if not path.is_file():
            raise TmiTokyoFileNotFound(
                f"{path} introuvable : dépose l'export CSV du portail statistique de Tokyo à cet endroit."
            )
        return _decode(path.read_bytes())

    def normalize(self, raw: str, spec: IndicatorSpec) -> pd.DataFrame:
        lines = raw.splitlines()
        if len(lines) <= HEADER_LINES:
            raise TmiTokyoFormatError(f"fichier trop court ({len(lines)} lignes)")

        code_row = next(csv.reader([lines[CODE_ROW]]))
        codes = [c.strip() for c in code_row[1:]]
        wanted = spec.params["code"]
        if wanted not in codes:
            raise TmiTokyoFormatError(f"code {wanted!r} absent (codes trouvés : {codes})")
        col_index = codes.index(wanted)

        data_text = "\n".join(lines[HEADER_LINES:])
        df = pd.read_csv(io.StringIO(data_text), header=None, na_values=["", "-", "***"])
        if df.empty or df.shape[1] < col_index + 2:
            return build_frame(timestamp=[], country=spec.country, indicator_code=spec.code, value=[], frequency=spec.frequency, unit=spec.unit, source=self.name)

        dates = pd.to_datetime(df[0].astype(str), format="%Y%m", errors="coerce")
        values = pd.to_numeric(df[col_index + 1], errors="coerce")
        mask = dates.notna() & values.notna()
        if not mask.any():
            return build_frame(timestamp=[], country=spec.country, indicator_code=spec.code, value=[], frequency=spec.frequency, unit=spec.unit, source=self.name)

        return build_frame(
            timestamp=dates[mask],
            country=spec.country,
            indicator_code=spec.code,
            value=values[mask],
            frequency=spec.frequency,
            unit=spec.unit,
            source=self.name,
            publication_lag_days=spec.publication_lag_days,
        )
