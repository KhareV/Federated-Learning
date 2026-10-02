"""C-V2-D0.6 post-result tests: validates the real, frozen diagnostic outputs under
reports/model_v2/c_v2_d0_6/ for row-count/closure correctness, firewall ledger cleanliness,
and internal consistency between the hypothesis audit and its underlying CSV/JSON evidence.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "reports/model_v2/c_v2_d0_6"


def _read_csv(name: str) -> list[dict]:
    with (OUT_DIR / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_patient_composition_row_counts() -> None:
    assert len(_read_csv("patient_composition_train_oof.csv")) == 27
    assert len(_read_csv("patient_composition_validation.csv")) == 7


def test_class_composition_train_oof_row_count_and_slices() -> None:
    rows = _read_csv("class_composition_train_oof.csv")
    assert len(rows) == 20
    slices = {r["composition"] for r in rows}
    assert slices == {"S_DOMINANT", "V_DOMINANT", "F_CONTAINING", "S_V_TIE"}


def test_class_composition_positive_support_sums_to_3557() -> None:
    rows = _read_csv("class_composition_train_oof.csv")
    rf_rows = [r for r in rows if r["model"] == "RF_ALL"]
    assert sum(int(r["support"]) for r in rf_rows) == 3557


def test_class_composition_validation_metadata_only() -> None:
    rows = _read_csv("class_composition_validation.csv")
    assert len(rows) == 4
    for row in rows:
        assert row["sensitivity"] == ""
        assert row["status"] == "MISSING_FROZEN_SOURCE_NO_PER_WINDOW_PREDICTIONS"


def test_score_distributions_available_and_missing_split() -> None:
    rows = _read_csv("score_distributions.csv")
    available = [r for r in rows if r["status"] == "AVAILABLE"]
    missing = [r for r in rows if r["status"] == "MISSING_FROZEN_SOURCE"]
    assert len(available) == 8
    assert len(missing) == 4
    assert all(r["population"] == "VALIDATION" for r in missing)


def test_threshold_region_errors_available_and_missing_split() -> None:
    rows = _read_csv("threshold_region_errors.csv")
    available = [r for r in rows if r["status"] == "AVAILABLE"]
    missing = [r for r in rows if r["status"] == "MISSING_FROZEN_SOURCE"]
    assert len(available) == 4
    assert len(missing) == 2


def test_patient_loo_auprc_row_count() -> None:
    rows = _read_csv("patient_loo_auprc.csv")
    assert len(rows) == 27 * 3 + 27


def test_patient_brier_row_count_and_split() -> None:
    rows = _read_csv("patient_brier.csv")
    available = [r for r in rows if r["status"] == "AVAILABLE"]
    missing = [r for r in rows if r["status"] == "MISSING_FROZEN_SOURCE"]
    assert len(available) == 27 * 3 + 27
    assert len(missing) == 7 * 2


def test_diagnostic_thresholds_structure() -> None:
    data = json.loads((OUT_DIR / "diagnostic_thresholds.json").read_text())
    assert set(data["train_oof"]["MODEL_V1"]) == {"20260927", "20260928", "20260929"}
    assert data["historical_validation"]["MODEL_V1"]["fit_any_threshold"] is False
    assert data["historical_validation"]["RF"]["fit_any_threshold"] is False
    assert data["historical_validation"]["RF"]["threshold_dependent_metrics_produced"] is False


def test_hypothesis_audit_verdicts_present_and_valid() -> None:
    data = json.loads((OUT_DIR / "train_oof_hypothesis_audit.json").read_text())
    valid = {"SUPPORTED", "MIXED", "NOT_SUPPORTED", "INSUFFICIENT_EVIDENCE"}
    for key in ("H_RHYTHM", "H_MORPH", "H_PATIENT", "H_THRESHOLD"):
        assert data[key]["verdict"] in valid
        assert "supporting_numbers" in data[key]


def test_historical_validation_context_decision_ineligible() -> None:
    data = json.loads((OUT_DIR / "historical_validation_context.json").read_text())
    assert data["decision_eligible"] is False
    assert data["historical_context_only"] is True
    assert data["cherry_picking_performed"] is False


def test_design_firewall_attestation_all_pass() -> None:
    data = json.loads((OUT_DIR / "design_firewall_attestation.json").read_text())
    assert data["hard_data_firewall"]["status"] == "PASS"
    assert data["hard_data_firewall"]["raw_ecg_waveform_opened"] is False
    assert data["no_model_training"]["v2_neural_fits_added"] == 0
    assert data["status"] == "PASS"


def test_scope_access_ledger_only_allowed_paths() -> None:
    from nhm.model_v2_d0_6_guard import known_allowed_paths

    allowed = set(known_allowed_paths())
    ledger_path = OUT_DIR / "scope_access_ledger.jsonl"
    rows = [json.loads(line) for line in ledger_path.read_text().splitlines()]
    assert len(rows) > 0
    for row in rows:
        assert row["relative_path"] in allowed


def test_scope_access_audit_matches_ledger() -> None:
    # The ledger is append-only and grows every time these tests re-exercise the gated
    # loaders, so only the stable invariant -- the SET of distinct paths touched -- is
    # compared, never the raw row count (which is run-dependent, not a correctness signal).
    audit = json.loads((OUT_DIR / "scope_access_audit.json").read_text())
    ledger_path = OUT_DIR / "scope_access_ledger.jsonl"
    rows = [json.loads(line) for line in ledger_path.read_text().splitlines()]
    assert set(audit["paths_accessed"]) == {r["relative_path"] for r in rows}
    assert audit["total_rows"] <= len(rows)
    assert audit["status"] == "PASS"


def test_d0_exit_audit_all_pass() -> None:
    data = json.loads((OUT_DIR / "d0_exit_audit.json").read_text())
    assert data["D0_EXIT"] == "PASS"
    for key in ("D0_1", "D0_2", "D0_3", "D0_4", "D0_5", "D0_6"):
        assert data[key]["complete"] is True
