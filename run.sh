#!/usr/bin/env bash
# Lanzador del Apuntador de Tareas (Python + Textual)
set -euo pipefail
cd "$(dirname "$0")"

exec python3 apuntador.py "$@"
