"""Pipeline ETL : exécute le catalogue d'indicateurs de façon asynchrone, avec repli
automatique et résilience (l'échec d'un indicateur n'interrompt pas les autres).

Lancement direct : `python -m app.pipeline` (à planifier via cron, voir deploy/crontab.example
et le README — pas de dépendance à Celery/Redis pour un usage personnel sans droits admin ;
voir `scheduler.py` pour la variante "tourne en continu").
"""
from __future__ import annotations

import asyncio
import logging
import sys

import pandas as pd

from .cache import Store
from .config import Settings, load_settings
from .connectors.base import Connector, IndicatorSpec
from .connectors.boj import BojConnector
from .connectors.ecb import EcbConnector
from .connectors.estat import EstatConnector
from .connectors.fred import FredConnector
from .connectors.imf import ImfConnector
from .connectors.manual import ManualCsvConnector
from .connectors.nbs_china import NbsChinaConnector
from .connectors.tmi_tokyo import TmiTokyoConnector
from .connectors.worldbank import WorldBankConnector
from .connectors.yfin import YFinanceConnector
from .httpclient import ApiClient
from .registry import INDICATORS
from .schema import concat
from .security import setup_logging

log = logging.getLogger("pipeline")

CONNECTOR_CLASSES: dict[str, type[Connector]] = {
    "fred": FredConnector,
    "ecb": EcbConnector,
    "imf": ImfConnector,
    "estat": EstatConnector,
    "boj": BojConnector,
    "nbs_china": NbsChinaConnector,
    "worldbank": WorldBankConnector,
    "manual": ManualCsvConnector,
    "tmi_tokyo": TmiTokyoConnector,
    "yfinance": YFinanceConnector,
}


def build_connectors(settings: Settings, client: ApiClient, store: Store) -> dict[str, Connector]:
    return {name: cls(client, store, settings.cache_ttl_s) for name, cls in CONNECTOR_CLASSES.items()}


async def run_one(connectors: dict[str, Connector], spec: IndicatorSpec) -> pd.DataFrame:
    """Exécute un indicateur, avec repli en cascade si `spec.fallback` est défini."""
    connector = connectors[spec.connector]
    try:
        df = await connector.run(spec)
        if df.empty:
            raise RuntimeError("réponse vide")
        log.info("%s (%s) : %d observations", spec.code, spec.connector, len(df))
        return df
    except Exception as exc:  # noqa: BLE001 - on veut isoler l'échec, pas arrêter le pipeline
        log.warning("échec %s via %s : %s", spec.code, spec.connector, exc)
        if spec.fallback is not None:
            log.info("repli de %s vers %s (%s)", spec.code, spec.fallback.code, spec.fallback.connector)
            return await run_one(connectors, spec.fallback)
        return pd.DataFrame()


async def run_all(settings: Settings | None = None, specs: list[IndicatorSpec] | None = None) -> pd.DataFrame:
    settings = settings or load_settings()
    specs = specs if specs is not None else INDICATORS
    store = Store(settings.data_dir)
    try:
        async with ApiClient(settings) as client:
            connectors = build_connectors(settings, client, store)
            enabled_specs = [s for s in specs if settings.source(s.connector).enabled]
            skipped = [s.code for s in specs if s not in enabled_specs]
            if skipped:
                log.info("indicateurs ignorés (connecteur désactivé, clé manquante) : %s", ", ".join(skipped))

            results = await asyncio.gather(*(run_one(connectors, s) for s in enabled_specs))
        df = concat(results)
        n = store.upsert_observations(df)
        purged = store.purge_expired_cache()
        if purged:
            log.info("cache : %d entrées expirées supprimées", purged)
        log.info("pipeline terminé : %d observations enregistrées sur %d indicateurs", n, len(enabled_specs))
        return df
    finally:
        store.close()


def main() -> None:
    setup_logging()
    asyncio.run(run_all())


if __name__ == "__main__":
    sys.exit(main())
