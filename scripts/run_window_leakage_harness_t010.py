#!/usr/bin/env python3
"""T010: synthetic-only window-manifest leakage harness validation.

Real MIT-BIH windows do not exist yet (T013 owns real window construction). This script
proves `evaluation.leakage_audit.audit_window_manifest` correctly accepts a clean synthetic
window manifest and correctly rejects each adversarial case, using only provenance metadata
(no waveform arrays). It must never be cited as evidence about real window distributions --
`reports/splits/window_audit.json` states `audit_mode: SYNTHETIC_HARNESS_VALIDATION` and
`real_window_count: 0` explicitly.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluation.leakage_audit import WindowAuditRow, audit_window_manifest  # noqa: E402

REPORT_DIR = ROOT / "reports/splits"

# A tiny synthetic frozen-split lookup: record_id -> (participant_group_id, partition).
SPLIT_LOOKUP: dict[str, tuple[str, str]] = {
    "100": ("MITDB_P100", "TRAIN"),
    "101": ("MITDB_P101", "TRAIN"),
    "106": ("MITDB_P106", "VALIDATION"),
    "201": ("MITDB_P201_202", "VALIDATION"),
    "202": ("MITDB_P201_202", "VALIDATION"),
    "210": ("MITDB_P210", "CALIBRATION"),
}
ELIGIBLE_RECORD_IDS = list(SPLIT_LOOKUP)


def _clean_manifest() -> list[WindowAuditRow]:
    """A valid synthetic manifest: legitimate within-partition overlap on 100 is expected and
    must not be flagged; every row correctly inherits its record's frozen partition/group."""
    return [
        WindowAuditRow("w1", "MITDB_P100", "100", "TRAIN", 0, 3600, "h1"),
        WindowAuditRow("w2", "MITDB_P100", "100", "TRAIN", 1800, 5400, "h2"),
        WindowAuditRow("w3", "MITDB_P101", "101", "TRAIN", 0, 3600, "h3"),
        WindowAuditRow("w4", "MITDB_P106", "106", "VALIDATION", 0, 3600, "h4"),
        WindowAuditRow("w5", "MITDB_P201_202", "201", "VALIDATION", 0, 3600, "h5"),
        WindowAuditRow("w6", "MITDB_P201_202", "202", "VALIDATION", 0, 3600, "h6"),
        WindowAuditRow("w7", "MITDB_P210", "210", "CALIBRATION", 0, 3600, "h7"),
    ]


def _adversarial_cases() -> dict[str, list[WindowAuditRow]]:
    clean = _clean_manifest()
    return {
        "same_patient_across_train_and_test": [
            WindowAuditRow("a1", "MITDB_P100", "100", "TRAIN", 0, 3600, "ha1"),
            WindowAuditRow("a2", "MITDB_P100", "100", "INTERNAL_TEST", 3600, 7200, "ha2"),
        ],
        "same_record_across_train_and_validation": [
            WindowAuditRow("b1", "MITDB_P101", "101", "TRAIN", 0, 3600, "hb1"),
            WindowAuditRow("b2", "MITDB_P101", "101", "VALIDATION", 3600, 7200, "hb2"),
        ],
        "identical_window_hash_across_partitions": [
            WindowAuditRow("c1", "MITDB_P100", "100", "TRAIN", 0, 3600, "hdup"),
            WindowAuditRow("c2", "MITDB_P106", "106", "VALIDATION", 0, 3600, "hdup"),
        ],
        "overlapping_source_intervals_across_partitions": [
            WindowAuditRow("d1", "MITDB_P201_202", "201", "VALIDATION", 0, 3600, "hd1"),
            WindowAuditRow("d2", "MITDB_P201_202", "201", "TRAIN", 1800, 5400, "hd2"),
        ],
        "wrong_record_to_partition_inheritance": [
            WindowAuditRow("e1", "MITDB_P100", "100", "VALIDATION", 0, 3600, "he1"),
        ],
        "excluded_record_entering_manifest": [
            WindowAuditRow("f1", "MITDB_P102", "102", "TRAIN", 0, 3600, "hf1"),
        ],
        "duplicate_example_ids": [
            WindowAuditRow("g1", "MITDB_P100", "100", "TRAIN", 0, 3600, "hg1"),
            WindowAuditRow("g1", "MITDB_P101", "101", "TRAIN", 0, 3600, "hg2"),
        ],
        "clean_manifest_control": clean,
    }


def run() -> dict[str, Any]:
    cases = _adversarial_cases()
    results = {}
    for name, rows in cases.items():
        outcome = audit_window_manifest(rows, SPLIT_LOOKUP, ELIGIBLE_RECORD_IDS)
        expected_status = "PASS" if name == "clean_manifest_control" else "FAIL"
        results[name] = {
            "expected_status": expected_status,
            "actual_status": outcome["status"],
            "matches_expectation": outcome["status"] == expected_status,
            "errors": outcome["errors"],
        }

    all_correct = all(row["matches_expectation"] for row in results.values())
    report = {
        "audit_mode": "SYNTHETIC_HARNESS_VALIDATION",
        "real_window_count": 0,
        "real_window_manifest_available": False,
        "real_window_audit_deferred_to": "T013",
        "cases": results,
        "synthetic_harness_validation": "PASS" if all_correct else "FAIL",
        "overall_status": "PASS" if all_correct else "FAIL",
    }
    return report


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = run()
    output_path = REPORT_DIR / "window_audit.json"
    temporary = output_path.with_suffix(f"{output_path.suffix}.tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(output_path)

    print(f"T010 synthetic window leakage harness: {report['overall_status']}")
    if report["overall_status"] != "PASS":
        raise RuntimeError(f"window leakage harness case(s) failed: {report['cases']}")


if __name__ == "__main__":
    main()
