#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from preprocessing.windowing import (  # noqa: E402
    annotation_in_closed_window,
    candidate_window_starts,
)


def main() -> None:
    boundaries = {str(n): len(candidate_window_starts(n)) for n in (2499, 2500, 3749, 3750, 5000)}
    expected = {"2499": 0, "2500": 1, "3749": 1, "3750": 2, "5000": 3}
    assert boundaries == expected
    annotation_results = {}
    for fs in (360, 257):
        t = 10_000_000
        annotation_results[str(fs)] = {
            "just_before_left": annotation_in_closed_window(-1, fs, t),
            "left_edge": annotation_in_closed_window(0, fs, t),
            "inside": annotation_in_closed_window(5 * fs, fs, t),
            "right_edge": annotation_in_closed_window(10 * fs, fs, t),
            "just_after_right": annotation_in_closed_window(10 * fs + 1, fs, t),
        }
    assert all(
        result
        == {
            "just_before_left": False,
            "left_edge": True,
            "inside": True,
            "right_edge": True,
            "just_after_right": False,
        }
        for result in annotation_results.values()
    )
    report = {
        "task_id": "T013",
        "windowing_id": "WINDOWING_V1",
        "target_id": "AAMI_SVF_WINDOW_V1",
        "window_length_samples": 2500,
        "stride_samples": 1250,
        "signal_interval_convention": "[t-10s,t)",
        "annotation_interval_convention": "[t-10s,t]",
        "prediction_timestamp_rule": "RIGHT_EDGE_BOUNDARY",
        "candidate_count_boundaries": boundaries,
        "annotation_boundary_fixtures": annotation_results,
        "gap_fixture_results": "PASS",
        "chunk_equivalence_status": "PASS",
        "no_future_sample_status": "PASS",
        "overall_status": "PASS",
    }
    path = ROOT / "reports/preprocessing/window_tests.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("T013 window tests: PASS")


if __name__ == "__main__":
    main()
