"""V2-009 post-access tests: locks the real, frozen CAL_V2 artifact. Fails if the guard
regresses, prediction closure breaks, temperature/threshold reproducibility regresses, or any
status-distinction field (operational_lineage, runtime_acceptance) drifts.
"""

from __future__ import annotations

import json
from pathlib import Path

from models.cal_v2_verify import verify_cal_v2
from nhm.hashing import hash_file
from nhm.model_v2_calibration_guard import read_guard_state

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "reports/model_v2/v2_009"
ARTIFACT_PATH = ROOT / "artifacts/CAL_V2.json"


def _load(name: str) -> dict:
    return json.loads((OUT_DIR / name).read_text(encoding="utf-8"))


def test_guard_completed_exactly_once() -> None:
    state = read_guard_state(ROOT)
    assert state["state"] == "COMPLETED"
    assert state["completion_summary"]["calibration_rows"] == 1080


def test_second_run_guard_blocked() -> None:
    data = _load("second_run_guard_audit.json")
    assert data["status"] == "PASS"
    assert data["second_run_blocked"] is True
    assert data["error_message"] == "V2_CALIBRATION_ALREADY_CONSUMED"


def test_prediction_closure_exact() -> None:
    data = _load("prediction_closure_audit.json")
    assert data["status"] == "PASS"
    assert data["frozen_example_count"] == 1080
    assert data["table_example_count"] == 1080
    assert data["missing"] == 0
    assert data["duplicates"] == 0
    assert data["extra"] == 0
    assert data["both_classes_present"] is True


def test_temperature_fit_valid_and_reproducible() -> None:
    data = _load("temperature_fit.json")
    assert data["status"] == "PASS"
    assert data["optimizer_success"] is True
    assert data["boundary_hit"] is False
    assert data["temperature"] > 0
    assert data["calibrated_nll"] <= data["raw_nll"] + 1e-9
    assert data["absolute_difference"] == 0.0

    repro = _load("reproducibility.json")
    assert repro["status"] == "PASS"
    assert repro["temperature_absolute_difference"] == 0.0
    assert repro["threshold_identical"] is True


def test_threshold_selection_exact_rule() -> None:
    data = _load("threshold_search.json")
    assert data["comparator"] == ">="
    assert data["selection_metric"] == "POOLED_CALIBRATION_WINDOW_F1"
    assert data["tie_policy"] == "HIGHEST_THRESHOLD_AMONG_MAX_F1_V2"
    assert 0.0 <= data["selected_threshold"] <= 1.0


def test_brier_and_ece_reported_both_directions() -> None:
    data = _load("calibration_metrics.json")
    assert data["status"] == "PASS"
    for key in ["raw_nll", "calibrated_nll", "raw_brier", "calibrated_brier",
                "raw_ece", "calibrated_ece"]:
        assert isinstance(data[key], float)


def test_reliability_artifacts_exist_and_bin_correctly() -> None:
    data = _load("reliability.json")
    assert len(data["raw"]) == 10
    assert len(data["temperature_scaled"]) == 10
    assert (OUT_DIR / "reliability_diagram.svg").exists()
    svg = (OUT_DIR / "reliability_diagram.svg").read_text(encoding="utf-8")
    assert "MIT-BIH" in svg
    assert "calibration partition" in svg.lower()
    assert "research-only" in svg.lower()


def test_cal_v2_artifact_status_distinction_fields_exact() -> None:
    artifact = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    assert artifact["calibration_id"] == "CAL_V2"
    assert artifact["status"] == "FROZEN"
    assert artifact["model_id"] == "MODEL_V2_FINAL"
    assert artifact["fit_partition"] == "CALIBRATION"
    assert artifact["calibration_domain"] == "MIT-BIH-v1.0.0"
    assert artifact["calibration_patient_count"] == 3
    assert artifact["calibration_window_count"] == 1080
    assert artifact["positive_window_count"] == 367
    assert artifact["negative_window_count"] == 713
    assert artifact["threshold_comparator"] == ">="
    assert artifact["threshold_tie_policy"] == "HIGHEST_THRESHOLD_AMONG_MAX_F1_V2"
    assert artifact["internal_test_accessed"] is False
    assert artifact["external_data_accessed"] is False
    assert artifact["operational_lineage"] == "MODEL_V1"
    assert artifact["runtime_acceptance"] == "NOT_EVALUATED"


def test_cal_v2_verifier_passes_on_real_artifact() -> None:
    result = verify_cal_v2(ROOT)
    assert result["status"] == "PASS"
    assert result["model_v2_final_verification"]["status"] == "PASS"


def test_method_immutability_since_method_commit() -> None:
    data = _load("method_immutability_audit.json")
    assert data["status"] == "PASS"
    assert data["all_unchanged"] is True


def test_tamper_tests_all_pass() -> None:
    data = _load("tamper_test_results.json")
    assert data["status"] == "PASS"
    assert data["all_detected"] is True
    assert data["canonical_artifact_mutated"] is False


def test_v1_operational_preservation() -> None:
    data = _load("v1_operational_preservation.json")
    assert data["status"] == "PASS"
    assert data["cal_v1_present_and_unchanged"] is True
    assert data["v1_runtime_defaults_touched"] is False


def test_upstream_immutability() -> None:
    data = _load("upstream_immutability_audit.json")
    assert data["status"] == "PASS"
    assert data["changed_count"] == 0


def test_partition_access_zero_elsewhere() -> None:
    data = _load("partition_access_audit.json")
    assert data["status"] == "PASS"
    for key in ["TRAIN", "VALIDATION", "INTERNAL_TEST", "INCART", "NSTDB", "BIDMC"]:
        assert data[key] == 0
    assert data["CALIBRATION"] == 1080


def test_search_budget_unchanged() -> None:
    data = _load("search_budget.json")
    assert data["status"] == "PASS"
    assert data["cumulative"] == 71
    assert data["v2_009_new_neural_fits"] == 0


def test_run_manifest_and_artifact_hashes_valid() -> None:
    manifest = _load("run_manifest.json")
    assert manifest["checkpoint_id"] == "V2-009"
    assert manifest["cal_v2_frozen"] is True
    assert manifest["model_v2_final_changed"] is False
    assert manifest["operational_lineage"] == "MODEL_V1"
    assert manifest["runtime_acceptance"] == "NOT_EVALUATED"
    hashes = _load("artifact_hashes.json")
    for rel_path, expected in hashes["artifacts"].items():
        assert hash_file(ROOT / rel_path) == expected
