"""V2-REL-001 post-result tests: the frozen ACCEPT decision, locks, cutover evidence, claim audit
and the registry transition. Immutable facts only."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
REL = ROOT / "reports/model_v2/v2_rel_001"
CUT = REL / "cutover"


def _j(path: Path) -> dict:
    return json.loads(path.read_text())


def test_decision_is_derived_accept_with_no_override() -> None:
    decision = _j(REL / "system_v2_release_decision.json")
    assert decision["SYSTEM_V2_RELEASE_DECISION"] == "ACCEPT" and not decision["failed_criteria"]
    assert decision["manual_override"] is False and len(decision["criteria"]) == 25
    assert decision["historical_model_promotion_disposition"] == "MODEL_V2_NOT_PROMOTED_RELEASE_CI"
    assert decision["new_system_release_disposition"] == "SYSTEM_V2_RESEARCH_DEFAULT_ACCEPTED"
    assert decision["federated_checkpoint_deployed"] is False
    lock = _j(ROOT / "artifacts/SYSTEM_V2_RELEASE_DECISION_V1.lock.json")
    assert lock["decision_sha256"] == hash_file(REL / "system_v2_release_decision.json")
    matrix = REL / "system_v2_release_evidence_matrix.json"
    assert lock["evidence_matrix_sha256"] == hash_file(matrix)


def test_matrix_keeps_history_and_distinguishes_second_look() -> None:
    matrix = _j(REL / "system_v2_release_evidence_matrix.json")
    assert matrix["A_official_validation_history"]["observed"]["decision"] == (
        "MODEL_V2_NOT_PROMOTED_RELEASE_CI")
    assert matrix["A_official_validation_history"]["observed"]["converted_to_pass"] is False
    assert "post_freeze_second_look_NOT_untouched_validation" in (
        matrix["B_central_model_improvement_evidence"])
    arch = matrix["G_federated_heldout_evaluation"]
    assert arch["all_architecture_effect_point_estimates_positive_for_AUPRC_and_patient_macro_F1"]
    assert arch["observed"]["internal_test"]["comparisons"] == 10


@pytest.mark.parametrize("name", [
    "default_replay", "rollback_replay", "isolation", "frontend", "lint", "regression",
    "protected_artifact_audit", "claim_audit", "smoke_model_v2", "smoke_gateway",
    "smoke_fl_init", "smoke_synthetic_fl", "smoke_fixed_vectors"])
def test_cutover_evidence_pass(name: str) -> None:
    assert _j(CUT / f"{name}.json")["status"] == "PASS"


def test_default_replay_did_not_use_the_research_launcher() -> None:
    data = _j(CUT / "default_replay.json")
    assert data["research_launcher_used"] is False
    assert "run_nhm_default" in data["launch_path"]
    assert data["scientific_metrics"] is False and data["real_waveform_dataset"] is False


def test_binding_and_system_locks_verify_and_predecessors_preserved() -> None:
    from scripts.verify_dashboard_ui_v1_5_v2rel001 import verify as ui
    from scripts.verify_default_runtime_binding_v2 import verify as binding
    from scripts.verify_e2e_replay_v1_4_v2rel001 import verify as e2e

    assert binding()["status"] == "PASS" and ui()["status"] == "PASS" and e2e()["status"] == "PASS"
    system = _j(ROOT / "artifacts/SOFTWARE_SYSTEM_V2.lock.json")
    assert system["default"]["model"] == "MODEL_V2_FINAL"
    assert system["rollback"]["role"] == "FROZEN_ROLLBACK_REFERENCE"
    assert system["federated_checkpoint_deployed"] is False


def test_registry_transition() -> None:
    def rows(name: str, key: str) -> dict:
        with (ROOT / f"manifests/model_v2/{name}_registry_v1.csv").open(newline="") as handle:
            return {r[key]: r["status"] for r in csv.DictReader(handle)}

    assert rows("task", "task_id")["V2-REL-001"] == "PASS"
    assert rows("gate", "gate_id")["V2RELG0"] == "PASS"
    comps = rows("component", "component_id")
    assert comps["SOFTWARE_SYSTEM_V2"] == "FROZEN_RESEARCH_SOFTWARE_DEFAULT"
    assert comps["ROLLBACK_RUNTIME_BINDING_V1"] == "FROZEN_ROLLBACK_REFERENCE"
    criteria = _j(CUT / "v2relg0_criteria.json")["criteria"]
    assert all(v is True or str(v).startswith("PENDING") for v in criteria.values())
