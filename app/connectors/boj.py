"""Banque du Japon — lecture des exports CSV de stat-search.boj.or.jp.

Historique : l'API REST documentée (`/api/v1/getDataCode`) a systématiquement renvoyé
"Invalid input parameters" lors des tests réels (25/09/2026), y compris avec un code de série
confirmé par ailleurs (`FM01'STRDCLUCON`). Le site web utilise en interne un script CGI hérité
(`famecgi2`), non documenté et non prévu pour un usage externe. On abandonne donc l'API REST
pour ce connecteur, au profit d'un export CSV téléchargé manuellement — le même mécanisme que
pour RBI/MOSPI (`connectors/manual.py`), mais avec un format fiable et déjà vérifié sur des
fichiers réels (voir `tests/fixtures/*.csv`) :

    ligne 1  : titre
    ligne 2  : date d'export
    ligne 3  : (vide), nom de catégorie (une colonne par série si le fichier en contient plusieurs)
    ligne 4  : "Series name" / "系列名称"
    ligne 5  : "Series code" / "データコード"   <- utilisée pour retrouver la bonne colonne
    ligne 6  : "Unit" / "単位"
    ligne 7  : "Start of the time-series" / "収録開始期"
    ligne 8  : "End of the time-series" / "収録終了期"
    ligne 9  : "Last update" / "最終更新日"
    ligne 10+: données, une ligne par période (date, valeur[, valeur2, ...]), "NA" = manquant

Format stable observé aussi bien en export anglais (UTF-8) qu'en export japonais (Shift-JIS) :
seul l'encodage et la langue des libellés changent, la position des lignes est identique.

Pour obtenir un fichier : sur https://www.stat-search.boj.or.jp, section "Search by statistics",
déplier la catégorie (ex. "Financial Markets"), cliquer sur l'icône de téléchargement CSV à côté
de la série souhaitée, puis déposer le fichier dans `data/manual/boj/` sous le nom attendu par
`registry.py` (`params["filename"]`).

`params` attendus dans l'IndicatorSpec :
    filename : nom du fichier dans data/manual/boj/, ex. "fm01_d_1.csv"
    code     : code de série à extraire (ex. "FM01'STRDCLUCON") — utile si le fichier contient
               plusieurs colonnes (cas des exports multi-séries) ; sinon la première colonne de
               données est utilisée.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

import pandas as pd

from .base import Connector, IndicatorSpec, safe_join
from ..schema import build_frame

HEADER_LINES = 9  # nombre de lignes de métadonnées avant les données, observé sur les exports réels
CODE_ROW = 4  # ligne "Series code" / "データコード" (index 0-based)


class BojFileNotFound(FileNotFoundError):
    pass


class BojFormatError(ValueError):
    pass


def _decode(raw_bytes: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "shift_jis", "cp932"):
        try:
            return raw_bytes.decode(enc)
        except UnicodeDecodeError:
            continue
    raise BojFormatError("impossible de décoder le fichier BOJ (essayé utf-8/shift_jis/cp932)")


class BojConnector(Connector):
    name = "boj"

    def cache_key(self, spec: IndicatorSpec) -> str:
        return spec.code

    async def get_raw(self, spec: IndicatorSpec):
        return await self.fetch_raw(spec)  # fichier local : pas de mise en cache réseau

    async def fetch_raw(self, spec: IndicatorSpec) -> str:
        src = self.client.settings.source("boj")
        path = safe_join(Path(src.base_url) / "boj", spec.params["filename"])
        if not path.is_file():
            raise BojFileNotFound(
                f"{path} introuvable : télécharge le CSV de la série depuis "
                f"https://www.stat-search.boj.or.jp (icône de téléchargement à côté de la série "
                f"dans 'Search by statistics'), et dépose-le à cet endroit."
            )
        return _decode(path.read_bytes())

    def normalize(self, raw: str, spec: IndicatorSpec) -> pd.DataFrame:
        lines = raw.splitlines()
        if len(lines) <= HEADER_LINES:
            raise BojFormatError(f"fichier trop court ({len(lines)} lignes) pour être un export BOJ valide")

        code_row = next(csv.reader([lines[CODE_ROW]]))
        codes = [c.strip() for c in code_row[1:]]  # colonne 0 = libellé "Series code"

        wanted = spec.params.get("code")
        if wanted:
            if wanted not in codes:
                raise BojFormatError(
                    f"code {wanted!r} absent de ce fichier (codes trouvés : {codes}) — "
                    f"vérifie que le bon fichier a été déposé pour {spec.code}."
                )
            col_index = codes.index(wanted)
        else:
            col_index = 0

        data_text = "\n".join(lines[HEADER_LINES:])
        df = pd.read_csv(io.StringIO(data_text), header=None, na_values=["NA", "***", "-"])
        if df.empty or df.shape[1] < col_index + 2:
            return build_frame(timestamp=[], country=spec.country, indicator_code=spec.code, value=[], frequency=spec.frequency, unit=spec.unit, source=self.name)

        dates = pd.to_datetime(df[0], errors="coerce", format="mixed")
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
