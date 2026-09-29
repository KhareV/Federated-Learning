#!/usr/bin/env python3
"""T012: run the GAP_POLICY_V1 synthetic proofs and emit reports/preprocessing/gap_tests.json
-- the canonical T012 gap-policy evidence artifact.

Software policy correctness only, over known-rate synthetic/public source-index arithmetic.
Explicitly NOT real-hardware evidence -- T004 remains BLOCKED_HARDWARE and no claim about
real ESP32/AD8232/MAX30102 timing/gap behavior is made here.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from preprocessing.gaps import (  # noqa: E402
    GAP_KIND_LONG,
    GAP_KIND_SHORT,
    GAP_POLICY_ID,
    GapController,
    NonMonotonicSourceIndexError,
    is_short_gap,
)

REPORT_PATH = ROOT / "reports/preprocessing/gap_tests.json"

BOUNDARY_CASES = [
    (250, 25, "SHORT"), (250, 26, "LONG"),
    (360, 36, "SHORT"), (360, 37, "LONG"),
    (257, 25, "SHORT"), (257, 26, "LONG"),
    (100, 10, "SHORT"), (100, 11, "LONG"),
    (125, 12, "SHORT"), (125, 13, "LONG"),
]


def _check_boundary_cases() -> dict[str, Any]:
    rows = []
    all_correct = True
    for source_rate_hz, missing_count, expected in BOUNDARY_CASES:
        observed = "SHORT" if is_short_gap(missing_count, source_rate_hz) else "LONG"
        correct = observed == expected
        all_correct = all_correct and correct
        rows.append(
            {
                "source_rate_hz": source_rate_hz,
                "missing_count": missing_count,
                "duration_ms": round(1000.0 * missing_count / source_rate_hz, 6),
                "expected_class": expected,
                "observed_class": observed,
                "correct": correct,
            }
        )
    return {"status": "PASS" if all_correct else "FAIL", "cases": rows}


def _check_short_gap() -> dict[str, Any]:
    gc = GapController(250)
    gc.process(np.array([123.456789]), np.array([0]))
    out = gc.process(np.array([999.0]), np.array([26]))
    fills = out.chunks[0].values[out.chunks[0].gap_mask == 1]
    exact_zoh = bool(np.all(fills == 123.456789)) and fills.size == 25
    fill_mask_ok = list(out.chunks[0].gap_mask) == [1] * 25 + [0]
    no_segment_break = out.chunks[0].starts_new_segment is False

    gc_a = GapController(250)
    gc_a.process(np.array([7.0]), np.array([0]))
    out_a = gc_a.process(np.array([1.0]), np.array([26]))
    gc_b = GapController(250)
    gc_b.process(np.array([7.0]), np.array([0]))
    out_b = gc_b.process(np.array([1e9]), np.array([26]))
    fills_a = out_a.chunks[0].values[out_a.chunks[0].gap_mask == 1]
    fills_b = out_b.chunks[0].values[out_b.chunks[0].gap_mask == 1]
    post_gap_independence = bool(np.array_equal(fills_a, fills_b))

    all_ok = all([exact_zoh, fill_mask_ok, no_segment_break, post_gap_independence])
    status = "PASS" if all_ok else "FAIL"
    return {
        "status": status,
        "exact_zoh": exact_zoh,
        "fill_mask": fill_mask_ok,
        "post_gap_independence": post_gap_independence,
        "no_segment_break": no_segment_break,
    }


def _check_long_gap() -> dict[str, Any]:
    gc = GapController(250)
    gc.process(np.array([5.0]) * 0 + 1e6, np.array([0]))
    out = gc.process(np.array([0.001]), np.array([27]))
    event = out.events[0]
    no_fill = event.fill_count == 0
    segment_break = event.next_segment_id == event.previous_segment_id + 1
    unusable = event.quality_requirement == "UNUSABLE"

    fresh = GapController(250)
    fresh_out = fresh.process(np.array([0.001]), np.array([0]))
    same_first_value = out.chunks[0].values[0] == fresh_out.chunks[0].values[0]

    status = "PASS" if all([no_fill, segment_break, unusable, same_first_value]) else "FAIL"
    return {
        "status": status,
        "no_fill": no_fill,
        "segment_break": segment_break,
        "unusable_spanning_requirement": unusable,
        "fresh_segment_equivalence": bool(same_first_value),
    }


def _check_future_append() -> dict[str, Any]:
    gc = GapController(250)
    gc.process(np.array([5.0]), np.array([0]))
    out_before = gc.process(np.array([6.0]), np.array([11]))
    fills_before = out_before.chunks[0].values[out_before.chunks[0].gap_mask == 1].copy()
    gc.process(np.array([1e9, -1e9]), np.array([12, 13]))
    status = "PASS" if bool(np.all(fills_before == 5.0)) else "FAIL"
    return {"status": status}


def _check_cross_chunk_equivalence() -> dict[str, Any]:
    values = np.array([1.0, 2.0, 3.0])
    indices = np.array([0, 1, 40])

    gc_single = GapController(250)
    out_single = gc_single.process(values, indices)
    gc_split = GapController(250)
    out_a = gc_split.process(values[:2], indices[:2])
    out_b = gc_split.process(values[2:], indices[2:])

    matched = out_single.events[0] == (out_a.events + out_b.events)[0]
    return {"status": "PASS" if matched else "FAIL"}


def _check_multiple_gaps() -> dict[str, Any]:
    def run() -> tuple[list[str], list[int]]:
        gc = GapController(250)
        vals = np.array([0.0, 1.0, 2.0, 3.0, 4.0, 5.0])
        idx = np.array([0, 1, 12, 23, 53, 59])
        out = gc.process(vals, idx)
        return [e.gap_kind for e in out.events], [c.segment_id for c in out.chunks]

    kinds_a, segments_a = run()
    kinds_b, segments_b = run()
    expected_kinds = [GAP_KIND_SHORT, GAP_KIND_SHORT, GAP_KIND_LONG, GAP_KIND_SHORT]
    status = "PASS" if kinds_a == kinds_b == expected_kinds and segments_a == segments_b else "FAIL"
    return {"status": status, "kinds": kinds_a, "segments": segments_a}


def _check_nonmonotonic_rejection() -> dict[str, Any]:
    gc = GapController(250)
    gc.process(np.array([1.0]), np.array([10]))
    try:
        gc.process(np.array([2.0]), np.array([5]))
        rejected = False
    except NonMonotonicSourceIndexError:
        rejected = True
    return {"status": "PASS" if rejected else "FAIL"}


def build_report() -> dict[str, Any]:
    boundary = _check_boundary_cases()
    short_gap = _check_short_gap()
    long_gap = _check_long_gap()
    future_append = _check_future_append()
    cross_chunk = _check_cross_chunk_equivalence()
    multiple_gaps = _check_multiple_gaps()
    nonmonotonic = _check_nonmonotonic_rejection()

    overall_status = (
        "PASS"
        if all(
            check["status"] == "PASS"
            for check in (
                boundary, short_gap, long_gap, future_append, cross_chunk, multiple_gaps,
                nonmonotonic,
            )
        )
        else "FAIL"
    )

    return {
        "task_id": "T012",
        "gap_policy_id": GAP_POLICY_ID,
        "boundary_cases": boundary,
        "short_gap": short_gap,
        "long_gap": long_gap,
        "future_append_status": future_append["status"],
        "cross_chunk_equivalence": cross_chunk["status"],
        "multiple_gap_status": multiple_gaps["status"],
        "nonmonotonic_rejection": nonmonotonic["status"],
        "hardware_validation_scope": {
            "software_policy_only": True,
            "real_device_evidence": False,
        },
        "overall_status": overall_status,
    }


def main() -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report = build_report()
    temporary = REPORT_PATH.with_suffix(f"{REPORT_PATH.suffix}.tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(REPORT_PATH)
    print(f"T012 gap policy tests: {report['overall_status']}")
    if report["overall_status"] != "PASS":
        raise RuntimeError(f"gap policy checks failed: {report}")


if __name__ == "__main__":
    main()
