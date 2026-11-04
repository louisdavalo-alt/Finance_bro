"""Connecteur générique pour les sources sans API JSON publique stable : RBI (DBIE) et
MOSPI (Inde).

Ni la RBI ni le MOSPI n'exposent d'API publique documentée : DBIE se pilote via une interface
web qui génère des exports Excel/CSV à la demande, et le MOSPI publie ses séries (PIB, PMI)
sous forme de communiqués et de fichiers téléchargeables plutôt que d'un service REST.

Solution retenue pour un usage personnel, sans scraping fragile :
1. Tu exportes toi-même, périodiquement, les séries qui t'intéressent depuis
   https://data.rbi.org.in (DBIE) ou https://mospi.gov.in vers un fichier CSV (2 colonnes :
   une date, une valeur), déposé dans `data/manual/<code>.csv`.
2. Ce connecteur lit ce fichier local : il n'y a pas d'appel réseau, donc pas de rate limit
   ni de cache à gérer, mais la donnée n'est aussi fraîche que ton dernier export.
3. En complément, `registry.py` déclare un repli automatique vers la Banque mondiale pour les
   mêmes indicateurs (fréquence annuelle, moins réactif mais toujours à jour).

`params` attendus dans l'IndicatorSpec :
    filename   : nom du fichier dans data/manual/, ex. "rbi_repo_rate.csv"
    date_col   : nom de la colonne date dans le CSV (par défaut "date")
    value_col  : nom de la colonne valeur dans le CSV (par défaut "value")
"""
from __future__ import annotations


import pandas as pd

from .base import Connector, IndicatorSpec, safe_join
from ..schema import build_frame


class ManualFileNotFound(FileNotFoundError):
    pass


class ManualCsvConnector(Connector):
    name = "manual"

    def cache_key(self, spec: IndicatorSpec) -> str:
        # Pas de mise en cache réseau : on relit le fichier à chaque fois (il est déjà local).
        return spec.code

    async def get_raw(self, spec: IndicatorSpec):
        return await self.fetch_raw(spec)  # court-circuite le cache DuckDB : lecture disque directe

    async def fetch_raw(self, spec: IndicatorSpec) -> str:
        src = self.client.settings.source("manual")
        path = safe_join(src.base_url, spec.params["filename"])
        if not path.is_file():
            raise ManualFileNotFound(
                f"{path} introuvable : dépose un export CSV (colonnes date/valeur) à cet endroit, "
                f"ou laisse le repli Banque mondiale de l'indicateur `{spec.code}` s'appliquer."
            )
        return path.read_text(encoding="utf-8")

    def normalize(self, raw: str, spec: IndicatorSpec) -> pd.DataFrame:
        import io

        date_col = spec.params.get("date_col", "date")
        value_col = spec.params.get("value_col", "value")
        df = pd.read_csv(io.StringIO(raw))
        if df.empty or date_col not in df.columns or value_col not in df.columns:
            return build_frame(timestamp=[], country=spec.country, indicator_code=spec.code, value=[], frequency=spec.frequency, unit=spec.unit, source=self.name)
        df = df.dropna(subset=[value_col])
        return build_frame(
            timestamp=pd.to_datetime(df[date_col]),
            country=spec.country,
            indicator_code=spec.code,
            value=pd.to_numeric(df[value_col], errors="coerce"),
            frequency=spec.frequency,
            unit=spec.unit,
            source=self.name,
            # Donnée déposée manuellement : on la considère connue dès sa date de référence.
            release_date=pd.to_datetime(df[date_col]),
        )
