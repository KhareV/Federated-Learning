"""C-V2-004-AUDIT-CLOSEOUT tests: locks the provenance/reproducibility/wording corrections
made to V2-004 without reopening any scientific result. Fails if any of the 35 per-fit
integrity checks regress, the D2 failed-launch is ever counted as a completed fit, a
post-result script is shown to mutate a protected scientific artifact, the frozen
BEST_LEARNED_ONLY/hybrid-trigger/lock values change, V2-005 starts, official VALIDATION is
touched, the full-regression proof shows a gap, or the interpretation note slips back to
prohibited overstrong wording.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
AUDIT_DIR = ROOT / "reports/model_v2/c_v2_004_audit_closeout"


def _load(name: str) -> dict:
    return json.loads((AUDIT_DIR / name).read_text(encoding="utf-8"))


def test_all_35_fit_integrity_rows_pass() -> None:
    with (AUDIT_DIR / "all_fit_integrity_audit.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 35
    assert all(row["status"] == "PASS" for row in rows)
    assert all(row["checkpoint_reload_consistency"] == "PASS" for row in rows)
    assert all(row["non_finite_detected"] == "False" for row in rows)
    assert all(row["outer_access_after_finalization"] == "True" for row in rows)


def test_canonical_fit_count_exactly_35() -> None:
    data = _load("fit_attempt_accounting.json")
    assert data["canonical_d1_fits"] == 15
    assert data["canonical_d2_fits"] == 20
    assert data["canonical_total_fits"] == 35
    assert data["unexpected_canonical_fits"] == 0
    assert data["v2_004_total_fits_per_search_budget_json"] == 35


def test_no_unexpected_d2_run_exists() -> None:
    data = _load("d2_launch_retry_provenance.json")
    assert data["committed_d2_run_directories_count"] == 20
    assert data["committed_d1_run_directories_count"] == 15


def test_failed_d2_launch_consumed_zero_canonical_fit() -> None:
    data = _load("d2_launch_retry_provenance.json")
    attributable = data["failed_launch_attributable_artifacts"]
    assert attributable["fit_summary_json_from_failed_attempt"] == 0
    assert attributable["canonical_outer_predictions_from_failed_attempt"] == 0
    assert attributable["selected_checkpoint_from_failed_attempt"] == 0
    assert attributable["completed_training_curve_from_failed_attempt"] == 0
    assert attributable["ledger_rows_from_failed_attempt"] == 0
    assert attributable["consumed_neural_fit_from_failed_attempt"] == 0


def test_posthoc_table_generator_did_not_mutate_protected_artifacts() -> None:
    data = _load("posthoc_table_generator_audit.json")
    assert data["status"] == "PASS"
    assert data["protected_artifacts_unchanged"] is True
    assert data["all_regenerated_byte_equal"] is True
    before = data["protected_artifacts_before"]
    after = data["protected_artifacts_after"]
    assert before == after


def test_component_lock_packaging_did_not_change_scientific_result() -> None:
    data = _load("component_lock_packaging_audit.json")
    assert data["status"] == "PASS"
    assert data["semantic_equal_to_canonical_excluding_expected_fields"] is True
    assert data["unexpected_differing_keys"] == []


def test_arch_causality_lock_hash_unchanged() -> None:
    lock_path = ROOT / "manifests/model_v2/MODEL_V2_ARCH_CAUSALITY_V1.lock.json"
    expected = "79c423fdcbd5c9dee1743ec60f704e56a48af201b6357499990cd54fa35729c3"
    assert hash_file(lock_path) == expected


def test_best_learned_only_unchanged() -> None:
    data = json.loads(
        (ROOT / "reports/model_v2/v2_004/best_learned_only.json").read_text(encoding="utf-8")
    )
    assert data["architecture_id"] == "MODEL_V2_TCN_MEANMAX"
    assert data["AUPRC_mean"] == 0.8558768456473372


def test_hybrid_trigger_still_false() -> None:
    confirmation = _load("hybrid_trigger_confirmation.json")
    assert confirmation["status"] == "PASS"
    assert confirmation["result"] is False
    assert confirmation["result_status_string"] == "FALSE"
    frozen = json.loads(
        (ROOT / "reports/model_v2/v2_004/hybrid_trigger.json").read_text(encoding="utf-8")
    )
    assert frozen["trigger"] is False
    assert frozen["status"] == "FALSE"


def test_v2_005_not_started() -> None:
    data = _load("registry_state_audit.json")
    assert data["status"] == "PASS"
    assert data["tasks"]["V2-005"] == "NOT_STARTED"
    assert data["gates"]["V2G4"] == "NOT_STARTED"
    assert data["tasks"]["V2-006"] == "NOT_STARTED"
    assert data["gates"]["V2G5"] == "NOT_STARTED"


def test_no_official_validation_or_other_scope_violation() -> None:
    scope = json.loads(
        (ROOT / "reports/model_v2/v2_004/scope_leakage_audit.json").read_text(encoding="utf-8")
    )
    assert scope["status"] == "PASS"
    assert scope["official_validation_touched"] is False
    assert scope["calibration_touched"] is False
    assert scope["internal_test_touched"] is False
    assert scope["incart_touched"] is False
    assert scope["nstdb_touched"] is False
    assert scope["bidmc_touched"] is False


def test_full_regression_proof_has_no_gap() -> None:
    data = _load("full_regression_proof.json")
    assert data["status"] == "PASS"
    assert data["collected_equals_executed"] is True
    assert data["duplicates"] == 0
    assert data["missing"] == 0
    assert data["failed_chunks"] == 0
    assert data["failed_tests"] == 0
    assert data["ruff"]["exit_code"] == 0
    assert data["pip_check"]["exit_code"] == 0


PROHIBITED_PHRASES = [
    "CAPCTRL is statistically indistinguishable from V1",
    "causes a significant improvement",
    "mean+max pooling adds no benefit",
]


def test_interpretation_note_does_not_use_prohibited_wording() -> None:
    data = _load("scientific_interpretation_correction.json")
    assert data["status"] == "PASS"
    assert data["biological_or_clinical_causal_claim_made"] is False
    assert data["formal_significance_claim_made_without_qualification"] is False

    corrected_text = " ".join(
        [
            data["H0"]["corrected_wording"],
            data["H1"]["corrected_wording"],
            data["H2"]["corrected_wording"],
        ]
    )
    for phrase in PROHIBITED_PHRASES:
        assert phrase not in corrected_text

    assert data["no_retroactive_reopening"]["retroactively_changed"] is False
    assert (
        data["no_retroactive_reopening"]["best_learned_only_v2_cv_v1_preserved_as"]
        == "MODEL_V2_TCN_MEANMAX"
    )


def test_git_chronology_and_scientific_method_immutability() -> None:
    chronology = _load("git_chronology_audit.json")
    assert chronology["status"] == "PASS"
    assert chronology["method_before_results"] is True
    assert chronology["attestation_before_results"] is True

    immutability = _load("scientific_method_immutability_audit.json")
    assert immutability["status"] == "PASS"
    assert immutability["any_file_changed_after_method_freeze"] is False


def test_upstream_locks_unchanged() -> None:
    data = _load("upstream_identity_audit.json")
    assert data["status"] == "PASS"
    for check in data["checks"].values():
        if "unchanged" in check:
            assert check["unchanged"] is True
