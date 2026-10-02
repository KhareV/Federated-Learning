#!/bin/bash
# V2-002: run all 15 predeclared fits sequentially, one fresh Python process per fit, in the
# predeclared run order. Stops immediately (set -e) on the first failure so a defect can be
# inspected before any retry, per Section 28.
set -euo pipefail
cd "$(dirname "$0")/.."

RUN_ORDER=(
  "0 20260927" "0 20260928" "0 20260929"
  "1 20260927" "1 20260928" "1 20260929"
  "2 20260927" "2 20260928" "2 20260929"
  "3 20260927" "3 20260928" "3 20260929"
  "4 20260927" "4 20260928" "4 20260929"
)

for pair in "${RUN_ORDER[@]}"; do
  read -r fold seed <<< "$pair"
  echo "=== STARTING V2-002-F0${fold}-S${seed} at $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
  PYTHONPATH=src:. .venv-t032/bin/python scripts/run_model_v1_cv_reference_fit_v2002.py \
    --outer-fold "$fold" --seed "$seed"
  echo "=== FINISHED V2-002-F0${fold}-S${seed} at $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
done

echo "ALL_15_FITS_COMPLETE"
