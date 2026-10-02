#!/bin/bash
# V2-004 D1: run all 15 predeclared fits sequentially, one fresh Python process per fit, in the
# predeclared architecture-major run order. Stops immediately (set -e) on the first failure so
# a defect can be inspected before any retry, per Section 19.
set -euo pipefail
cd "$(dirname "$0")/.."

RUN_ORDER=(
  "MODEL_V2_CAPCTRL 0" "MODEL_V2_CAPCTRL 1" "MODEL_V2_CAPCTRL 2" "MODEL_V2_CAPCTRL 3" "MODEL_V2_CAPCTRL 4"
  "MODEL_V2_TCN_MEAN 0" "MODEL_V2_TCN_MEAN 1" "MODEL_V2_TCN_MEAN 2" "MODEL_V2_TCN_MEAN 3" "MODEL_V2_TCN_MEAN 4"
  "MODEL_V2_TCN_MEANMAX 0" "MODEL_V2_TCN_MEANMAX 1" "MODEL_V2_TCN_MEANMAX 2" "MODEL_V2_TCN_MEANMAX 3" "MODEL_V2_TCN_MEANMAX 4"
)
SEED=20260927

for pair in "${RUN_ORDER[@]}"; do
  read -r architecture fold <<< "$pair"
  echo "=== STARTING V2-004-D1-${architecture}-F0${fold}-S${SEED} at $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
  PYTHONPATH=src:. .venv-t032/bin/python scripts/run_v2_004_fit.py \
    --architecture "$architecture" --stage D1 --outer-fold "$fold" --seed "$SEED"
  echo "=== FINISHED V2-004-D1-${architecture}-F0${fold}-S${SEED} at $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
done

echo "ALL_15_D1_FITS_COMPLETE"
