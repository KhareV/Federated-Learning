"""C-V2-PRE006-AUTHORITY-REPAIR: MODEL_V2_RESEARCH_PROTOCOL_V3 structural tests. Proves V1/V2
remain byte-unchanged, V3's predecessor is V2, V3 changes only the declared drift fields
(official-VALIDATION checkpoint-selection role, AUROC D5 gate, search budget, CAL_V2
ordering, MODEL_V2_FINAL/runtime-acceptance separation), and the V2-007/V2-008 registry notes
match the corrected contract. Read-only against already-frozen artifacts except where it
regenerates V3 in a subprocess to prove reproducibility.
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import yaml

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
V1_YAML = ROOT / "configs/model_v2/research_protocol_v1.yaml"
V2_YAML = ROOT / "configs/model_v2/research_protocol_v2.yaml"
V3_YAML = ROOT / "configs/model_v2/research_protocol_v3.yaml"
V3_LOCK = ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V3.lock.json"


def _load_v3() -> dict:
    return yaml.safe_load(V3_YAML.read_text(encoding="utf-8"))


def test_protocol_v1_byte_unchanged() -> None:
    assert (
        hash_file(ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V1.lock.json")
        == "4dadf234afd239539240e4e2662b1fdf54e5154400b1ea4e0c14c8e4107e2eb7"
    )


def test_protocol_v2_byte_unchanged() -> None:
    assert (
        hash_file(ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V2.lock.json")
        == "f300473a84d5ba1ceda1da722c4b2745856b43b4c1353e5af8cb2e8a3f878f81"
    )


def test_v3_predecessor_is_v2() -> None:
    v3 = _load_v3()
    assert v3["protocol_id"] == "MODEL_V2_RESEARCH_PROTOCOL_V3"
    assert v3["parent_protocol"] == "MODEL_V2_RESEARCH_PROTOCOL_V2"
    lock = json.loads(V3_LOCK.read_text(encoding="utf-8"))
    assert lock["parent_protocol"] == "MODEL_V2_RESEARCH_PROTOCOL_V2"
    assert lock["v1_unmodified"] is True
    assert lock["v2_unmodified"] is True


def test_v3_changes_only_declared_drift_fields() -> None:
    v2 = yaml.safe_load(V2_YAML.read_text(encoding="utf-8"))
    v3 = _load_v3()

    unchanged_top_level_keys = [
        "fixed_scientific_constants",
        "model_seeds",
        "primary_metrics",
        "patient_cluster_bootstrap",
        "architectures",
        "architecture_search_policy",
        "feature_ablation_contract",
        "hybrid_trigger",
        "loss_and_sampling",
        "optimizer_experiment",
        "calibration_policy",
        "post_freeze_second_look",
        "runtime_acceptance_guardrails",
        "downstream_impact",
    ]
    for key in unchanged_top_level_keys:
        assert v2[key] == v3[key], f"{key} changed between V2 and V3"

    # official_validation changed only in the declared sub-fields
    ov2 = v2["official_validation"]
    ov3 = v3["official_validation"]
    for key in ov2:
        if key in {"early_stopping_checkpoint_selection", "promotion_requirement"}:
            continue
        assert ov2[key] == ov3[key], f"official_validation.{key} changed unexpectedly"

    p2 = ov2["promotion_requirement"]
    p3 = ov3["promotion_requirement"]
    for key in p2:
        if key == "auroc_material_regression_forbidden":
            continue
        assert p2[key] == p3[key], f"promotion_requirement.{key} changed unexpectedly"


def test_official_validation_cannot_be_early_stop_source() -> None:
    v3 = _load_v3()
    split = v3["final_train_role_split"]
    assert "early_stopping" in split["official_validation_forbidden_roles"]
    assert "early_stopping_metric" in split["final_inner_validation_controls"]


def test_official_validation_cannot_be_scheduler_source() -> None:
    v3 = _load_v3()
    split = v3["final_train_role_split"]
    assert "scheduler" in split["official_validation_forbidden_roles"]
    assert "scheduler_metric" in split["final_inner_validation_controls"]


def test_official_validation_cannot_be_checkpoint_source() -> None:
    v3 = _load_v3()
    split = v3["final_train_role_split"]
    assert "checkpoint_selection" in split["official_validation_forbidden_roles"]
    assert "checkpoint_selection_metric" in split["final_inner_validation_controls"]
    assert (
        v3["official_validation"]["early_stopping_checkpoint_selection"]
        == "FINAL_TRAIN_INNER_VALIDATION_LOCKED_V3_ROLE"
    )


def test_pos_weight_derives_only_from_optimise() -> None:
    v3 = _load_v3()
    split = v3["final_train_role_split"]
    assert split["pos_weight_formula"] == "negative_OPTIMISE_windows / positive_OPTIMISE_windows"
    assert "pos_weight" in split["optimise_controls"]
    assert "pos_weight" in split["official_validation_forbidden_roles"]


def test_fit_cap_is_90() -> None:
    v3 = _load_v3()
    assert v3["search_budget"]["d0_d5_max_neural_fits"] == 90


def test_v2_006_local_cap_is_15() -> None:
    v3 = _load_v3()
    assert v3["search_budget"]["v2_006_local_max_new_fits"] == 15


def test_v2_007_max_new_fits_is_6() -> None:
    v3 = _load_v3()
    assert v3["search_budget"]["v2_007_max_new_fits"] == 6


def test_cumulative_budget_feasible() -> None:
    v3 = _load_v3()
    budget = v3["search_budget"]
    assert budget["completed_neural_fits_before_v2_006"] == 50
    assert budget["max_cumulative_after_v2_006"] == 65
    assert budget["max_cumulative_through_v2_007"] == 71
    assert budget["max_cumulative_through_v2_007"] <= budget["d0_d5_max_neural_fits"]


def test_d5_hard_promotion_criteria_unchanged_auprc_rules() -> None:
    v3 = _load_v3()
    promotion = v3["official_validation"]["promotion_requirement"]
    assert promotion["mean_three_seed_validation_auprc_min"] == 0.646
    assert (
        promotion[
            "paired_patient_cluster_bootstrap_delta_auprc_vs_model_v1_lower_95_ci_bound_min"
        ]
        == 0.0
    )


def test_auroc_not_an_extra_d5_hard_gate() -> None:
    v3 = _load_v3()
    promotion = v3["official_validation"]["promotion_requirement"]
    assert promotion["auroc_material_regression_forbidden"] is False
    assert promotion["auroc_role"] == "SECONDARY_DIAGNOSTIC_REPORTED_NOT_A_D5_HARD_GATE"


def test_runtime_auroc_guard_remains_separate() -> None:
    v2 = yaml.safe_load(V2_YAML.read_text(encoding="utf-8"))
    v3 = _load_v3()
    assert v3["runtime_acceptance_guardrails"] == v2["runtime_acceptance_guardrails"]
    assert "INCART" in v3["runtime_acceptance_guardrails"]


def test_release_seed_fixed_to_20260927() -> None:
    v3 = _load_v3()
    ov = v3["official_validation"]
    assert ov["release_checkpoint_seed"] == 20260927
    assert ov["release_checkpoint_seed_fixed_regardless_of_score"] is True


def test_cal_v2_ordering_present_and_not_contingent_on_runtime() -> None:
    v3 = _load_v3()
    ordering = v3["cal_v2_ordering"]
    assert ordering["cal_v2_contingent_on_runtime_acceptance"] is False
    assert ordering["chronology"][0] == "MODEL_V2_official_validation"
    assert "CAL_V2_fit_freeze" in ordering["chronology"]
    assert ordering["chronology"].index("CAL_V2_fit_freeze") < ordering["chronology"].index(
        "runtime_acceptance_decision"
    )


def test_model_v2_final_separate_from_runtime_acceptance() -> None:
    v3 = _load_v3()
    separation = v3["model_v2_final_vs_runtime_acceptance"]
    assert separation["model_v1_remains_operational_if_v2_not_runtime_accepted"] is True


def test_v3_lock_reproducible() -> None:
    before = V3_LOCK.read_text(encoding="utf-8")
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/freeze_research_protocol_v3_pre006.py")],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    after = V3_LOCK.read_text(encoding="utf-8")
    assert before == after


def test_v2_007_registry_matches_v3_contract() -> None:
    with (ROOT / "manifests/model_v2/task_registry_v1.csv").open(newline="") as handle:
        tasks = {row["task_id"]: row for row in csv.DictReader(handle)}
    notes = tasks["V2-007"]["notes"]
    assert "MITDB_TRAIN_FINAL_INNER_V2_V1" in notes
    assert "FINAL_INNER_VALIDATION" in notes
    assert "never provides gradient updates" in notes
    assert "never determines pos_weight" in notes
    assert tasks["V2-007"]["status"] == "NOT_STARTED"


def test_v2_008_registry_matches_v3_contract() -> None:
    with (ROOT / "manifests/model_v2/task_registry_v1.csv").open(newline="") as handle:
        tasks = {row["task_id"]: row for row in csv.DictReader(handle)}
    notes = tasks["V2-008"]["notes"]
    assert "mean three-seed official VALIDATION AUPRC > 0.646" in notes
    assert "lower-95%-CI bound > 0" in notes
    assert "secondary diagnostic" in notes
    assert "NOT an additional hard D5 promotion gate" in notes
    assert tasks["V2-008"]["status"] == "NOT_STARTED"


def test_component_registry_v3_row_additive() -> None:
    with (ROOT / "manifests/model_v2/component_registry_v1.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    v3_row = next(r for r in rows if r["component_id"] == "MODEL_V2_RESEARCH_PROTOCOL_V3")
    assert v3_row["predecessor_id"] == "MODEL_V2_RESEARCH_PROTOCOL_V2"
    assert v3_row["status"] == "FROZEN_RESEARCH_PROTOCOL"
    v1_row = next(r for r in rows if r["component_id"] == "MODEL_V2_RESEARCH_PROTOCOL_V1")
    v2_row = next(r for r in rows if r["component_id"] == "MODEL_V2_RESEARCH_PROTOCOL_V2")
    assert v1_row["status"] == "FROZEN_RESEARCH_PROTOCOL"
    assert v2_row["status"] == "FROZEN_RESEARCH_PROTOCOL"
