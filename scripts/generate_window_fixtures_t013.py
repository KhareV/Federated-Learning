#!/usr/bin/env python3
"""Generate tiny synthetic T013 regression fixtures; never dataset evidence."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests/fixtures/windows"


def main() -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    time = np.arange(2500, dtype=np.float64) / 250.0
    base = np.sin(2 * np.pi * 1.2 * time)
    arrays = np.stack([base * (index + 1) / 7.0 for index in range(7)])
    array_path = FIXTURE_DIR / "window_signals_v1.npy"
    with array_path.open("wb") as handle:
        np.save(handle, arrays, allow_pickle=False)
    metadata = {
        "fixture_origin": "synthetic_engineering_regression",
        "clinical_evidence": False,
        "sample_rate_hz": 250,
        "window_samples": 2500,
        "cases": [
            "ELIGIBLE_NEGATIVE",
            "ELIGIBLE_POSITIVE",
            "EXCLUDE_Q",
            "EXCLUDE_UNMAPPABLE",
            "EXCLUDE_LT5_MAPPABLE_BEATS",
            "DEGRADED_SHORT_GAP",
            "UNUSABLE_LONG_GAP",
        ],
    }
    (FIXTURE_DIR / "window_cases_v1.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("T013 synthetic fixture cache: generated")


if __name__ == "__main__":
    main()
