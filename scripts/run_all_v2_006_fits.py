#!/usr/bin/env python3
"""V2-006: run the predeclared challenger matrix -- MODEL_V2_TCN_MEANMAX x 5 folds x 3 seeds
= exactly 15 fits (seed 20260927 folds 0-4, then 20260928 folds 0-4, then 20260929 folds
0-4). No CONTROL fits (reused read-only from V2-004). One fresh Python process per fit
(subprocess), sequential, deterministic order; order never changes based on intermediate
performance.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEEDS = (20260927, 20260928, 20260929)
FOLDS = (0, 1, 2, 3, 4)


def main() -> None:
    for seed in SEEDS:
        for fold in FOLDS:
            timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            print(f"=== STARTING V2-006-OPT-CORR-F{fold:02d}-S{seed} at {timestamp} ===")
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/run_v2_006_fit.py"),
                    "--outer-fold",
                    str(fold),
                    "--seed",
                    str(seed),
                ],
                cwd=ROOT,
                check=True,
            )
            timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            print(f"=== FINISHED V2-006-OPT-CORR-F{fold:02d}-S{seed} at {timestamp} ===")

    print("ALL_V2_006_FITS_COMPLETE")


if __name__ == "__main__":
    main()
