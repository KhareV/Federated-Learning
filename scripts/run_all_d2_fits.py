#!/usr/bin/env python3
"""V2-004 D2 (conditional): read the D1-advancement list from the already-frozen
d1_decision.json and run exactly the predeclared D2 matrix -- at most 2 architectures x 5
folds x 2 additional seeds (20260928, 20260929) = at most 20 fits. No manual architecture
substitution: the advancement list is read mechanically, never typed in by hand. One fresh
Python process per fit (subprocess), sequential, architecture-major then seed-major order.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D1_DECISION_PATH = ROOT / "reports/model_v2/v2_004/d1_decision.json"
SEEDS = (20260928, 20260929)
FOLDS = (0, 1, 2, 3, 4)


def main() -> None:
    decision = json.loads(D1_DECISION_PATH.read_text(encoding="utf-8"))
    advancement = decision["one_se_rule"]["d2_advancement_list"]
    if not advancement:
        print("D1 advancement list is empty -- no D2 fits to run. Exiting 0.")
        return
    if len(advancement) > 2:
        raise RuntimeError(f"D1 advancement list has {len(advancement)} entries, max 2 allowed")

    print(f"D2 architectures (from d1_decision.json, read mechanically): {advancement}")
    for architecture in advancement:
        for seed in SEEDS:
            for fold in FOLDS:
                timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
                print(f"=== STARTING V2-004-D2-{architecture}-F0{fold}-S{seed} at {timestamp} ===")
                subprocess.run(
                    [
                        sys.executable,
                        str(ROOT / "scripts/run_v2_004_fit.py"),
                        "--architecture",
                        architecture,
                        "--stage",
                        "D2",
                        "--outer-fold",
                        str(fold),
                        "--seed",
                        str(seed),
                    ],
                    cwd=ROOT,
                    check=True,
                )
                timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
                print(f"=== FINISHED V2-004-D2-{architecture}-F0{fold}-S{seed} at {timestamp} ===")

    print("ALL_D2_FITS_COMPLETE")


if __name__ == "__main__":
    main()
