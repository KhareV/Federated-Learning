#!/usr/bin/env python3
"""Repeat the frozen T017 fit and require byte-identical semantic artifacts."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from evaluation.calibration import fit_cal_v1  # noqa: E402
from nhm.hashing import hash_file  # noqa: E402


def main() -> None:
    paths = [
        ROOT / "artifacts/CAL_V1.json",
        ROOT / "reports/calibration/calibration_predictions.csv",
        ROOT / "reports/calibration/reliability.json",
        ROOT / "reports/calibration/reliability_diagram.svg",
        ROOT / "reports/t017/threshold_search.json",
        ROOT / "reports/t017/partition_access_audit.json",
        ROOT / "reports/t017/calibration_audit.json",
        ROOT / "reports/t017/reproducibility.json",
    ]
    before = {str(path.relative_to(ROOT)): hash_file(path) for path in paths}
    fit_cal_v1(ROOT)
    after = {str(path.relative_to(ROOT)): hash_file(path) for path in paths}
    if before != after:
        changed = sorted(path for path in before if before[path] != after[path])
        raise RuntimeError(f"CALIBRATION_REPRODUCIBILITY_FAILURE: {changed}")
    print("T017 calibration artifact reproducibility: PASS")


if __name__ == "__main__":
    main()
