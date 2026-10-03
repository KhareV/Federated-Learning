"""V2-010 post-access results tests: guard COMPLETED states, exact closure against frozen
V1 row counts, both hard runtime-acceptance guards, independent-verification agreement, and
every Section 41-44 integrity audit.
"""

from __future__ import annotations

import json
from pathlib import Path

from nhm.hashing import hash_file
from nhm.model_v2_second_look_guard import DATASETS, read_guard_state

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_010"


def _load(name: str) -> dict:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def test_all_three_guards_completed() -> None:
    for dataset in DATASETS:
        state = read_guard_state(ROOT, dataset)
        assert state["state"] == "COMPLETED"


def test_internal_test_closure_exact() -> None:
    audit = _load("internal_access_audit.json")
    assert audit["closure_exact"] is True
    assert audit["row_count"] == 2157
    assert audit["positive_count"] == 1156
    assert audit["negative_count"] == 1001


def test_incart_closure_exact() -> None:
    audit = _load("incart_access_audit.json")
    assert audit["closure_exact"] is True
    assert audit["row_count"] == 26864
    assert audit["patient_cluster_count"] == 32


def test_nstdb_closure_exact() -> None:
    audit = _load("nstdb_access_audit.json")
    assert audit["closure_exact"] is True
    assert audit["row_count"] == 4320
    assert audit["pair_id_count"] == 720
    assert audit["snr_levels"] == [24, 18, 12, 6, 0, -6]


def test_v2_predictions_never_reuse_v1_model_or_calibration_id() -> None:
    import csv

    with (OUT / "internal_v2_predictions.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert all(row["model_id"] == "MODEL_V2_FINAL" for row in rows)
    assert all(row["calibration_id"] == "CAL_V2" for row in rows)


def test_incart_comparison_hard_gate_pass() -> None:
    data = _load("incart_comparison.json")
    assert data["role"] == "HARD_GATE"
    assert data["INCART_AUROC_RUNTIME_GUARD_PASS"] is True
    assert data["auroc_delta_ci_lower_95"] >= 0.0


def test_nstdb_comparison_hard_gate_pass_no_dropped_snr() -> None:
    data = _load("nstdb_comparison_summary.json")
    assert data["role"] == "HARD_GATE"
    assert data["NSTDB_NO_COLLAPSE_PASS"] is True
    assert set(data["delta_auprc_by_snr"]) == {"24", "18", "12", "6", "0", "-6"}
    assert all(value >= -1e-12 for value in data["delta_auprc_by_snr"].values())


def test_internal_test_descriptive_only_not_a_hard_gate() -> None:
    data = _load("internal_comparison.json")
    assert data["role"] == "DESCRIPTIVE_ONLY_NOT_A_HARD_GATE"


def test_runtime_acceptance_decision_accepted_with_correct_reasoning() -> None:
    data = _load("runtime_acceptance_decision.json")
    assert data["MODEL_V2_RUNTIME_ACCEPTED"] == "ACCEPTED"
    assert data["method_integrity_pass"] is True
    assert data["INCART_AUROC_RUNTIME_GUARD_PASS"] is True
    assert data["NSTDB_NO_COLLAPSE_PASS"] is True
    assert data["internal_test_participates_in_decision"] is False
    assert data["operational_lineage"] == "MODEL_V1"
    assert data["subjective_override_applied"] is False


def test_independent_verification_agrees() -> None:
    data = _load("independent_verification.json")
    assert data["status"] == "PASS"
    assert data["decision_agreement"] is True
    assert data["independent_decision"] == data["official_decision"] == "ACCEPTED"


def test_method_immutable_post_access() -> None:
    data = _load("method_immutability_audit.json")
    assert data["status"] == "PASS"
    assert data["all_scientific_files_unchanged"] is True


def test_protected_upstream_artifacts_unmutated() -> None:
    data = _load("protected_artifact_audit.json")
    assert data["status"] == "PASS"
    for relative, expected in data["artifacts"].items():
        assert hash_file(ROOT / relative) == expected


def test_second_invocation_blocked_for_all_three() -> None:
    data = _load("second_run_guard_audit.json")
    assert data["status"] == "PASS"
    assert all(data["blocked"].values())


def test_reproducibility_bit_exact() -> None:
    data = _load("reproducibility.json")
    assert data["status"] == "PASS"
    assert data["identical_on_rerun"] is True


def test_run_manifest_consistent_with_decision() -> None:
    manifest = _load("run_manifest.json")
    decision = _load("runtime_acceptance_decision.json")
    assert manifest["status"] == "PASS"
    assert manifest["MODEL_V2_RUNTIME_ACCEPTED"] == decision["MODEL_V2_RUNTIME_ACCEPTED"]
    assert manifest["operational_lineage"] == "MODEL_V1"
    assert manifest["official_validation_reopened"] is False
    assert manifest["calibration_reopened"] is False
    assert manifest["v1_inference_rerun"] is False
    assert manifest["v2_retrained"] is False


def test_artifact_hashes_self_consistent() -> None:
    data = _load("artifact_hashes.json")
    for relative, expected in data["artifacts"].items():
        assert hash_file(ROOT / relative) == expected
