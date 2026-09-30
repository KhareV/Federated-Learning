from __future__ import annotations

import csv
import json
from pathlib import Path

from evaluation.bidmc_context_v2 import (
    INHERITED_FIELDS,
    load_t021_rows,
    verify_context_lock,
    verify_rows,
)

ROOT = Path(__file__).resolve().parents[1]


def _v2_rows() -> list[dict[str, str]]:
    with (ROOT / "reports/c021_hr_b/bidmc_context_rows_v2.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        return list(csv.DictReader(handle))


def test_frozen_context_lock_and_guardrails_verify() -> None:
    result = verify_context_lock(ROOT)
    assert result["status"] == "PASS"
    assert result["metrics"]["coverage"] >= 0.90
    assert result["metrics"]["median_absolute_error_bpm"] <= 10.0
    assert result["metrics"]["mae_bpm"] <= 20.0


def test_all_53_records_and_exact_t021_row_closure() -> None:
    old = load_t021_rows(ROOT)
    new = _v2_rows()
    assert len({row["record_id"] for row in new}) == 53
    assert [(row["record_id"], row["timestamp_us"]) for row in old] == [
        (row["record_id"], row["timestamp_us"]) for row in new
    ]
    assert len(new) == len({(row["record_id"], row["timestamp_us"]) for row in new})


def test_all_inherited_fields_are_byte_equal() -> None:
    for old, new in zip(load_t021_rows(ROOT), _v2_rows(), strict=True):
        assert {field: old[field] for field in INHERITED_FIELDS} == {
            field: new[field] for field in INHERITED_FIELDS
        }


def test_frozen_rows_recompute_main_metrics() -> None:
    recomputed = verify_rows(ROOT)
    report = json.loads(
        (ROOT / "reports/bidmc_multimodal_engineering_v2.json").read_text(encoding="utf-8")
    )
    assert recomputed["metrics"] == report["V2_ECG_HR_vs_HR"]
    assert recomputed["agreement"] == report["ECG_PPG_V2_agreement"]
    assert recomputed["warning"] == report["natural_rate_warning_audit"]


def test_policy_is_descriptive_and_unchanged() -> None:
    report = json.loads(
        (ROOT / "reports/bidmc_multimodal_engineering_v2.json").read_text(encoding="utf-8")
    )
    warning = report["natural_rate_warning_audit"]
    assert warning["tolerance_bpm"] == 20.0
    assert warning["duration_seconds"] == 10
    assert warning["policy_changed_from_result"] is False
    assert report["alert_policy"]["changed"] is False
