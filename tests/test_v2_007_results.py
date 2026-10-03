"""V2-007 post-result tests: locks the frozen official-VALIDATION outcome. Fails if the
guard state regresses, the V1 reconstruction stops matching historical T015 scalars, the
finalist selection or promotion decision changes, prediction closure breaks, the search
budget drifts, or independent reverification/tamper evidence stops showing PASS.
"""

from __future__ import annotations

import json
from pathlib import Path

from nhm.hashing import hash_file
from nhm.model_v2_official_validation_guard import read_guard_state

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "reports/model_v2/v2_007"


def _load(name: str) -> dict:
    return json.loads((OUT_DIR / name).read_text(encoding="utf-8"))


def test_guard_completed_exactly_once() -> None:
    state = read_guard_state(ROOT)
    assert state["state"] == "COMPLETED"
    assert state["completion_summary"]["v2_prediction_rows"] == 17280
    assert state["completion_summary"]["v1_prediction_rows"] == 8640


def test_second_run_guard_blocked() -> None:
    data = _load("second_run_guard_audit.json")
    assert data["status"] == "PASS"
    assert data["second_run_blocked"] is True
    assert data["error_message"] == "MODEL_V2_VALIDATION_ALREADY_CONSUMED"


def test_prediction_closure_exact() -> None:
    data = _load("prediction_closure_audit.json")
    assert data["status"] == "PASS"
    assert data["total_v2_rows"] == 17280
    assert data["total_v1_rows"] == 8640
    assert data["violations"] == []


def test_v1_reconstruction_matches_historical_t015() -> None:
    data = _load("v1_reference_reconstruction_audit.json")
    assert data["status"] == "PASS"
    assert data["all_historical_values_reproduced"] is True
    assert data["reconstructed_three_seed_mean_auprc"] == 0.49827972496232814
    for seed_data in data["per_seed"].values():
        assert seed_data["match"] is True


def test_finalist_selection_exact() -> None:
    data = _load("finalist_selection.json")
    assert data["selected_finalist"] == "A"
    assert data["selected_architecture_id"] == "MODEL_V2_TCN_MEAN"
    assert data["selected_schedule_id"] == "CONFIG_V2_TCN_MEAN_ORIGINAL_V1"
    assert data["within_one_se"] is True
    assert data["tie_break_path"] == "fewer_trainable_parameters"
    assert data["a_params"] < data["b_params"]


def test_promotion_decision_exact() -> None:
    data = _load("promotion_decision.json")
    assert data["decision"] == "MODEL_V2_NOT_PROMOTED_RELEASE_CI"
    assert data["promotion_eligible"] is False
    assert data["criterion_a_mean_auprc_gt_0_646"] is True
    assert data["criterion_b1_release_delta_lower_ci_gt_0"] is False
    assert data["criterion_b2_three_seed_mean_delta_lower_ci_gt_0"] is True
    assert data["release_seed"] == 20260927
    assert data["no_auroc_hard_gate"] is True
    assert data["no_p_value_gate"] is True
    assert data["no_rf_or_lr_gate"] is True


def test_release_candidate_fixed_seed_not_best_seed() -> None:
    per_seed = {}
    import csv

    with (OUT_DIR / "finalist_validation_summary.csv").open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["architecture_id"] == "MODEL_V2_TCN_MEAN":
                per_seed = {
                    20260927: float(row["seed_20260927_auprc"]),
                    20260928: float(row["seed_20260928_auprc"]),
                    20260929: float(row["seed_20260929_auprc"]),
                }
    assert per_seed  # sanity
    best_seed = max(per_seed, key=lambda s: per_seed[s])
    promotion = _load("promotion_decision.json")
    assert promotion["release_seed"] == 20260927
    # release seed is fixed regardless of whether it is the best-scoring seed
    assert promotion["release_seed"] == 20260927 or best_seed != 20260927


def test_independent_reverification_matches_frozen() -> None:
    data = _load("independent_reverification.json")
    assert data["status"] == "PASS"
    assert all(data["matches_frozen"].values())
    assert data["reverified_selected_finalist"] == "A"
    assert data["reverified_decision"] == "MODEL_V2_NOT_PROMOTED_RELEASE_CI"


def test_bootstrap_reproducibility_byte_identical() -> None:
    data = _load("bootstrap_reproducibility.json")
    assert data["status"] == "PASS"
    assert data["differing_files"] == []


def test_tamper_tests_all_pass() -> None:
    data = _load("tamper_test_results.json")
    assert data["status"] == "PASS"
    assert data["all_tampers_detected"] is True
    assert data["canonical_artifacts_mutated"] is False


def test_method_immutability_since_method_commit() -> None:
    data = _load("method_immutability_audit.json")
    assert data["status"] == "PASS"
    assert data["all_unchanged"] is True


def test_protected_artifact_audit_zero_changes() -> None:
    data = _load("protected_artifact_audit.json")
    assert data["status"] == "PASS"
    assert data["changed_count"] == 0


def test_scope_leakage_and_search_budget() -> None:
    leakage = _load("scope_leakage_audit.json")
    assert leakage["status"] == "PASS"
    assert leakage["no_leakage"] is True
    budget = _load("search_budget.json")
    assert budget["status"] == "PASS"
    assert budget["cumulative"] == 71
    assert budget["d0_d5_max_neural_fits"] == 90


def test_comparison_asymmetry_disclosed() -> None:
    data = _load("comparison_asymmetry.json")
    assert data["status"] == "DISCLOSED"
    assert data["v1_retrained_under_v2_protocol"] is False


def test_component_locks_frozen() -> None:
    for name in [
        "MODEL_V2_VALIDATION_BOOTSTRAP_DRAWS_V1",
        "MODEL_V2_OFFICIAL_VALIDATION_V1",
        "MODEL_V2_VALIDATION_DECISION_V1",
    ]:
        path = ROOT / f"manifests/model_v2/{name}.lock.json"
        assert path.exists()
        lock = json.loads(path.read_text(encoding="utf-8"))
        assert lock["component_id"] == name
        assert lock["owner_task"] == "V2-007"


def test_no_model_v2_final_or_cal_v2_created() -> None:
    run_manifest = _load("run_manifest.json")
    assert run_manifest["model_v2_final_created"] is False
    assert run_manifest["cal_v2_created"] is False


def test_run_manifest_and_artifact_hashes_valid() -> None:
    manifest = _load("run_manifest.json")
    assert manifest["checkpoint_id"] == "V2-007"
    assert manifest["cumulative_v2_fits"] == 71
    hashes = _load("artifact_hashes.json")
    for rel_path, expected in hashes["artifacts"].items():
        assert hash_file(ROOT / rel_path) == expected
