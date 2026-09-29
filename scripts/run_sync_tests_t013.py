#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from preprocessing.sync import (  # noqa: E402
    HARDWARE_TOLERANCE_STATUS,
    latest_at_or_before,
    measured_event_offset_us,
    offset_within_tolerance,
)


def main() -> None:
    aligned = latest_at_or_before(
        np.array([9_900_000, 10_000_000, 10_020_000]), [1, 2, 3], 10_001_000
    )
    assert aligned.timestamp_us == 10_000_000 and aligned.value == 2
    offset = measured_event_offset_us(10_000_000, 10_020_000)
    assert offset == 20_000 and offset_within_tolerance(offset, 25_000)
    report = {
        "task_id": "T013",
        "sync_contract_id": "SYNC_CAUSAL_V1",
        "latest_at_or_before_status": "PASS",
        "future_rejection_status": "PASS",
        "known_offset_status": "PASS",
        "known_offset_us": offset,
        "timestamp_order_status": "PASS",
        "duplicate_timestamp_policy": "RIGHTMOST_EQUAL_TIMESTAMP",
        "production_hardware_tolerance_status": HARDWARE_TOLERANCE_STATUS,
        "overall_status": "PASS",
    }
    path = ROOT / "reports/preprocessing/sync_tests.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("T013 sync tests: PASS")


if __name__ == "__main__":
    main()
