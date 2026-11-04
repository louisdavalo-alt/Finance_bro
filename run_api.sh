#!/usr/bin/env bash
# Lance l'API de consultation au premier plan (Ctrl+C pour arrêter).
# Peut tourner en même temps que le pipeline : l'API ne lit que les exports Parquet.
set -euo pipefail
cd "$(dirname "$0")"
umask 077
exec .venv/bin/python -m app.serve
