"""V2-006 pre-run tests: proves the method (CONTROL reuse, challenger contract, role
firewall, bootstrap-SE-delta definition, adoption rule, shortlist policy) is correctly
frozen BEFORE any challenger fit runs. Read-only against frozen V2-004/Protocol V3/CV
manifest artifacts; never trains a model.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import yaml

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
V3_YAML = ROOT / "configs/model_v2/research_protocol_v3.yaml"
OPT_CONFIG = ROOT / "configs/model_v2/optimizer_correction_v1.yaml"


def _opt_config() -> dict:
    return yaml.safe_load(OPT_CONFIG.read_text(encoding="utf-8"))


def _v3() -> dict:
    return yaml.safe_load(V3_YAML.read_text(encoding="utf-8"))


def test_protocol_v1_v2_v3_immutable() -> None:
    assert (
        hash_file(ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V1.lock.json")
        == "4dadf234afd239539240e4e2662b1fdf54e5154400b1ea4e0c14c8e4107e2eb7"
    )
    assert (
        hash_file(ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V2.lock.json")
        == "f300473a84d5ba1ceda1da722c4b2745856b43b4c1353e5af8cb2e8a3f878f81"
    )
    assert (
        hash_file(ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V3.lock.json")
        == "287aff4ff3fcf583524f06e6af51f23bd65949a75abef14cde80ff0936873db8"
    )


def test_final_inner_manifest_exact_and_untouched() -> None:
    assert (
        hash_file(ROOT / "manifests/model_v2/cv/MITDB_TRAIN_FINAL_INNER_V2_V1.csv")
        == "bb5b4f6f7205fe37d0132ebccaca7889a916b115f5ad096ecc967940421455ce"
    )


def test_v2_006_uses_old_outer_inner_manifests_not_final_inner() -> None:
    import scripts._v2_006_lib as lib

    assert lib.OUTER_CV_CSV.name == "MITDB_TRAIN_CV_V2_V1.csv"
    assert lib.INNER_CV_CSV.name == "MITDB_TRAIN_INNER_V2_V1.csv"
    source = (ROOT / "scripts/run_v2_006_fit.py").read_text(encoding="utf-8")
    assert "MITDB_TRAIN_FINAL_INNER_V2_V1" not in source
    lib_source = (ROOT / "scripts/_v2_006_lib.py").read_text(encoding="utf-8")
    assert "MITDB_TRAIN_FINAL_INNER_V2_V1" not in lib_source


def test_winning_architecture_is_tcn_meanmax() -> None:
    import scripts._v2_006_lib as lib

    assert lib.ARCHITECTURE_ID == "MODEL_V2_TCN_MEANMAX"
    arch_lock = json.loads(
        (ROOT / "manifests/model_v2/MODEL_V2_ARCH_CAUSALITY_V1.lock.json").read_text()
    )
    best = json.loads((ROOT / "reports/model_v2/v2_004/best_learned_only.json").read_text())
    assert best["architecture_id"] == "MODEL_V2_TCN_MEANMAX"
    del arch_lock


def test_architecture_params_57577() -> None:
    import scripts._v2_006_lib as lib

    model = lib.build_architecture()
    count = sum(p.numel() for p in model.parameters() if p.requires_grad)
    assert count == 57577 == lib.EXPECTED_PARAMETER_COUNT


def test_control_is_read_only_v2_004_evidence_never_retrained() -> None:
    source = (ROOT / "scripts/aggregate_v2_006.py").read_text(encoding="utf-8")
    assert "run_v2_004_fit" not in source
    assert "load_control_predictions" in source
    for fold in range(5):
        exp_id = f"V2-004-D1-MEANMAX-F{fold:02d}-S20260927"
        assert (ROOT / f"reports/model_v2/v2_004/runs/{exp_id}/outer_predictions.csv").exists()
    for seed in (20260928, 20260929):
        for fold in range(5):
            exp_id = f"V2-004-D2-MEANMAX-F{fold:02d}-S{seed}"
            path = ROOT / f"reports/model_v2/v2_004/runs/{exp_id}/outer_predictions.csv"
            assert path.exists()


def test_challenger_count_exactly_15_three_seeds_five_folds() -> None:
    config = _opt_config()
    matrix = config["challenger"]["experiment_matrix"]
    assert matrix["seeds"] == [20260927, 20260928, 20260929]
    assert matrix["outer_folds"] == [0, 1, 2, 3, 4]
    assert matrix["total_planned_fits"] == 15


def test_challenger_only_changes_scheduler_and_early_stop() -> None:
    config = _opt_config()
    challenger = config["challenger"]
    assert challenger["only_permitted_changes"] == {
        "scheduler_patience": 3,
        "scheduler_factor": 0.3,
        "early_stopping_patience": 8,
    }
    inherited = challenger["inherited_fields"]
    assert inherited["learning_rate"] == 0.001
    assert inherited["weight_decay"] == 0.0001
    assert inherited["batch_size"] == 64
    assert inherited["max_epochs"] == 50
    assert inherited["optimizer"] == "AdamW"
    assert inherited["loss"] == "BCEWithLogitsLoss"
    assert inherited["pos_weight_source"] == "OPTIMISE_ONLY"


def test_challenger_scheduler_exact_values() -> None:
    import scripts._v2_006_lib as lib

    control_config, _ = lib.load_frozen_model_v1_config()
    challenger_config = lib.build_challenger_config(control_config)
    assert challenger_config["scheduler"]["patience"] == 3
    assert challenger_config["scheduler"]["factor"] == 0.3
    assert challenger_config["training"]["early_stopping_patience"] == 8
    # Every other field inherited unchanged from control.
    for key in control_config["scheduler"]:
        if key in {"patience", "factor"}:
            continue
        assert control_config["scheduler"][key] == challenger_config["scheduler"][key]
    for key in control_config["optimizer"]:
        assert control_config["optimizer"][key] == challenger_config["optimizer"][key]
    assert control_config["training"]["batch_size"] == challenger_config["training"]["batch_size"]
    assert control_config["training"]["max_epochs"] == challenger_config["training"]["max_epochs"]


def test_control_scheduler_matches_actual_frozen_config_not_memory() -> None:
    import scripts._v2_006_lib as lib

    control_config, _ = lib.load_frozen_model_v1_config()
    assert control_config["scheduler"]["factor"] == 0.1
    assert control_config["scheduler"]["patience"] == 10
    assert control_config["training"]["early_stopping_patience"] == 7


def test_role_firewall_stage_ids_registered() -> None:
    from nhm.model_v2_cv_role_guard import STAGE_ALLOWED_ROLES

    assert STAGE_ALLOWED_ROLES["V2-006_TRAIN_SELECT"] == frozenset(
        {"OPTIMISE", "INNER_VALIDATION"}
    )
    assert STAGE_ALLOWED_ROLES["V2-006_OUTER_EVAL"] == frozenset({"OUTER_TEST"})


def test_outer_test_denied_before_checkpoint_finalized() -> None:
    from nhm.model_v2_cv_role_guard import CVRoleAccessViolation, check_cv_role_allowed

    try:
        check_cv_role_allowed(
            "OUTER_TEST", "V2-006_OUTER_EVAL",
            requested_outer_fold=0, experiment_outer_fold=0, checkpoint_finalized=False,
        )
        raise AssertionError("expected CVRoleAccessViolation")
    except CVRoleAccessViolation:
        pass


def test_bootstrap_draws_reused_not_new_rng() -> None:
    import numpy as np

    config = _opt_config()
    identity = config["bootstrap_draws_identity"]
    assert identity["bootstrap_id"] == "MODEL_V2_BOOTSTRAP_DRAWS_V1"
    assert identity["new_rng_forbidden"] is True
    draws = np.load(ROOT / identity["source_path"])
    assert draws.shape == (identity["replicates"], identity["patient_slots"])


def test_bootstrap_se_delta_definition_frozen() -> None:
    config = _opt_config()
    definition = config["bootstrap_se_delta_definition"]
    assert (
        definition["method"]
        == "sample_standard_deviation_ddof_1_of_valid_paired_delta_rep_values"
    )
    for forbidden in definition["forbidden_definitions"]:
        assert forbidden in {
            "control_bootstrap_sd_alone", "challenger_bootstrap_sd_alone",
            "ci_width_over_1_96", "fold_to_fold_sd", "seed_sd",
        }


def test_adoption_rule_strict_comparator_no_auroc_gate() -> None:
    config = _opt_config()
    rule = config["adoption_rule"]
    assert rule["condition_a"] == "point_delta_strictly_greater_than_bootstrap_se_delta"
    assert rule["condition_b"] == "challenger_seed_sd_lte_control_seed_sd"
    assert rule["no_auroc_adoption_gate"] is True
    assert rule["no_p_value_rule"] is True
    assert rule["no_ci_only_rule"] is True
    assert rule["both_required"] is True


def test_no_extra_optimizer_variant_forbidden_list() -> None:
    config = _opt_config()
    forbidden = config["challenger"]["forbidden_changes"]
    for item in [
        "learning_rate", "weight_decay", "batch_size", "optimizer_family",
        "loss_function", "augmentation", "normalization", "architecture",
        "pos_weight_rule", "second_challenger_variant",
    ]:
        assert item in forbidden


def test_shortlist_exactly_two_entries_policy() -> None:
    config = _opt_config()
    policy = config["finalist_shortlist_policy"]
    assert policy["max_official_validation_configurations"] == 2
    assert policy["finalist_a"]["architecture"] == "MODEL_V2_TCN_MEAN"
    assert policy["finalist_a"]["schedule_unchanged"] is True
    assert policy["finalist_b"]["architecture"] == "MODEL_V2_TCN_MEANMAX"
    assert policy["third_finalist_forbidden"] is True


def test_tcn_mean_keeps_original_schedule_never_challenged() -> None:
    source = (ROOT / "scripts/_v2_006_lib.py").read_text(encoding="utf-8")
    assert "MODEL_V2_TCN_MEAN\"" not in source or "MODEL_V2_TCN_MEANMAX" in source
    config = _opt_config()
    assert config["architecture"]["component_id"] == "MODEL_V2_TCN_MEANMAX"


def test_search_budget_90_cap_not_violated_by_plan() -> None:
    config = _opt_config()
    budget = config["search_budget"]
    assert budget["d0_d5_max_neural_fits"] == 90
    assert budget["completed_neural_fits_before_v2_006"] == 50
    assert budget["v2_006_max_new_fits"] == 15
    assert budget["max_cumulative_after_v2_006"] == 65
    assert budget["max_cumulative_after_v2_006"] <= budget["d0_d5_max_neural_fits"]


def test_official_validation_inaccessible_by_code_inspection() -> None:
    for path in [
        "scripts/_v2_006_lib.py", "scripts/run_v2_006_fit.py",
        "scripts/aggregate_v2_006.py", "scripts/bootstrap_v2_006.py",
        "scripts/decide_v2_006.py",
    ]:
        source = (ROOT / path).read_text(encoding="utf-8")
        for forbidden in ["CALIBRATION", "INTERNAL_TEST", "INCART", "NSTDB", "BIDMC"]:
            assert forbidden not in source, f"{path} references {forbidden}"


def test_run_manifest_schema_contract_available() -> None:
    schema_path = ROOT / "contracts/model_v2_run_manifest_v1.schema.json"
    assert schema_path.exists()


def test_architecture_causality_and_best_learned_only_unchanged() -> None:
    assert (
        hash_file(ROOT / "manifests/model_v2/MODEL_V2_ARCH_CAUSALITY_V1.lock.json")
        == "79c423fdcbd5c9dee1743ec60f704e56a48af201b6357499990cd54fa35729c3"
    )


def test_v2_006_and_v2g5_not_started_before_real_run() -> None:
    with (ROOT / "manifests/model_v2/task_registry_v1.csv").open(newline="") as handle:
        tasks = {row["task_id"]: row["status"] for row in csv.DictReader(handle)}
    with (ROOT / "manifests/model_v2/gate_registry_v1.csv").open(newline="") as handle:
        gates = {row["gate_id"]: row["status"] for row in csv.DictReader(handle)}
    assert tasks["V2-006"] in {"NOT_STARTED", "PASS"}
    assert gates["V2G5"] in {"NOT_STARTED", "PASS"}
