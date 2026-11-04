"""Interface commune à tous les connecteurs.

Un connecteur sépare volontairement deux étapes :
- `fetch_raw`  : appel réseau (asynchrone), passe par le cache et le rate limiter.
- `normalize`  : fonction PURE (aucun réseau), transforme la réponse brute en DataFrame
                 au schéma unifié. C'est cette fonction que les tests unitaires exercent,
                 avec des réponses figées (fixtures), sans dépendre du réseau.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from ..httpclient import ApiClient
from ..cache import Store


@dataclass(frozen=True)
class IndicatorSpec:
    """Description déclarative d'une série à ingérer (voir `registry.py`)."""

    code: str  # code interne, ex. "US_CPI"
    country: str  # ISO3 ou zone : USA, FRA, DEU, JPN, CHN, IND, EA
    connector: str  # nom du connecteur : fred, ecb, imf, estat, boj, worldbank, nbs_china, manual, yfinance
    frequency: str  # D/W/M/Q/A
    unit: str
    params: dict = field(default_factory=dict)  # propre à chaque connecteur (series_id, dataflow, statsDataId, ...)
    publication_lag_days: int = 30  # estimation du délai réel de publication, si la source ne le fournit pas
    fallback: "IndicatorSpec | None" = None  # utilisé si ce connecteur échoue (voir pipeline.run_all)


def safe_join(base: str | Path, filename: str) -> Path:
    """Chemin d'un fichier déposé manuellement, garanti DANS `base` : refuse les chemins absolus et
    les `..` (un `filename` du registre mal saisi ne doit pas pouvoir lire n'importe quel fichier
    de la machine, puis l'exposer via l'API)."""
    base_path = Path(base).resolve()
    candidate = (base_path / filename).resolve()
    if Path(filename).is_absolute() or not candidate.is_relative_to(base_path):
        raise ValueError(f"nom de fichier hors du répertoire autorisé : {filename!r}")
    return candidate


class Connector(ABC):
    name: str

    def __init__(self, client: ApiClient, store: Store, cache_ttl_s: dict):
        self.client = client
        self.store = store
        self.cache_ttl_s = cache_ttl_s

    def cache_key(self, spec: IndicatorSpec) -> str:
        return spec.code

    async def get_raw(self, spec: IndicatorSpec):
        key = self.cache_key(spec)
        cached = self.store.cache_get(self.name, key)
        if cached is not None:
            return cached
        raw = await self.fetch_raw(spec)
        ttl = self.cache_ttl_s.get(spec.frequency, 24 * 3600)
        self.store.cache_set(self.name, key, raw, ttl)
        return raw

    @abstractmethod
    async def fetch_raw(self, spec: IndicatorSpec):
        """Appel réseau brut (sans cache ici : `get_raw` s'en charge)."""

    @abstractmethod
    def normalize(self, raw, spec: IndicatorSpec) -> pd.DataFrame:
        """Transforme la réponse brute en DataFrame conforme à `schema.COLUMNS`. Pure, sans réseau."""

    async def run(self, spec: IndicatorSpec) -> pd.DataFrame:
        raw = await self.get_raw(spec)
        return self.normalize(raw, spec)
