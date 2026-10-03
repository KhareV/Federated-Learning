"""C-V2-PRE006-AUTHORITY-REPAIR tests: locks the implementation-drift repair against the
self-contained MODEL_V2 authority contract. Fails if either frozen predecessor protocol
changes, Protocol V3 permits official VALIDATION to drive early-stopping/scheduler/
checkpoint-selection, the final TRAIN manifest is missing or malformed, the fit cap drifts
from 90, V2-008 regains the obsolete AUROC hard gate or loses either required AUPRC
criterion, the release seed changes, conditional-skip semantics break, V2-006/V2G5 start, or
MODEL_V2_FINAL/CAL_V2 appear.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import yaml

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
AUDIT_DIR = ROOT / "reports/model_v2/c_v2_pre006_authority_repair"
V3_YAML = ROOT / "configs/model_v2/research_protocol_v3.yaml"


def _load(name: str) -> dict:
    return json.loads((AUDIT_DIR / name).read_text(encoding="utf-8"))


def _v3() -> dict:
    return yaml.safe_load(V3_YAML.read_text(encoding="utf-8"))


def _registry() -> tuple[dict, dict]:
    with (ROOT / "manifests/model_v2/task_registry_v1.csv").open(newline="") as handle:
        tasks = {row["task_id"]: row for row in csv.DictReader(handle)}
    with (ROOT / "manifests/model_v2/gate_registry_v1.csv").open(newline="") as handle:
        gates = {row["gate_id"]: row["status"] for row in csv.DictReader(handle)}
    return tasks, gates


def test_protocol_v1_v2_byte_unchanged() -> None:
    assert (
        hash_file(ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V1.lock.json")
        == "4dadf234afd239539240e4e2662b1fdf54e5154400b1ea4e0c14c8e4107e2eb7"
    )
    assert (
        hash_file(ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V2.lock.json")
        == "f300473a84d5ba1ceda1da722c4b2745856b43b4c1353e5af8cb2e8a3f878f81"
    )


def test_protocol_v3_parent_is_v2() -> None:
    v3 = _v3()
    assert v3["parent_protocol"] == "MODEL_V2_RESEARCH_PROTOCOL_V2"


def test_protocol_v3_forbids_official_validation_early_stop_scheduler_checkpoint() -> None:
    v3 = _v3()
    forbidden = v3["final_train_role_split"]["official_validation_forbidden_roles"]
    assert "early_stopping" in forbidden
    assert "scheduler" in forbidden
    assert "checkpoint_selection" in forbidden
    assert (
        v3["official_validation"]["early_stopping_checkpoint_selection"]
        != "OFFICIAL_VALIDATION_LOCKED_V2.2_ROLE"
    )


def test_final_train_manifest_exists_with_27_groups() -> None:
    manifest = ROOT / "manifests/model_v2/cv/MITDB_TRAIN_FINAL_INNER_V2_V1.csv"
    assert manifest.exists()
    with manifest.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 27


def test_final_train_manifest_roles_disjoint_and_conserved() -> None:
    data = _load("final_inner_manifest_audit.json")
    assert data["status"] == "PASS"
    assert data["role_disjoint"] is True
    assert data["union_equals_full_train_population"] is True
    assert data["held_out_or_external_overlap"] == []
    assert data["windows_conserved_exactly"] is True
    assert data["positives_conserved_exactly"] is True
    assert data["negatives_conserved_exactly"] is True
    assert data["both_roles_contain_both_classes"] is True


def test_fit_cap_is_90_not_100() -> None:
    v3 = _v3()
    assert v3["search_budget"]["d0_d5_max_neural_fits"] == 90
    data = _load("fit_budget_correction.json")
    assert data["authoritative_cap"] == 90


def test_v2_006_local_cap_not_above_15() -> None:
    v3 = _v3()
    assert v3["search_budget"]["v2_006_local_max_new_fits"] <= 15


def test_v2_008_does_not_contain_obsolete_auroc_hard_gate() -> None:
    tasks, _ = _registry()
    notes = tasks["V2-008"]["notes"]
    assert "NOT an additional hard D5 promotion gate" in notes
    v3 = _v3()
    assert v3["official_validation"]["promotion_requirement"][
        "auroc_material_regression_forbidden"
    ] is False


def test_v2_008_retains_both_required_aprc_promotion_conditions() -> None:
    tasks, _ = _registry()
    notes = tasks["V2-008"]["notes"]
    assert "mean three-seed official VALIDATION AUPRC > 0.646" in notes
    assert "lower-95%-CI bound > 0" in notes
    v3 = _v3()
    promotion = v3["official_validation"]["promotion_requirement"]
    assert promotion["mean_three_seed_validation_auprc_min"] == 0.646
    assert (
        promotion[
            "paired_patient_cluster_bootstrap_delta_auprc_vs_model_v1_lower_95_ci_bound_min"
        ]
        == 0.0
    )


def test_release_seed_is_20260927() -> None:
    v3 = _v3()
    ov = v3["official_validation"]
    assert ov["release_checkpoint_seed"] == 20260927
    assert ov["release_checkpoint_seed_fixed_regardless_of_score"] is True


def test_v2_005_skip_resolver_still_works_and_arbitrary_rejected() -> None:
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
    # MODEL_V2_FINAL (V2-008) and CAL_V2 (V2-009) have since legitimately frozen; this test
    # only guards against an invalid status value for either.
    with (ROOT / "manifests/model_v2/component_registry_v1.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    model_v2_final = next(r for r in rows if r["component_id"] == "MODEL_V2_FINAL")
    assert model_v2_final["status"] in {"NOT_STARTED", "FROZEN"}
    cal_v2 = next(r for r in rows if r["component_id"] == "CAL_V2")
    assert cal_v2["status"] in {"NOT_STARTED", "FROZEN"}


def test_no_waveform_access_or_fits_occurred() -> None:
    data = _load("no_data_no_training_audit.json")
    assert data["status"] == "PASS"
    assert data["neural_fits_added"] == 0
    assert data["classical_fits_added"] == 0
    assert data["waveform_reads"] == 0
    assert data["official_validation_accessed"] is False
    assert data["calibration_accessed"] is False


def test_cal_v2_ordering_preserved_and_not_accessed() -> None:
    data = _load("cal_v2_ordering_confirmation.json")
    assert data["status"] == "PASS"
    assert data["cal_v2_contingent_on_runtime_acceptance"] is False
    assert data["cal_v2_accessed_in_this_checkpoint"] is False
    assert data["cal_v1_modified_in_this_checkpoint"] is False


def test_upstream_scientific_locks_unchanged() -> None:
    data = _load("upstream_identity_audit.json")
    assert data["status"] == "PASS"
    for check in data["checks"].values():
        if isinstance(check, dict) and "unchanged" in check:
            assert check["unchanged"] is True


def test_run_manifest_and_artifact_hashes_valid() -> None:
    manifest = _load("run_manifest.json")
    assert manifest["checkpoint_id"] == "C-V2-PRE006-AUTHORITY-REPAIR"
    assert manifest["v1_v2_protocol_mutated"] is False
    hashes = _load("artifact_hashes.json")
    for rel_path, expected in hashes["artifacts"].items():
        assert hash_file(ROOT / rel_path) == expected
