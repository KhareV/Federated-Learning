"""C-V2-PRE006-CLOSEOUT tests: locks the final-inner-split/protocol-ordering closeout
finding. Mechanical evidence (V1 doc Section K, carried forward byte-identical into V2's
official_validation.early_stopping_checkpoint_selection field) shows the frozen protocol
deliberately uses official VALIDATION itself -- not a TRAIN-only inner split -- for
checkpoint selection among the V2-007 finalists. Neither CASE A nor CASE B's protocol-repair
branch applies; the actual defect was an incorrect V2-007 registry clarification introduced
by the immediately preceding checkpoint, now corrected. No Protocol V3, no new CV manifest,
and no scientific artifact mutation occur here.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
AUDIT_DIR = ROOT / "reports/model_v2/c_v2_pre006_closeout"


def _load(name: str) -> dict:
    return json.loads((AUDIT_DIR / name).read_text(encoding="utf-8"))


def _registry() -> tuple[dict, dict]:
    with (ROOT / "manifests/model_v2/task_registry_v1.csv").open(newline="") as handle:
        tasks = {row["task_id"]: row for row in csv.DictReader(handle)}
    with (ROOT / "manifests/model_v2/gate_registry_v1.csv").open(newline="") as handle:
        gates = {row["gate_id"]: row["status"] for row in csv.DictReader(handle)}
    return tasks, gates


def test_old_outer_cv_inner_manifest_unchanged() -> None:
    data = _load("final_inner_split_manifest_audit.json")
    assert data["mitdb_train_cv_v2_v1_csv_sha256_matches_lock"] is True
    assert data["mitdb_train_inner_v2_v1_csv_sha256_matches_lock"] is True


def test_no_final_inner_manifest_was_fabricated() -> None:
    classification = _load("final_inner_split_case_classification.json")
    assert classification["final_inner_manifest_created"] is False
    assert classification["protocol_v3_created"] is False
    assert classification["case_a_applies"] is False
    assert classification["case_b_applies"] is False
    assert (
        classification["actual_classification"]
        == "CASE_NEITHER_PROTOCOL_UNAMBIGUOUS_PRIOR_REGISTRY_ERROR"
    )


def test_v2_007_wording_reflects_actual_role_semantics() -> None:
    # This checkpoint's own conclusion (official VALIDATION itself governs checkpoint
    # selection) was itself superseded by C-V2-PRE006-AUTHORITY-REPAIR, which found this to
    # be implementation drift relative to the self-contained MODEL_V2 authority contract and
    # corrected V2-007 to use a dedicated TRAIN-only final inner split instead. This test now
    # only guards the historical evidence snapshot this checkpoint actually produced
    # (v2_007_registry_semantic_audit.json, read by test_official_validation_role_not_falsely_
    # denied below), not the live registry text, which has since legitimately changed again.
    # V2-007 has since legitimately run and passed -- guard only against an invalid value.
    tasks, _ = _registry()
    assert tasks["V2-007"]["status"] in {"NOT_STARTED", "PASS"}


def test_official_validation_role_not_falsely_denied() -> None:
    audit = _load("v2_007_registry_semantic_audit.json")
    assert audit["status"] == "PASS"
    assert audit["before_row_contained_incorrect_claim"] is True
    assert audit["after_notes_states_official_validation_used_for_checkpoint_selection"] is True
    for fact_ok in audit["after_notes_preserves_true_facts"].values():
        assert fact_ok is True


def test_early_stopping_field_unambiguous() -> None:
    data = _load("early_stopping_field_resolution.json")
    assert data["status"] == "PASS"
    assert data["ambiguous"] is False
    assert data["applies_to_official_validation_at_the_v2_007_finalist_stage"] is True
    assert data["applies_to_final_train_only_fitting"] is False
    assert data["optimizer_values_changed_in_this_checkpoint"] is False
    assert data["architecture_decisions_changed_in_this_checkpoint"] is False


def test_protocol_v1_and_v2_immutable() -> None:
    # The "no V3 created" assertion was this checkpoint's own point-in-time scope: at the
    # time C-V2-PRE006-CLOSEOUT ran, no V3 was needed. C-V2-PRE006-AUTHORITY-REPAIR has since
    # legitimately created MODEL_V2_RESEARCH_PROTOCOL_V3 as an additive successor -- this
    # test now only guards V1/V2 immutability, which both checkpoints agree on.
    assert (
        hash_file(ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V1.lock.json")
        == "4dadf234afd239539240e4e2662b1fdf54e5154400b1ea4e0c14c8e4107e2eb7"
    )
    assert (
        hash_file(ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V2.lock.json")
        == "f300473a84d5ba1ceda1da722c4b2745856b43b4c1353e5af8cb2e8a3f878f81"
    )


def test_cal_v2_ordering_machine_unambiguous() -> None:
    ordering = _load("protocol_internal_ordering_audit.json")
    resolution = _load("cal_v2_ordering_resolution.json")
    assert ordering["status"] == "PASS"
    assert ordering["chain_proves_cal_v2_necessarily_precedes_runtime_acceptance"] is True
    assert ordering["machine_unambiguous_without_protocol_v3"] is True
    assert resolution["status"] == "PASS"
    assert resolution["cal_v2_contingent_on_runtime_acceptance"] is False
    assert resolution["protocol_v3_required"] is False


def test_v2_008_auroc_wording_matches_active_protocol() -> None:
    data = _load("v2_008_auroc_clause_audit.json")
    assert data["status"] == "PASS"
    assert data["classification"] == "ACTIVE_HARD_REQUIREMENT"
    assert data["registry_mentions_auroc"] is True
    assert data["registry_wording_matches_active_classification"] is True


def test_no_protocol_wide_neural_fit_cap_falsely_asserted() -> None:
    data = _load("search_budget_authority_confirmation.json")
    assert data["status"] == "PASS"
    assert data["no_cap_of_90_invented"] is True
    assert data["no_cap_of_100_invented_as_authoritative"] is True
    assert data["no_protocol_v3_created_to_formalize_cap"] is True
    assert data["completed_neural_fits_before_v2_006"] == 50
    assert data["v2_006_phase_local_new_fit_maximum"] == 15


def test_v2_005_skip_resolver_still_valid_and_arbitrary_rejected() -> None:
    data = _load("conditional_prerequisite_regression.json")
    assert data["status"] == "PASS"
    assert data["v2_005_resolves_for_v2_007"] is True
    assert data["arbitrary_undeclared_skipped_task_rejected"] is True
    assert data["canonical_t_task_semantics_unchanged"] is True


def test_v2_006_and_v2g5_not_regressed() -> None:
    # This checkpoint ran strictly before V2-006; it required V2-006/V2G5 to still be
    # NOT_STARTED at that time, which was true. V2-006 has since legitimately run and
    # passed -- this test only guards against an invalid status value.
    tasks, gates = _registry()
    assert tasks["V2-006"]["status"] in {"NOT_STARTED", "PASS"}
    assert gates["V2G5"] in {"NOT_STARTED", "PASS"}
    assert tasks["V2-005"]["status"] == "SKIPPED_BY_PROTOCOL"
    assert gates["V2G4"] == "PASS"


def test_model_v2_final_and_cal_v2_absent() -> None:
    with (ROOT / "manifests/model_v2/component_registry_v1.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    for component_id in ("MODEL_V2_FINAL", "CAL_V2"):
        row = next(r for r in rows if r["component_id"] == component_id)
        assert row["status"] == "NOT_STARTED"


def test_no_waveform_access_or_fits_occurred() -> None:
    data = _load("no_data_no_training_audit.json")
    assert data["status"] == "PASS"
    assert data["neural_fits_added"] == 0
    assert data["classical_fits_added"] == 0
    assert data["waveform_reads"] == 0
    assert data["official_validation_accessed"] is False
    assert data["calibration_accessed"] is False


def test_upstream_scientific_locks_unchanged() -> None:
    data = _load("upstream_identity_audit.json")
    assert data["status"] == "PASS"
    for check in data["checks"].values():
        if isinstance(check, dict) and "unchanged" in check:
            assert check["unchanged"] is True


def test_run_manifest_and_artifact_hashes_valid() -> None:
    manifest = _load("run_manifest.json")
    assert manifest["checkpoint_id"] == "C-V2-PRE006-CLOSEOUT"
    assert manifest["protocol_v3_created"] is False
    assert manifest["final_inner_manifest_created"] is False
    hashes = _load("artifact_hashes.json")
    for rel_path, expected in hashes["artifacts"].items():
        assert hash_file(ROOT / rel_path) == expected
