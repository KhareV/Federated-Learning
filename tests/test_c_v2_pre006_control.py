"""C-V2-PRE006-CONTROL tests: locks the future-registry-vs-active-Protocol-V2 reconciliation.
Fails if either frozen protocol changes, the obsolete V2-008 promotion text reappears, any
future task/gate status regresses, V2-005/V2G4 regress, MODEL_V2_FINAL/CAL_V2 appear, any
waveform/data access occurs, the search-budget authority finding disagrees silently, a
conditional skip is treated globally as PASS, or V2-007 cannot resolve the real V2-005
prerequisite via the new resolver.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
AUDIT_DIR = ROOT / "reports/model_v2/c_v2_pre006_control"


def _load(name: str) -> dict:
    return json.loads((AUDIT_DIR / name).read_text(encoding="utf-8"))


def _registry() -> tuple[dict, dict]:
    with (ROOT / "manifests/model_v2/task_registry_v1.csv").open(newline="") as handle:
        tasks = {row["task_id"]: row for row in csv.DictReader(handle)}
    with (ROOT / "manifests/model_v2/gate_registry_v1.csv").open(newline="") as handle:
        gates = {row["gate_id"]: row["status"] for row in csv.DictReader(handle)}
    return tasks, gates


def test_protocol_v1_and_v2_locks_unchanged() -> None:
    assert (
        hash_file(ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V1.lock.json")
        == "4dadf234afd239539240e4e2662b1fdf54e5154400b1ea4e0c14c8e4107e2eb7"
    )
    assert (
        hash_file(ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V2.lock.json")
        == "f300473a84d5ba1ceda1da722c4b2745856b43b4c1353e5af8cb2e8a3f878f81"
    )


def test_v2_008_no_longer_contains_obsolete_promotion_gate() -> None:
    tasks, _ = _registry()
    notes = tasks["V2-008"]["notes"]
    assert "0.5628608" not in notes
    assert "0.5628607838787021" not in notes
    assert "0.646" in notes
    assert "lower-95%-CI" in notes or "lower_95_ci" in notes.lower().replace("-", "_")
    # V2-008 has since legitimately run and passed; this test only guards the content above.
    assert tasks["V2-008"]["status"] in {"NOT_STARTED", "PASS"}


def test_known_registry_contradiction_was_confirmed_and_corrected() -> None:
    data = _load("known_registry_contradiction.json")
    assert data["classification"] == "CONTRADICTION_CONFIRMED"
    assert data["stale_text_present_in_registry_before_correction"] is True
    assert "0.5628608" in data["registry_current_text_before_correction"]


def test_v2_007_wording_reflects_frozen_protocol() -> None:
    # This checkpoint (C-V2-PRE006-CONTROL) originally asserted an official-VALIDATION-for-
    # checkpoint-selection claim; C-V2-PRE006-CLOSEOUT corrected it one way, and
    # C-V2-PRE006-AUTHORITY-REPAIR has since corrected it again (a dedicated TRAIN-only final
    # inner split, per the self-contained MODEL_V2 authority contract). The exact wording has
    # now legitimately changed twice (and V2-007 has since legitimately run and passed); this
    # test only guards that it still references its governing protocol, not any specific
    # superseded phrasing or status.
    tasks, _ = _registry()
    notes = tasks["V2-007"]["notes"]
    assert "MODEL_V2_RESEARCH_PROTOCOL_V3" in notes
    assert tasks["V2-007"]["status"] in {"NOT_STARTED", "PASS"}


def test_future_task_and_gate_rows_all_not_started() -> None:
    task_summary = _load("future_task_semantic_summary.json")
    gate_summary = _load("future_gate_semantic_summary.json")
    assert task_summary["status"] == "PASS"
    assert task_summary["all_future_tasks_not_started"] is True
    assert task_summary["unresolved_contradictions"] == []
    assert gate_summary["status"] == "PASS"
    assert gate_summary["all_future_gates_not_started"] is True
    assert gate_summary["unresolved_contradictions"] == []

    # V2-006..V2-011 and V2G5..V2G10 have since legitimately run and passed (this checkpoint
    # ran strictly before them); every other future task/gate must still be exactly NOT_STARTED.
    tasks, gates = _registry()
    for n in range(6, 15):
        task_id = f"V2-{n:03d}"
        if task_id in {"V2-006", "V2-007", "V2-008", "V2-009", "V2-010", "V2-011"}:
            assert tasks[task_id]["status"] in {"NOT_STARTED", "PASS"}
        else:
            assert tasks[task_id]["status"] == "NOT_STARTED"
    for n in range(5, 14):
        gate_id = f"V2G{n}"
        if gate_id in {"V2G5", "V2G6", "V2G7", "V2G8", "V2G9", "V2G10"}:
            assert gates[gate_id] in {"NOT_STARTED", "PASS"}
        else:
            assert gates[gate_id] == "NOT_STARTED"


def test_v2_005_and_v2g4_not_regressed() -> None:
    tasks, gates = _registry()
    assert tasks["V2-005"]["status"] == "SKIPPED_BY_PROTOCOL"
    assert gates["V2G4"] == "PASS"


def test_v2_006_not_regressed() -> None:
    # This checkpoint ran strictly before V2-006; V2-006 has since legitimately run and
    # passed -- this test only guards against an invalid status value.
    tasks, _ = _registry()
    assert tasks["V2-006"]["status"] in {"NOT_STARTED", "PASS"}


def test_model_v2_final_and_cal_v2_do_not_exist() -> None:
    data = _load("component_registry_semantic_audit.json")
    assert data["status"] == "PASS"
    assert data["checks"]["MODEL_V2_FINAL_not_frozen"] is True
    assert data["checks"]["CAL_V2_not_frozen"] is True
    assert data["checks"]["MODEL_V2_HYBRID_does_not_exist"] is True
    assert data["checks"]["MODEL_V2_AUX_FEATURES_V1_still_conditional_reserved"] is True


def test_no_data_or_training_occurred() -> None:
    data = _load("no_data_no_training_audit.json")
    assert data["status"] == "PASS"
    for key in [
        "neural_fits_added", "classical_fits_added", "waveform_reads",
        "model_inference_runs", "checkpoints_created", "feature_extraction_runs",
        "bootstrap_results_generated", "new_scientific_metrics",
    ]:
        assert data[key] == 0
    for key in [
        "official_validation_accessed", "calibration_accessed", "internal_test_accessed",
        "incart_accessed", "nstdb_accessed", "bidmc_accessed",
    ]:
        assert data[key] is False


def test_search_budget_authority_finding_not_silently_disagreeing() -> None:
    data = _load("search_budget_authority_audit.json")
    assert data["status"] == "PASS"
    assert data["protocol_v2_global_neural_fit_cap_field_exists"] is False
    assert data["current_completed_v2_neural_fits"] == 50
    assert data["v2_005_reported_cap"] == data["v2_004_reported_cap"] == 100
    assert data["cap_90_mentioned_anywhere_in_repo"] is False


def test_conditional_skip_not_treated_globally_as_pass() -> None:
    from nhm.model_v2_prerequisite_resolver import is_v2_prerequisite_resolved

    # An undeclared/unevidenced SKIPPED_BY_PROTOCOL task must not resolve.
    assert (
        is_v2_prerequisite_resolved(
            "SKIPPED_BY_PROTOCOL",
            task_predeclares_conditional_skip=False,
            has_frozen_disposition_evidence=False,
        )
        is False
    )


def test_v2_007_resolves_real_v2_005_prerequisite_via_resolver() -> None:
    from nhm.model_v2_prerequisite_resolver import v2_005_prerequisite_resolved_for_v2_007

    assert v2_005_prerequisite_resolved_for_v2_007() is True


def test_conditional_prerequisite_integration_performed() -> None:
    data = _load("conditional_prerequisite_integration_audit.json")
    assert data["status"] == "PASS"
    assert data["integration_performed"] is True
    assert data["canonical_t_task_prerequisite_semantics_changed"] is False
    assert data["v2_005_resolves_v2_007_prerequisite"] is True
    assert data["arbitrary_fake_skipped_task_rejected"] is True


def test_upstream_scientific_locks_unchanged() -> None:
    data = _load("upstream_identity_audit.json")
    assert data["status"] == "PASS"
    for check in data["checks"].values():
        if isinstance(check, dict) and "unchanged" in check:
            assert check["unchanged"] is True


def test_registry_structural_validation_exact() -> None:
    data = _load("registry_structural_validation.json")
    assert data["status"] == "PASS"
    for file_result in data["files"].values():
        assert file_result["status"] == "PASS"
        assert file_result["misaligned_rows"] == []
        assert file_result["ids_unique"] is True


def test_protocol_internal_consistency_no_material_contradiction() -> None:
    data = _load("protocol_v2_internal_consistency.json")
    assert data["status"] == "PASS"
    assert data["material_contradiction_between_yaml_and_doc"] is False


def test_run_manifest_and_artifact_hashes_valid() -> None:
    manifest = _load("run_manifest.json")
    assert manifest["checkpoint_id"] == "C-V2-PRE006-CONTROL"
    assert manifest["no_protocol_mutated"] is True
    hashes = _load("artifact_hashes.json")
    for rel_path, expected in hashes["artifacts"].items():
        assert hash_file(ROOT / rel_path) == expected
