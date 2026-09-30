from __future__ import annotations

import csv
import inspect
import json
from pathlib import Path

from evaluation.bidmc_context import verify
from preprocessing.context_quality import estimate_ecg_rate, estimate_ppg_rate

ROOT = Path(__file__).resolve().parents[1]


def test_frozen_context_result_verifies_and_has_no_disease_metrics() -> None:
    assert verify(ROOT)["status"] == "PASS"
    report = json.loads((ROOT / "reports/bidmc_multimodal_engineering.json").read_text())
    assert report["no_AAMI_SVF_target"] is True
    assert report["no_arrhythmia_model_use"] is True
    assert "AUPRC" not in report and "sensitivity" not in report


def test_bidmc19_spo2_is_unavailable_without_dropping_context() -> None:
    with (ROOT / "reports/t021/bidmc_context_rows.csv").open(newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row["record_id"] == "bidmc19"]
    assert rows
    assert all(row["spo2_valid"] == "false" for row in rows)
    assert all(row["spo2_provenance"] == "SOURCE_CHANNEL_UNAVAILABLE" for row in rows)
    assert all(row["ppg_context_available"] == "true" for row in rows)


def test_reference_values_cannot_enter_detector_interfaces() -> None:
    assert set(inspect.signature(estimate_ppg_rate).parameters) == {
        "values",
        "short_gap_present",
        "long_gap_present",
    }
    assert set(inspect.signature(estimate_ecg_rate).parameters) == {"values"}


def test_reproducibility_and_alignment_reports_pass() -> None:
    reproduction = json.loads((ROOT / "reports/t021/reproducibility.json").read_text())
    alignment = json.loads((ROOT / "reports/t021/alignment_audit.json").read_text())
    assert reproduction["context_rows_identical"] is True
    assert reproduction["engineering_metrics_identical"] is True
    assert alignment["overall_status"] == "PASS"
    assert alignment["future_samples_used"] is False
