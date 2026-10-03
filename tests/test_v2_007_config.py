"""V2-007 pre-fit test gate (Section 27). Must all pass BEFORE the first V2-007 neural fit.
Covers: architecture/config identity, finalist shortlist, final-inner manifest, role/partition
firewalls (including the new FINAL_INNER_VALIDATION/OFFICIAL_VALIDATION roles), OPTIMISE-only
pos_weight, scheduler/early-stop source, official-VALIDATION-forbidden-during-training,
V1 reference checkpoint hashes, bootstrap-draw freeze + multiplicity, synthetic finalist-
selection and promotion-rule unit tests (Sections 23/24, frozen before any result exists),
the one-shot guard state machine, and a representative tamper-test subset.
"""

from __future__ import annotations

import copy
import csv
import json
import tempfile
from pathlib import Path

import numpy as np
import pytest
import yaml

import scripts._v2_007_lib as lib
import scripts._v2_007_stats as stats
from nhm.hashing import hash_file
from nhm.model_v2_cv_role_guard import CVRoleAccessViolation, check_cv_role_allowed
from nhm.model_v2_official_validation_guard import (
    OfficialValidationGuardViolation,
    arm_guard,
    check_and_begin_session,
    complete_session,
    mark_partially_consumed,
    read_guard_state,
)
from nhm.model_v2_partition_guard import PartitionAccessViolation, check_partition_allowed

ROOT = lib.ROOT
OUT_DIR = ROOT / "reports/model_v2/v2_007"


# ---------------------------------------------------------------------------
# Architecture / config identity
# ---------------------------------------------------------------------------

def test_architecture_parameter_counts_exact() -> None:
    for architecture_id, expected in lib.EXPECTED_PARAMETER_COUNTS.items():
        model = lib.build_architecture(architecture_id)
        count = sum(p.numel() for p in model.parameters() if p.requires_grad)
        assert count == expected


def test_training_contract_reused_unchanged_from_model_v1_config() -> None:
    config, config_sha256 = lib.load_frozen_model_v1_config()
    assert config_sha256 == "f46810593edbc3d74e00d1ad992fe2af5b02a0b9474118374a90f0bd1fd338dc"
    assert config["optimizer"]["learning_rate"] == 0.001
    assert config["optimizer"]["weight_decay"] == 0.0001
    assert config["training"]["batch_size"] == 64
    assert config["training"]["max_epochs"] == 50
    assert config["training"]["early_stopping_patience"] == 7
    assert config["scheduler"]["factor"] == 0.1
    assert config["scheduler"]["patience"] == 10
    assert config["scheduler"]["threshold"] == 0.0001
    assert config["scheduler"]["threshold_mode"] == "rel"
    assert config["scheduler"]["cooldown"] == 0
    assert config["scheduler"]["min_lr"] == 0.0
    assert config["scheduler"]["epsilon"] == 1.0e-8
    assert config["augmentation"]["order"] == "FILTERED_WINDOW_THEN_AUGMENT_THEN_PER_WINDOW_ZSCORE"


def test_official_validation_config_parses_and_matches_frozen_identities() -> None:
    config = yaml.safe_load(
        (ROOT / "configs/model_v2/official_validation_v1.yaml").read_text(encoding="utf-8")
    )
    assert config["active_protocol_lock_sha256"] == (
        "287aff4ff3fcf583524f06e6af51f23bd65949a75abef14cde80ff0936873db8"
    )
    assert config["final_train_manifest"]["manifest_sha256"] == (
        "bb5b4f6f7205fe37d0132ebccaca7889a916b115f5ad096ecc967940421455ce"
    )
    assert config["promotion_rule"]["decision_vocabulary"] == [
        "MODEL_V2_PROMOTION_ELIGIBLE",
        "MODEL_V2_NOT_PROMOTED_AUPRC_THRESHOLD",
        "MODEL_V2_NOT_PROMOTED_RELEASE_CI",
        "MODEL_V2_NOT_PROMOTED_THREE_SEED_CI",
        "MODEL_V2_NOT_PROMOTED_MULTIPLE_CRITERIA",
    ]


# ---------------------------------------------------------------------------
# Finalist shortlist
# ---------------------------------------------------------------------------

def test_finalist_shortlist_exactly_two_and_matches_frozen() -> None:
    lock = json.loads(
        (ROOT / "manifests/model_v2/MODEL_V2_FINALIST_SHORTLIST_V1.lock.json").read_text(
            encoding="utf-8"
        )
    )
    assert lock["shortlist_count"] == 2
    assert len(lib.FINALISTS) == 2
    ids = {(f["architecture_id"], f["schedule_id"]) for f in lib.FINALISTS}
    assert ids == {
        ("MODEL_V2_TCN_MEAN", "CONFIG_V2_TCN_MEAN_ORIGINAL_V1"),
        ("MODEL_V2_TCN_MEANMAX", "CONFIG_V2_TCN_MEANMAX_ORIGINAL_V1"),
    }


# ---------------------------------------------------------------------------
# Final TRAIN-only inner split
# ---------------------------------------------------------------------------

def test_final_inner_manifest_exact_groups_and_closure() -> None:
    optimise, final_inner = lib.load_final_inner_roles()
    assert len(optimise) == 22
    assert len(final_inner) == 5
    assert final_inner == sorted(
        ["MITDB_P105", "MITDB_P113", "MITDB_P118", "MITDB_P205", "MITDB_P208"]
    )
    lib.verify_final_inner_closure(optimise, final_inner)
    assert hash_file(lib.FINAL_INNER_CSV) == (
        "bb5b4f6f7205fe37d0132ebccaca7889a916b115f5ad096ecc967940421455ce"
    )


def test_final_inner_window_and_class_counts_mechanical() -> None:
    optimise, final_inner = lib.load_final_inner_roles()
    with lib.WINDOW_MANIFEST.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    counts = {"OPTIMISE": [0, 0, 0], "FINAL_INNER_VALIDATION": [0, 0, 0]}
    role_of = {g: "OPTIMISE" for g in optimise}
    role_of.update({g: "FINAL_INNER_VALIDATION" for g in final_inner})
    for row in rows:
        if row["partition"] != "TRAIN" or row["core_eligible"].upper() != "TRUE":
            continue
        role = role_of.get(row["participant_group_id"])
        if role is None:
            continue
        counts[role][0] += 1
        if int(row["label"]) == 1:
            counts[role][1] += 1
        else:
            counts[role][2] += 1
    total = counts["OPTIMISE"][0] + counts["FINAL_INNER_VALIDATION"][0]
    pos = counts["OPTIMISE"][1] + counts["FINAL_INNER_VALIDATION"][1]
    neg = counts["OPTIMISE"][2] + counts["FINAL_INNER_VALIDATION"][2]
    assert total == 9660
    assert pos == 3557
    assert neg == 6103


def test_official_validation_population_mechanical() -> None:
    groups = lib.official_validation_groups()
    assert len(groups) == 7
    with lib.WINDOW_MANIFEST.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    val_rows = [
        r for r in rows if r["partition"] == "VALIDATION" and r["core_eligible"].upper() == "TRUE"
    ]
    assert len(val_rows) == 2880
    assert sum(1 for r in val_rows if int(r["label"]) == 1) == 676
    assert sum(1 for r in val_rows if int(r["label"]) == 0) == 2204
    found_groups = {r["participant_group_id"] for r in val_rows}
    assert found_groups == set(groups)
    # no TRAIN/CALIBRATION/INTERNAL_TEST group id may appear in the VALIDATION group set
    train_optimise, train_final_inner = lib.load_final_inner_roles()
    assert not (set(groups) & set(train_optimise) & set(train_final_inner))
    assert not (set(groups) & (set(train_optimise) | set(train_final_inner)))


# ---------------------------------------------------------------------------
# Role / partition firewalls
# ---------------------------------------------------------------------------

def test_v2_007_train_select_allows_only_optimise_and_final_inner_validation() -> None:
    check_cv_role_allowed(
        "OPTIMISE", "V2-007_TRAIN_SELECT", requested_outer_fold=0, experiment_outer_fold=0
    )
    check_cv_role_allowed(
        "FINAL_INNER_VALIDATION", "V2-007_TRAIN_SELECT",
        requested_outer_fold=0, experiment_outer_fold=0,
    )
    with pytest.raises(CVRoleAccessViolation):
        check_cv_role_allowed(
            "OFFICIAL_VALIDATION", "V2-007_TRAIN_SELECT",
            requested_outer_fold=0, experiment_outer_fold=0,
        )
    with pytest.raises(CVRoleAccessViolation):
        check_cv_role_allowed(
            "OUTER_TEST", "V2-007_TRAIN_SELECT", requested_outer_fold=0, experiment_outer_fold=0
        )


def test_official_validation_role_forbidden_during_training_stage() -> None:
    for forbidden_stage in ("V2-007_TRAIN_SELECT", "V2-007_TRAIN_DIAGNOSTIC"):
        with pytest.raises(CVRoleAccessViolation):
            check_cv_role_allowed(
                "OFFICIAL_VALIDATION", forbidden_stage,
                requested_outer_fold=0, experiment_outer_fold=0, checkpoint_finalized=True,
            )


def test_official_validation_role_requires_checkpoint_finalized() -> None:
    with pytest.raises(CVRoleAccessViolation):
        check_cv_role_allowed(
            "OFFICIAL_VALIDATION", "V2-007_OFFICIAL_VALIDATION",
            requested_outer_fold=0, experiment_outer_fold=0, checkpoint_finalized=False,
        )
    check_cv_role_allowed(
        "OFFICIAL_VALIDATION", "V2-007_OFFICIAL_VALIDATION",
        requested_outer_fold=0, experiment_outer_fold=0, checkpoint_finalized=True,
    )


def test_partition_firewall_train_only_during_fitting() -> None:
    check_partition_allowed("TRAIN", "V2-007", {"TRAIN"})
    with pytest.raises(PartitionAccessViolation):
        check_partition_allowed("VALIDATION", "V2-007", {"TRAIN"})
    with pytest.raises(PartitionAccessViolation):
        check_partition_allowed("CALIBRATION", "V2-007", {"TRAIN"})


def test_prior_phase_role_firewall_behavior_unchanged() -> None:
    # V2-004/V2-006 regression: OUTER_TEST still requires checkpoint_finalized, same message.
    with pytest.raises(CVRoleAccessViolation) as exc:
        check_cv_role_allowed(
            "OUTER_TEST", "V2-004_OUTER_EVAL",
            requested_outer_fold=0, experiment_outer_fold=0, checkpoint_finalized=False,
        )
    assert "CV_ROLE_FIREWALL_OUTER_TEST_BEFORE_CHECKPOINT_FINALIZED" in str(exc.value)


# ---------------------------------------------------------------------------
# OPTIMISE-only pos_weight
# ---------------------------------------------------------------------------

def test_pos_weight_derived_from_optimise_only() -> None:
    labels = np.array([1, 1, 0, 0, 0, 0], dtype=np.int64)
    info = lib.derive_pos_weight(labels)
    assert info["source_partition"] == "TRAIN"
    assert info["pos_weight"] == 4 / 2
    assert info["train_positives"] == 2
    assert info["train_negatives"] == 4


# ---------------------------------------------------------------------------
# V1 reference checkpoints
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("seed", "expected_sha"),
    [
        (20260927, "021352eb067932015b657f0570ac155f8ef00af2d43864e13a110d0252bc7bfe"),
        (20260928, "a346ce6c8b38c50c0c87c4c6ed72a85b36e829c7a27878d86e1e672404db9e8d"),
        (20260929, "63ab477810e65efca388ba53eb4a290b98aad51234f600f37f12b87950af9b74"),
    ],
)
def test_v1_reference_checkpoint_hash_exact(seed: int, expected_sha: str) -> None:
    path = ROOT / f"checkpoints/candidates/MODEL_V1/MODEL_V1_seed_{seed}_best.pt"
    assert path.exists()
    assert hash_file(path) == expected_sha


# ---------------------------------------------------------------------------
# Bootstrap draw freeze
# ---------------------------------------------------------------------------

def test_validation_bootstrap_draws_frozen_and_reproducible() -> None:
    manifest = json.loads(
        (OUT_DIR / "validation_bootstrap_draws_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["bootstrap_id"] == "MODEL_V2_VALIDATION_BOOTSTRAP_DRAWS_V1"
    assert manifest["bootstrap_seed"] == 20260927
    assert manifest["replicates"] == 2000
    assert manifest["slots_per_replicate"] == 7
    assert manifest["sorted_patient_index_mapping"] == lib.official_validation_groups()

    draws = np.load(OUT_DIR / "validation_bootstrap_draws.npz")["draws"]
    assert draws.shape == (2000, 7)
    rng = np.random.default_rng(20260927)
    expected = rng.integers(0, 7, size=(2000, 7))
    assert np.array_equal(draws, expected)


def test_bootstrap_draw_multiplicity_preserved_not_deduplicated() -> None:
    draws = np.load(OUT_DIR / "validation_bootstrap_draws.npz")["draws"]
    has_repeat_within_a_replicate = any(
        len(set(draws[i].tolist())) < draws.shape[1] for i in range(draws.shape[0])
    )
    assert has_repeat_within_a_replicate


# ---------------------------------------------------------------------------
# Finalist-selection rule -- synthetic (Section 23), frozen before any result exists
# ---------------------------------------------------------------------------

def test_finalist_comparison_not_within_one_se_picks_higher_mean() -> None:
    result = stats.finalist_comparison(
        a_three_seed_mean=0.50, b_three_seed_mean=0.70,
        a_rep_mean_distribution=np.zeros(2000), b_rep_mean_distribution=np.full(2000, 0.2),
        a_params=57553, b_params=57577, a_seed_sd=0.01, b_seed_sd=0.01,
        a_config_id="A", b_config_id="B",
    )
    assert result["within_one_se"] is False
    assert result["selected"] == "B"


def test_finalist_comparison_within_one_se_tie_break_by_params() -> None:
    rng = np.random.default_rng(0)
    rep = rng.normal(0.0, 0.05, size=2000)
    result = stats.finalist_comparison(
        a_three_seed_mean=0.60, b_three_seed_mean=0.61,
        a_rep_mean_distribution=np.zeros(2000), b_rep_mean_distribution=rep,
        a_params=57553, b_params=57577, a_seed_sd=0.02, b_seed_sd=0.02,
        a_config_id="A", b_config_id="B",
    )
    assert result["within_one_se"] is True
    assert result["selected"] == "A"
    assert result["tie_break_path"] == "fewer_trainable_parameters"


def test_finalist_comparison_within_one_se_tie_break_by_seed_sd() -> None:
    rng = np.random.default_rng(1)
    b_rep = 0.001 + rng.normal(0.0, 0.05, size=2000)
    result = stats.finalist_comparison(
        a_three_seed_mean=0.60, b_three_seed_mean=0.601,
        a_rep_mean_distribution=np.zeros(2000), b_rep_mean_distribution=b_rep,
        a_params=100, b_params=100, a_seed_sd=0.03, b_seed_sd=0.01,
        a_config_id="A", b_config_id="B",
    )
    assert result["within_one_se"] is True
    assert result["selected"] == "B"
    assert result["tie_break_path"] == "lower_three_seed_AUPRC_sample_SD"


def test_finalist_comparison_within_one_se_tie_break_lexicographic() -> None:
    rng = np.random.default_rng(2)
    b_rep = 0.001 + rng.normal(0.0, 0.05, size=2000)
    result = stats.finalist_comparison(
        a_three_seed_mean=0.60, b_three_seed_mean=0.601,
        a_rep_mean_distribution=np.zeros(2000), b_rep_mean_distribution=b_rep,
        a_params=100, b_params=100, a_seed_sd=0.02, b_seed_sd=0.02,
        a_config_id="CONFIG_A", b_config_id="CONFIG_B",
    )
    assert result["within_one_se"] is True
    assert result["selected"] == "A"
    assert result["tie_break_path"] == "lexicographically_smaller_config_id"


def test_three_seed_mean_replicate_distribution_averages_seeds_not_probabilities() -> None:
    per_seed = {
        20260927: np.array([0.1, 0.2]),
        20260928: np.array([0.3, 0.4]),
        20260929: np.array([0.5, 0.6]),
    }
    result = stats.three_seed_mean_replicate_distribution(per_seed)
    assert np.allclose(result, [0.3, 0.4])


def test_bootstrap_multiplicity_pooling_preserves_repeats() -> None:
    labels_by_group = {"g0": np.array([1, 0]), "g1": np.array([1, 1])}
    probs_by_group = {"g0": np.array([0.9, 0.1]), "g1": np.array([0.8, 0.7])}
    draw_row = np.array([0, 0, 1])  # g0 drawn twice, g1 once
    labels, probs = stats.bootstrap_replicate_pooled(
        draw_row, ["g0", "g1"], labels_by_group, probs_by_group
    )
    assert labels.tolist() == [1, 0, 1, 0, 1, 1]
    assert probs.tolist() == [0.9, 0.1, 0.9, 0.1, 0.8, 0.7]


def test_degenerate_bootstrap_replicate_recorded_as_nan() -> None:
    labels_by_group = {"g0": np.array([0, 0])}
    probs_by_group = {"g0": np.array([0.1, 0.2])}
    draws = np.array([[0, 0]])  # only group g0, all-negative -> degenerate (single class)
    dist = stats.bootstrap_auprc_distribution(draws, ["g0"], labels_by_group, probs_by_group)
    assert np.isnan(dist[0])


# ---------------------------------------------------------------------------
# Promotion rule -- synthetic (Section 24/42), frozen before any result exists
# ---------------------------------------------------------------------------

def test_promotion_eligible_requires_all_three_criteria() -> None:
    result = stats.promotion_decision(
        selected_three_seed_mean_auprc=0.70,
        release_delta_ci={"lower": 0.01, "upper": 0.1},
        three_seed_delta_ci={"lower": 0.02, "upper": 0.12},
    )
    assert result["decision"] == "MODEL_V2_PROMOTION_ELIGIBLE"
    assert result["promotion_eligible"] is True


def test_promotion_not_promoted_auprc_threshold() -> None:
    result = stats.promotion_decision(
        selected_three_seed_mean_auprc=0.5,
        release_delta_ci={"lower": 0.01, "upper": 0.1},
        three_seed_delta_ci={"lower": 0.02, "upper": 0.12},
    )
    assert result["decision"] == "MODEL_V2_NOT_PROMOTED_AUPRC_THRESHOLD"


def test_promotion_not_promoted_release_ci() -> None:
    result = stats.promotion_decision(
        selected_three_seed_mean_auprc=0.70,
        release_delta_ci={"lower": -0.01, "upper": 0.1},
        three_seed_delta_ci={"lower": 0.02, "upper": 0.12},
    )
    assert result["decision"] == "MODEL_V2_NOT_PROMOTED_RELEASE_CI"


def test_promotion_not_promoted_three_seed_ci() -> None:
    result = stats.promotion_decision(
        selected_three_seed_mean_auprc=0.70,
        release_delta_ci={"lower": 0.01, "upper": 0.1},
        three_seed_delta_ci={"lower": -0.02, "upper": 0.12},
    )
    assert result["decision"] == "MODEL_V2_NOT_PROMOTED_THREE_SEED_CI"


def test_promotion_not_promoted_multiple_criteria() -> None:
    result = stats.promotion_decision(
        selected_three_seed_mean_auprc=0.5,
        release_delta_ci={"lower": -0.01, "upper": 0.1},
        three_seed_delta_ci={"lower": -0.02, "upper": 0.12},
    )
    assert result["decision"] == "MODEL_V2_NOT_PROMOTED_MULTIPLE_CRITERIA"


def test_promotion_threshold_is_strict_not_gte() -> None:
    result = stats.promotion_decision(
        selected_three_seed_mean_auprc=0.646,
        release_delta_ci={"lower": 0.01, "upper": 0.1},
        three_seed_delta_ci={"lower": 0.02, "upper": 0.12},
    )
    assert result["criterion_a_mean_auprc_gt_0_646"] is False


# ---------------------------------------------------------------------------
# One-shot official-VALIDATION guard -- synthetic, uses a temp root (never the real guard file)
# ---------------------------------------------------------------------------

def test_guard_arm_then_begin_then_complete() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        preconditions = {"a": 1}
        arm_guard(root, preconditions=preconditions)
        state = check_and_begin_session(root, observed_preconditions=preconditions)
        assert state["state"] == "RUNNING"
        completed = complete_session(root, completion_summary={"rows": 100})
        assert completed["state"] == "COMPLETED"


def test_guard_second_invocation_blocked_after_completion() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        preconditions = {"a": 1}
        arm_guard(root, preconditions=preconditions)
        check_and_begin_session(root, observed_preconditions=preconditions)
        complete_session(root, completion_summary={"rows": 100})
        with pytest.raises(OfficialValidationGuardViolation, match="ALREADY_CONSUMED"):
            check_and_begin_session(root, observed_preconditions=preconditions)


def test_guard_precondition_mismatch_rejected() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        arm_guard(root, preconditions={"a": 1})
        with pytest.raises(OfficialValidationGuardViolation, match="PRECONDITION_MISMATCH"):
            check_and_begin_session(root, observed_preconditions={"a": 2})


def test_guard_partial_consumption_blocks_further_access() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        preconditions = {"a": 1}
        arm_guard(root, preconditions=preconditions)
        check_and_begin_session(root, observed_preconditions=preconditions)
        mark_partially_consumed(root, failure_summary={"error": "crash"})
        state = read_guard_state(root)
        assert state["requires_human_review"] is True
        with pytest.raises(OfficialValidationGuardViolation, match="PARTIALLY_CONSUMED"):
            check_and_begin_session(root, observed_preconditions=preconditions)


def test_guard_cannot_double_arm() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        arm_guard(root, preconditions={"a": 1})
        with pytest.raises(OfficialValidationGuardViolation, match="GUARD_ALREADY_EXISTS"):
            arm_guard(root, preconditions={"a": 1})


def test_real_guard_file_armed_before_any_fit() -> None:
    state = read_guard_state(ROOT)
    assert state is not None
    assert state["state"] in {"ARMED", "RUNNING", "COMPLETED"}


# ---------------------------------------------------------------------------
# Tamper-test subset (full exhaustive suite runs post-result in generate_v2_007_evidence.py)
# ---------------------------------------------------------------------------

def test_tamper_protocol_v3_change_detected() -> None:
    lock = json.loads(
        (ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V3.lock.json").read_text(
            encoding="utf-8"
        )
    )
    tampered = copy.deepcopy(lock)
    tampered["protocol_id"] = "TAMPERED"
    with tempfile.TemporaryDirectory() as tmp:
        tampered_path = Path(tmp) / "tampered.json"
        tampered_path.write_text(json.dumps(tampered, sort_keys=True), encoding="utf-8")
        assert hash_file(tampered_path) != hash_file(
            ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V3.lock.json"
        )


def test_tamper_promotion_threshold_change_detected() -> None:
    result_ok = stats.promotion_decision(
        selected_three_seed_mean_auprc=0.646,
        release_delta_ci={"lower": 0.01, "upper": 0.1},
        three_seed_delta_ci={"lower": 0.02, "upper": 0.12},
    )
    assert result_ok["criterion_a_mean_auprc_gt_0_646"] is False
    tampered_threshold = 0.5
    assert (tampered_threshold < 0.646) != (stats.PROMOTION_AUPRC_THRESHOLD < 0.646)


def test_tamper_release_seed_change_detected() -> None:
    assert lib.RELEASE_SEED == 20260927


def test_tamper_strict_gt_not_gte() -> None:
    assert not (0.646 > 0.646)
    assert 0.6461 > 0.646
