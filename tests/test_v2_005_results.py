"""V2-005 CONDITIONAL HYBRID DISPOSITION result tests. Proves the pre-registered hybrid
trigger was mechanically recomputed from frozen scalar inputs and confirmed FALSE, zero
hybrid fits/checkpoints/scientific artifacts were created, no waveform or forbidden
partition was accessed, every upstream V2-003/V2-004 lock remains byte-identical, and the
registry transition (V2-005 -> SKIPPED_BY_PROTOCOL, V2G4 -> PASS) is exact. Read-only:
never regenerates V2-004 or V2-005 evidence.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
V2_005_DIR = ROOT / "reports/model_v2/v2_005"


def _load(name: str) -> dict:
    return json.loads((V2_005_DIR / name).read_text(encoding="utf-8"))


def _registry_status() -> tuple[dict, dict]:
    with (ROOT / "manifests/model_v2/task_registry_v1.csv").open(newline="") as handle:
        tasks = {row["task_id"]: row["status"] for row in csv.DictReader(handle)}
    with (ROOT / "manifests/model_v2/gate_registry_v1.csv").open(newline="") as handle:
        gates = {row["gate_id"]: row["status"] for row in csv.DictReader(handle)}
    return tasks, gates


def test_v2_004_remains_pass_and_v2g3_remains_pass() -> None:
    tasks, gates = _registry_status()
    assert tasks["V2-004"] == "PASS"
    assert gates["V2G3"] == "PASS"


def test_v2_005_skipped_by_protocol_and_v2g4_pass() -> None:
    tasks, gates = _registry_status()
    assert tasks["V2-005"] == "SKIPPED_BY_PROTOCOL"
    assert gates["V2G4"] == "PASS"


def test_v2_006_and_v2g5_not_regressed() -> None:
    # This checkpoint (V2-005) ran strictly before V2-006; it required V2-006/V2G5 to still
    # be NOT_STARTED at that time, which was true. V2-006 has since legitimately run and
    # passed -- this test only guards against an invalid status value, and that V2-007/V2G6
    # (which V2-006 itself must not start) remain untouched.
    tasks, gates = _registry_status()
    assert tasks["V2-006"] in {"NOT_STARTED", "PASS"}
    assert gates["V2G5"] in {"NOT_STARTED", "PASS"}
    assert tasks["V2-007"] == "NOT_STARTED"
    assert gates["V2G6"] == "NOT_STARTED"


def test_trigger_identities_match_frozen_decisions() -> None:
    verification = _load("hybrid_trigger_verification.json")
    assert verification["status"] == "PASS"
    assert verification["classical_reference_id"] == "BEST_REDUCED_RF_V1"
    assert verification["learned_reference_id"] == "BEST_LEARNED_ONLY_V2_CV_V1"
    assert verification["learned_architecture_read_from_artifact"] == "MODEL_V2_TCN_MEANMAX"
    assert verification["identity_checks"]["classical_reference_variant_is_RR"] is True
    assert verification["identity_checks"]["classical_reference_feature_count_is_9"] is True
    assert (
        verification["identity_checks"]["stability_decision_agrees_on_best_learned_only"]
        is True
    )


def test_classical_and_learned_auprc_exact() -> None:
    verification = _load("hybrid_trigger_verification.json")
    assert verification["classical_auprc_read_from_artifact"] == 0.713140103147974
    assert verification["learned_auprc_read_from_artifact"] == 0.8558768456473372


def test_gap_recomputation_matches_frozen_value() -> None:
    verification = _load("hybrid_trigger_verification.json")
    assert verification["gap_matches_within_1e-15"] is True
    assert verification["recomputed_gap"] == verification["stored_gap"]
    assert verification["stored_gap"] == -0.1427367424993632


def test_threshold_comparator_and_trigger_false() -> None:
    verification = _load("hybrid_trigger_verification.json")
    assert verification["stored_threshold"] == 0.03
    assert verification["stored_comparator"] == ">="
    assert verification["stored_trigger"] is False
    assert verification["recomputed_trigger"] is False
    assert verification["stored_and_recomputed_trigger_agree"] is True


def test_zero_hybrid_fits_and_zero_new_checkpoints() -> None:
    data = _load("zero_fit_audit.json")
    assert data["status"] == "PASS"
    assert data["fit_delta"] == 0
    assert data["checkpoint_delta"] == 0
    assert data["delta"]["v2_005_run_directory_count"] == 0
    assert data["delta"]["v2_004_run_directory_count"] == 0


def test_no_hybrid_or_aux_feature_scientific_artifact() -> None:
    data = _load("unexpected_hybrid_state_audit.json")
    assert data["status"] == "PASS"
    assert data["no_unauthorized_preexisting_hybrid_result"] is True
    assert data["hybrid_or_aux_checkpoint_hits"] == []
    assert data["aux_features_row_still_reserved"] is True
    assert data["frozen_or_selected_hybrid_rows"] == []
    assert data["v2_005_fit_run_directories_found"] == []


def test_no_waveform_or_forbidden_partition_access() -> None:
    data = _load("data_scope_audit.json")
    assert data["status"] == "PASS"
    assert data["TRAIN_waveform_accessed"] is False
    assert data["VALIDATION_accessed"] is False
    assert data["CALIBRATION_accessed"] is False
    assert data["INTERNAL_TEST_accessed"] is False
    assert data["INCART_accessed"] is False
    assert data["NSTDB_accessed"] is False
    assert data["BIDMC_accessed"] is False
    assert data["raw_ECG_accessed"] is False
    assert data["annotations_accessed"] is False
    assert data["model_inference_run"] is False


def test_arch_causality_feature_audit_and_protocol_unchanged() -> None:
    data = _load("upstream_identity_audit.json")
    assert data["status"] == "PASS"
    for check in data["checks"].values():
        assert check["unchanged"] is True


def test_search_budget_remains_50() -> None:
    data = _load("search_budget.json")
    assert data["status"] == "PASS"
    assert data["cumulative_neural_fits_after_v2_005"] == 50
    assert data["v2_005_neural_fits_added"] == 0
    assert data["v2_005_classical_fits_added"] == 0
    assert data["hybrid_fit_count"] == 0
    assert data["global_neural_fit_cap"] == 100


def test_v2g4_pass_cannot_be_interpreted_as_hybrid_performance_pass() -> None:
    disposition = _load("hybrid_disposition.json")
    assert disposition["hybrid_model_created"] is False
    assert disposition["branch"] == "SKIP_HYBRID"
    note = disposition["gate_note"]
    assert "not hybrid-model performance" in note
    assert "correct conditional-branch handling" in note


def test_registry_csv_field_alignment_exact() -> None:
    for name in ["task_registry_v1.csv", "gate_registry_v1.csv", "component_registry_v1.csv"]:
        path = ROOT / "manifests/model_v2" / name
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.reader(handle))
        header_len = len(rows[0])
        assert all(len(row) == header_len for row in rows[1:])

    with (ROOT / "manifests/model_v2/task_registry_v1.csv").open(newline="") as handle:
        task_rows = list(csv.DictReader(handle))
    assert len(task_rows) == 14
    assert len({row["task_id"] for row in task_rows}) == 14

    with (ROOT / "manifests/model_v2/gate_registry_v1.csv").open(newline="") as handle:
        gate_rows = list(csv.DictReader(handle))
    assert len(gate_rows) == 14
    assert len({row["gate_id"] for row in gate_rows}) == 14


def test_run_manifest_and_artifact_hashes_valid() -> None:
    manifest = _load("run_manifest.json")
    assert manifest["checkpoint_id"] == "V2-005"
    hashes = _load("artifact_hashes.json")
    for rel_path, expected in hashes["artifacts"].items():
        assert hash_file(ROOT / rel_path) == expected


def test_v2_004_protected_tree_matched_head_before_and_after() -> None:
    before = _load("v2_004_readonly_integrity_before.json")
    after = _load("v2_004_readonly_integrity_after.json")
    assert before["status"] == "PASS"
    assert after["status"] == "PASS"
    assert before["mismatch_count"] == 0
    assert after["mismatch_count"] == 0
    assert before["file_count"] == after["file_count"]


# ---------------------------------------------------------------------------
# Section 24: V2-004 protection test -- read-only identity comparison against
# committed artifacts, no regeneration.
# ---------------------------------------------------------------------------

def test_v2_004_frozen_artifacts_unchanged_identity() -> None:
    lock_path = ROOT / "manifests/model_v2/MODEL_V2_ARCH_CAUSALITY_V1.lock.json"
    assert (
        hash_file(lock_path)
        == "79c423fdcbd5c9dee1743ec60f704e56a48af201b6357499990cd54fa35729c3"
    )

    v2_004_dir = ROOT / "reports/model_v2/v2_004"
    best_learned_only = json.loads(
        (v2_004_dir / "best_learned_only.json").read_text(encoding="utf-8")
    )
    assert best_learned_only["architecture_id"] == "MODEL_V2_TCN_MEANMAX"
    assert best_learned_only["AUPRC_mean"] == 0.8558768456473372

    hybrid_trigger = json.loads(
        (v2_004_dir / "hybrid_trigger.json").read_text(encoding="utf-8")
    )
    assert hybrid_trigger["trigger"] is False
    assert hybrid_trigger["gap"] == -0.1427367424993632

    stability_decision = json.loads(
        (v2_004_dir / "d2_stability_decision.json").read_text(encoding="utf-8")
    )
    assert stability_decision["best_learned_only_architecture_id"] == "MODEL_V2_TCN_MEANMAX"
    assert stability_decision["v2_004_outcome"] == "D2_TWO_SURVIVORS"


def test_feature_audit_lock_unchanged() -> None:
    lock_path = ROOT / "manifests/model_v2/MODEL_V2_FEATURE_AUDIT_V1.lock.json"
    assert (
        hash_file(lock_path)
        == "a6876430dcad040b7008a69200fb4a36d735ad9a58d834c46d66d5543609623b"
    )


def test_protocol_v2_unchanged() -> None:
    lock_path = ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V2.lock.json"
    assert (
        hash_file(lock_path)
        == "f300473a84d5ba1ceda1da722c4b2745856b43b4c1353e5af8cb2e8a3f878f81"
    )


def test_no_new_component_registry_row() -> None:
    # V2-005 itself added zero component rows (row count was 18 immediately after this
    # phase). A later checkpoint (C-V2-PRE006-AUTHORITY-REPAIR) has since legitimately added
    # MODEL_V2_RESEARCH_PROTOCOL_V3 -- this test only guards against a hybrid-specific
    # component ever appearing, which remains V2-005's own scope.
    with (ROOT / "manifests/model_v2/component_registry_v1.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) >= 18
    forbidden_ids = {"MODEL_V2_HYBRID", "MODEL_V2_HYBRID_V1", "HYBRID_SCALER_V1"}
    assert not any(row["component_id"] in forbidden_ids for row in rows)

    aux_row = next(r for r in rows if r["component_id"] == "MODEL_V2_AUX_FEATURES_V1")
    assert aux_row["status"] == "PRE_REGISTERED_CONDITIONAL"


def test_no_freeze_registry_or_canonical_t_task_change() -> None:
    transition = _load("registry_transition.json")
    assert transition["no_freeze_registry_change"] is True
    assert transition["no_canonical_t_task_registry_change"] is True
    assert transition["no_new_component_registry_row"] is True
