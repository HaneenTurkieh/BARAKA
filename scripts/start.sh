#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
exec .venv/bin/python -m uvicorn backend.server:app --host 0.0.0.0 --port "${PORT:-8000}"
