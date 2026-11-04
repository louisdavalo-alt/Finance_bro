"""Planification du pipeline.

Deux façons de le programmer, aucune n'exigeant de droits admin ni de service supplémentaire :

1. **cron + ce script en tâche ponctuelle** (recommandé pour un usage personnel) :
   `python -m app.pipeline` s'exécute, écrit dans DuckDB/Parquet, puis se termine.
   Voir `deploy/crontab.example`.

2. **Ce module, en processus de fond** (`python -m app.scheduler`) : utile si tu préfères un
   seul processus long-lived à surveiller plutôt que des exécutions cron séparées. Utilise
   APScheduler (bibliothèque Python pure, aucun service externe) plutôt que Celery : Celery
   demande un broker (Redis/RabbitMQ) qui tourne en permanence, ce qui a plus de sens pour
   plusieurs workers distribués que pour un pipeline personnel mono-machine. Si tu passes un
   jour à plusieurs machines, remplacer ce fichier par des tâches Celery ne change rien au
   reste du code : `pipeline.run_all()` resterait la fonction appelée.
"""
from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import load_settings
from .pipeline import run_all
from .security import setup_logging

log = logging.getLogger("scheduler")

# Une seule exécution à la fois. L'ancienne version planifiait une fonction SYNCHRONE qui lançait
# `asyncio.create_task(run_all())` et rendait la main aussitôt : `max_instances=1` ne protégeait
# donc rien (la tâche durait 0 ms pour APScheduler), deux exécutions longues pouvaient se
# chevaucher et se disputer le verrou DuckDB, et la tâche, non référencée, pouvait même être
# récupérée par le ramasse-miettes en cours de route.
_run_lock = asyncio.Lock()


async def _job() -> None:
    if _run_lock.locked():
        log.warning("exécution précédente encore en cours : celle-ci est sautée")
        return
    async with _run_lock:
        try:
            await run_all(load_settings())
        except Exception:  # noqa: BLE001 - le planificateur doit survivre à une exécution ratée
            log.exception("échec de l'exécution planifiée du pipeline")


async def main() -> None:
    setup_logging()
    scheduler = AsyncIOScheduler()
    # Toutes les heures : le cache (voir cache.py) évite de re-solliciter une source dont la
    # fréquence de publication est plus lente (mensuelle, trimestrielle...).
    scheduler.add_job(_job, CronTrigger(minute=0), id="macro_pipeline", max_instances=1, coalesce=True)
    scheduler.start()
    log.info("planificateur démarré : exécution du pipeline toutes les heures")
    await _job()  # une première exécution immédiate
    try:
        await asyncio.Event().wait()  # tourne indéfiniment
    finally:
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
