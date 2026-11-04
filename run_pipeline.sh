#!/usr/bin/env bash
# Exécute le pipeline une fois (à planifier via cron, voir deploy/crontab.example).
set -euo pipefail
cd "$(dirname "$0")"
umask 077  # base DuckDB, exports et journaux lisibles uniquement par l'utilisateur courant
mkdir -p data
if command -v flock >/dev/null 2>&1; then
  exec flock -n data/.pipeline.lock .venv/bin/python -m app.pipeline
fi
exec .venv/bin/python -m app.pipeline
