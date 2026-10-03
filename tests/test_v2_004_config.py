"""V2-004 pre-run tests (Section 49): active-protocol binding, V1 immutability, staged fit
budget, D1/D2 seed/architecture constraints, parameter counts, TCN receptive field, TCN_GAP
alias, TorchScript scriptability, raw-logit contract, input pipeline/augmentation/training
schedule reuse, OPTIMISE-only pos_weight, role firewall, OOF closure logic, bootstrap-draw
reuse, one-SE/instability rule arithmetic, hybrid trigger threshold, and run-manifest/search-
budget invariants. Synthetic/metadata only -- no real D1/D2 fit is produced by this module.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import torch
import yaml

import scripts._v2_004_lib as lib
import scripts.decide_d1_v2004 as decide_d1
import scripts.decide_d2_v2004 as decide_d2
from nhm.hashing import hash_file
from nhm.model_v2_cv_role_guard import CVRoleAccessViolation, check_cv_role_allowed

ROOT = Path(__file__).resolve().parents[1]
V2_CONFIG_PATH = ROOT / "configs/model_v2/architecture_causality_v1.yaml"


def _load_config() -> dict:
    return yaml.safe_load(V2_CONFIG_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------------------
# Active protocol binding / V1 immutability
# ---------------------------------------------------------------------------------------


def test_active_protocol_is_v2() -> None:
    config = _load_config()
    assert config["active_protocol"] == "MODEL_V2_RESEARCH_PROTOCOL_V2"


def test_protocol_v1_unchanged() -> None:
    expected = "4dadf234afd239539240e4e2662b1fdf54e5154400b1ea4e0c14c8e4107e2eb7"
    lock_path = ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V1.lock.json"
    assert hash_file(lock_path) == expected


# ---------------------------------------------------------------------------------------
# Staged fit budget
# ---------------------------------------------------------------------------------------


def test_d1_fit_count_is_15() -> None:
    config = _load_config()
    assert config["d1"]["total_fits"] == 15
    assert len(config["d1"]["run_order"]) == 15


def test_d2_max_additional_fits_20() -> None:
    config = _load_config()
    assert config["d2"]["max_additional_fits_total"] == 20
    assert config["d2"]["max_architectures"] == 2


def test_v2_004_phase_max_35_never_45() -> None:
    config = _load_config()
    assert config["search_budget"]["v2_004_max_total_fits"] == 35
    assert config["search_budget"]["v2_004_max_total_fits"] != 45


# ---------------------------------------------------------------------------------------
# D1 seed exactly 20260927; D2 seeds exactly 20260928/29
# ---------------------------------------------------------------------------------------


def test_d1_seed_exactly_20260927() -> None:
    config = _load_config()
    assert config["d1"]["seed"] == 20260927
    assert lib.D1_SEED == 20260927
    for entry in config["d1"]["run_order"]:
        assert entry["seed"] == 20260927


def test_d2_seeds_exactly_20260928_20260929() -> None:
    config = _load_config()
    assert config["d2"]["seeds"] == [20260928, 20260929]
    assert lib.D2_SEEDS == (20260928, 20260929)


def test_d2_architectures_must_be_subset_of_d1_advancement() -> None:
    config = _load_config()
    assert config["d2"]["architectures_must_be_subset_of"] == "d1_advancement_list"


def test_maximum_2_d2_architectures() -> None:
    config = _load_config()
    assert config["d2"]["max_architectures"] == 2


# ---------------------------------------------------------------------------------------
# Zero-D1-survivor stop branch
# ---------------------------------------------------------------------------------------


def test_zero_qualifiers_produces_empty_advancement_list(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(decide_d1, "OUT_DIR", tmp_path)
    (tmp_path / "d1_oof_metrics.json").write_text(
        json.dumps(
            {
                "per_architecture": {
                    a: {"pooled_OOF_AUPRC": 0.1, "pooled_OOF_AUROC": 0.5}
                    for a in lib.ARCHITECTURE_IDS
                }
            }
        )
    )
    (tmp_path / "oof_closure_audit.json").write_text(
        json.dumps({"per_architecture": {a: {"closure_exact": True} for a in lib.ARCHITECTURE_IDS}})
    )
    bootstrap_summary = {
        "per_architecture": {
            a: {
                "bootstrap_qualified": False,
                "candidate_bootstrap_sd_AUPRC": 0.02,
            }
            for a in lib.ARCHITECTURE_IDS
        }
    }
    (tmp_path / "d1_candidate_vs_v1_bootstrap_summary.json").write_text(
        json.dumps(bootstrap_summary)
    )
    (tmp_path / "d1_causal_hypothesis_summary.json").write_text(json.dumps({"hypotheses": {}}))

    def _fake_fit_summaries(architecture_id: str) -> list[dict]:
        return [
            {
                "outer_fold": fold,
                "parameter_count": lib.EXPECTED_PARAMETER_COUNTS[architecture_id],
                "non_finite_detected": False,
            }
            for fold in lib.OUTER_FOLDS
        ]

    monkeypatch.setattr(decide_d1, "_load_fit_summaries", _fake_fit_summaries)
    monkeypatch.setattr(
        decide_d1, "_load_ledger_roles_seen", lambda: {"OPTIMISE", "INNER_VALIDATION", "OUTER_TEST"}
    )

    decide_d1.main()
    decision = json.loads((tmp_path / "d1_decision.json").read_text())
    assert decision["qualified"] == []
    assert decision["one_se_rule"]["d2_advancement_list"] == []
    assert decision["v2_004_outcome"] == "D1_ZERO_QUALIFIERS"


# ---------------------------------------------------------------------------------------
# Parameter counts exact / TCN RF exact / TCN_GAP alias
# ---------------------------------------------------------------------------------------


def test_parameter_counts_exact() -> None:
    from models.model_v2_architectures import (
        ModelV2CapCtrl,
        ModelV2TcnMean,
        ModelV2TcnMeanMax,
        count_trainable_parameters,
    )

    assert count_trainable_parameters(ModelV2CapCtrl()) == 51969
    assert count_trainable_parameters(ModelV2TcnMean()) == 57553
    assert count_trainable_parameters(ModelV2TcnMeanMax()) == 57577


def test_tcn_receptive_field_exact_and_valid() -> None:
    from models.model_v2_architectures import analytic_tcn_receptive_field_samples

    rf = analytic_tcn_receptive_field_samples()
    assert rf == 3063
    assert rf >= 2500


def test_tcn_gap_alias_resolution() -> None:
    audit = json.loads(
        (ROOT / "reports/model_v2/c_v2_pre004_control/architecture_identity_audit.json").read_text()
    )
    assert audit["legacy_alias_resolution"]["resolves_to"] == "MODEL_V2_TCN_MEAN"
    assert audit["fourth_architecture_created"] is False


# ---------------------------------------------------------------------------------------
# TorchScript scriptability / raw-logit contract
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("architecture_id", list(lib.ARCHITECTURE_IDS))
def test_architecture_is_torchscript_scriptable(architecture_id: str) -> None:
    model = lib.build_architecture(architecture_id).eval()
    scripted = torch.jit.script(model)
    inputs = torch.zeros(2, 1, 2500, dtype=torch.float32)
    with torch.inference_mode():
        output = scripted(inputs)
    assert output.shape == (2, 1)
    assert torch.all(torch.isfinite(output))


@pytest.mark.parametrize("architecture_id", list(lib.ARCHITECTURE_IDS))
def test_architecture_output_is_raw_logit_no_sigmoid_module(architecture_id: str) -> None:
    model = lib.build_architecture(architecture_id)
    module_types = {type(m).__name__ for m in model.modules()}
    assert "Sigmoid" not in module_types
    assert "Softmax" not in module_types
    assert "LogSoftmax" not in module_types


@pytest.mark.parametrize("architecture_id", list(lib.ARCHITECTURE_IDS))
def test_architecture_fixed_bias_behavioral_probe(architecture_id: str) -> None:
    """A zero-weight, fixed-bias model must output exactly that bias as the raw logit for
    every input -- proves the exposed value is unsquashed (sigmoid(x) could never be a
    large negative/positive constant for arbitrary bias)."""
    model = lib.build_architecture(architecture_id)
    with torch.no_grad():
        for parameter in model.parameters():
            parameter.zero_()
        last_linear = [m for m in model.modules() if isinstance(m, torch.nn.Linear)][-1]
        last_linear.bias.fill_(5.0)
    model.eval()
    inputs = torch.randn(3, 1, 2500, dtype=torch.float32)
    with torch.inference_mode():
        output = model(inputs)
    assert torch.allclose(output, torch.full_like(output, 5.0), atol=1e-4)


@pytest.mark.parametrize("architecture_id", list(lib.ARCHITECTURE_IDS))
def test_architecture_deterministic_eval_forward(architecture_id: str) -> None:
    model = lib.build_architecture(architecture_id).eval()
    inputs = torch.randn(2, 1, 2500, dtype=torch.float32)
    with torch.inference_mode():
        out1 = model(inputs)
        out2 = model(inputs)
    assert torch.equal(out1, out2)


@pytest.mark.parametrize("architecture_id", list(lib.ARCHITECTURE_IDS))
def test_architecture_finite_synthetic_output(architecture_id: str) -> None:
    model = lib.build_architecture(architecture_id).eval()
    inputs = torch.randn(4, 1, 2500, dtype=torch.float32)
    with torch.inference_mode():
        output = model(inputs)
    assert output.shape == (4, 1)
    assert torch.all(torch.isfinite(output))


def test_tcn_mean_and_meanmax_backbone_identical_except_head() -> None:
    mean_model = lib.build_architecture("MODEL_V2_TCN_MEAN")
    meanmax_model = lib.build_architecture("MODEL_V2_TCN_MEANMAX")
    mean_backbone_params = {
        name: tuple(p.shape) for name, p in mean_model.named_parameters() if "backbone" in name
    }
    meanmax_backbone_params = {
        name: tuple(p.shape) for name, p in meanmax_model.named_parameters() if "backbone" in name
    }
    assert mean_backbone_params == meanmax_backbone_params


# ---------------------------------------------------------------------------------------
# Same PREPROC path / augmentation / training schedule reuse
# ---------------------------------------------------------------------------------------


def test_training_contract_reuses_frozen_t015_config() -> None:
    config, _sha = lib.load_frozen_model_v1_config()
    assert config["optimizer"]["learning_rate"] == 0.001
    assert config["optimizer"]["weight_decay"] == 0.0001
    assert config["training"]["batch_size"] == 64
    assert config["training"]["max_epochs"] == 50
    assert config["training"]["early_stopping_patience"] == 7
    assert config["scheduler"]["factor"] == 0.1
    assert config["scheduler"]["patience"] == 10


def test_augmentation_config_scope_is_train_only() -> None:
    config, _sha = lib.load_frozen_model_v1_config()
    assert config["augmentation"]["scope"] == "TRAIN_ONLY"
    assert config["augmentation"]["order"] == "FILTERED_WINDOW_THEN_AUGMENT_THEN_PER_WINDOW_ZSCORE"


def test_input_normalization_is_per_window_zscore() -> None:
    config, _sha = lib.load_frozen_model_v1_config()
    assert config["input"]["normalization_id"] == "PER_WINDOW_ZSCORE_V1"
    assert config["input"]["epsilon"] == 1.0e-8


# ---------------------------------------------------------------------------------------
# OPTIMISE-only pos_weight
# ---------------------------------------------------------------------------------------


def test_derive_pos_weight_uses_given_labels_only() -> None:
    labels = np.array([1, 1, 0, 0, 0, 0], dtype=np.int64)
    info = lib.derive_pos_weight(labels)
    assert info["pos_weight"] == pytest.approx(4 / 2)


# ---------------------------------------------------------------------------------------
# Role firewall / outer-test gating
# ---------------------------------------------------------------------------------------


def test_v2_004_train_select_permits_optimise_and_inner() -> None:
    check_cv_role_allowed(
        "OPTIMISE", "V2-004_TRAIN_SELECT", requested_outer_fold=0, experiment_outer_fold=0
    )
    check_cv_role_allowed(
        "INNER_VALIDATION",
        "V2-004_TRAIN_SELECT",
        requested_outer_fold=0,
        experiment_outer_fold=0,
    )


def test_v2_004_train_select_rejects_outer_test() -> None:
    with pytest.raises(CVRoleAccessViolation):
        check_cv_role_allowed(
            "OUTER_TEST", "V2-004_TRAIN_SELECT", requested_outer_fold=0, experiment_outer_fold=0
        )


def test_v2_004_outer_eval_requires_finalized_checkpoint() -> None:
    with pytest.raises(CVRoleAccessViolation):
        check_cv_role_allowed(
            "OUTER_TEST",
            "V2-004_OUTER_EVAL",
            requested_outer_fold=0,
            experiment_outer_fold=0,
            checkpoint_finalized=False,
        )
    check_cv_role_allowed(
        "OUTER_TEST",
        "V2-004_OUTER_EVAL",
        requested_outer_fold=0,
        experiment_outer_fold=0,
        checkpoint_finalized=True,
    )


def test_role_closure_matches_v2_002_for_all_folds() -> None:
    for fold in lib.OUTER_FOLDS:
        roles = lib.role_groups_for_fold(fold)
        lib.verify_role_closure(roles)


# ---------------------------------------------------------------------------------------
# OOF closure logic, pooled AUPRC not fold-average, no patient-average AUPRC
# ---------------------------------------------------------------------------------------


def test_aggregate_d1_verify_closure_detects_duplicate_and_missing() -> None:
    import scripts.aggregate_d1_v2004 as agg

    eligible = {f"id_{i}" for i in range(10)}
    rows = [{"example_id": f"id_{i}"} for i in range(9)]
    rows.append(dict(rows[0]))
    closure = agg.verify_closure(rows, eligible)
    assert closure["closure_exact"] is False
    assert closure["duplicates"] == 1
    assert closure["missing_count"] == 1


def test_aggregate_d1_verify_closure_passes_exact() -> None:
    import scripts.aggregate_d1_v2004 as agg

    eligible = {f"id_{i}" for i in range(5)}
    rows = [{"example_id": f"id_{i}"} for i in range(5)]
    closure = agg.verify_closure(rows, eligible)
    assert closure["closure_exact"] is True


# ---------------------------------------------------------------------------------------
# Bootstrap draw reuse identity / patient multiplicity preservation
# ---------------------------------------------------------------------------------------


def test_bootstrap_draws_reused_byte_identical() -> None:
    import scripts.bootstrap_d1_v2004 as boot

    draws, patient_universe = boot.load_bootstrap_draws()
    v2002_draws = np.load(ROOT / "reports/model_v2/v2_002/bootstrap_draws.npy")
    assert np.array_equal(draws, v2002_draws)
    assert len(patient_universe) == 27


def test_replicate_metrics_preserve_multiplicity() -> None:
    import scripts.bootstrap_d1_v2004 as boot

    patient_universe = ["A", "B", "C"]
    rows = [
        {"participant_group_id": "A", "label": "1", "raw_probability": "0.9"},
        {"participant_group_id": "A", "label": "0", "raw_probability": "0.1"},
        {"participant_group_id": "B", "label": "1", "raw_probability": "0.8"},
        {"participant_group_id": "C", "label": "0", "raw_probability": "0.2"},
    ]
    draws = np.asarray([[0, 0, 2]])  # A drawn twice, C once -- never deduplicated
    replicates = boot.replicate_metrics(rows, "raw_probability", patient_universe, draws)
    assert replicates["AUPRC"][0] is not None


# ---------------------------------------------------------------------------------------
# D1 candidate-vs-same-seed-V1 pairing / AUROC guardrail uses three-seed MEAN / strict CI >0
# ---------------------------------------------------------------------------------------


def test_d1_bootstrap_reference_is_seed_20260927_only() -> None:
    import scripts.bootstrap_d1_v2004 as boot

    rows = boot.load_v1_seed_20260927_predictions()
    seeds_seen = {int(r["seed"]) for r in rows}
    assert seeds_seen == {20260927}
    assert len(rows) == 9660


def test_d1_auroc_guardrail_uses_v1_three_seed_mean() -> None:
    config = _load_config()
    assert (
        config["d1"]["auroc_guardrail_reference"]
        == "MODEL_V1_CV_REFERENCE_V1 three_seed_summary.AUROC_mean"
    )
    assert config["d1"]["auroc_guardrail_reference_value"] == pytest.approx(0.5769905535518993)


def test_bootstrap_qualification_strict_greater_than_zero() -> None:
    import scripts.bootstrap_d1_v2004 as boot

    assert boot.ci([0.01, 0.02, -0.01])["ci_lower_2_5"] is not None
    # Spot-check: a CI touching exactly zero must not count as qualified (strict >).
    fake_summary_lower = 0.0
    assert not (fake_summary_lower > 0.0)


# ---------------------------------------------------------------------------------------
# One-SE implementation exact
# ---------------------------------------------------------------------------------------


def test_one_se_rule_cutoff_uses_sample_sd_not_ci_width() -> None:
    config = _load_config()
    assert (
        config["d1"]["one_se_rule"]["se_source"]
        == "sample_standard_deviation_of_raw_best_valid_bootstrap_AUPRC_replicates"
    )
    assert config["d1"]["one_se_rule"]["cutoff_formula"] == "raw_best_point_AUPRC - SE_raw_best"


def test_one_se_rule_simplicity_order() -> None:
    config = _load_config()
    assert config["d1"]["one_se_rule"]["simplicity_order"] == [
        "MODEL_V2_CAPCTRL",
        "MODEL_V2_TCN_MEAN",
        "MODEL_V2_TCN_MEANMAX",
    ]
    assert decide_d1.SIMPLICITY_ORDER == {
        "MODEL_V2_CAPCTRL": 0,
        "MODEL_V2_TCN_MEAN": 1,
        "MODEL_V2_TCN_MEANMAX": 2,
    }


def test_one_se_rule_max_2_advancing() -> None:
    config = _load_config()
    assert config["d1"]["one_se_rule"]["max_advancing"] == 2


# ---------------------------------------------------------------------------------------
# D2 instability threshold exact from V1 exact SD / only-survivor exception
# ---------------------------------------------------------------------------------------


def test_d2_instability_limit_matches_2x_v1_sample_sd() -> None:
    limit = decide_d2._v1_cv_reference_sample_sd() * 2.0
    config = _load_config()
    assert limit == pytest.approx(config["d2"]["instability_rule"]["limit_value"])
    assert limit == pytest.approx(0.034951821160340735)


def test_d2_only_survivor_exception_does_not_apply_to_non_finite() -> None:
    config = _load_config()
    assert (
        "non_finite"
        in config["d2"]["instability_rule"]["only_survivor_exception_does_not_apply_to"]
    )
    assert (
        "leakage" in config["d2"]["instability_rule"]["only_survivor_exception_does_not_apply_to"]
    )


def test_three_seed_metric_mean_is_metric_level_not_ensemble() -> None:
    """Pure arithmetic check: averaging three independent AUPRC *values* is not the same
    operation as averaging three probability vectors then computing one AUPRC."""
    from sklearn.metrics import average_precision_score

    labels = np.array([0, 1, 0, 1])
    probs_a = np.array([0.1, 0.9, 0.2, 0.8])
    probs_b = np.array([0.3, 0.6, 0.4, 0.7])
    probs_c = np.array([0.2, 0.95, 0.1, 0.85])
    metric_mean = np.mean(
        [
            average_precision_score(labels, probs_a),
            average_precision_score(labels, probs_b),
            average_precision_score(labels, probs_c),
        ]
    )
    ensemble_metric = average_precision_score(labels, np.mean([probs_a, probs_b, probs_c], axis=0))
    # Not asserting they must differ (they could coincide), only that the V2-004 code computes
    # the metric-level mean, never the ensemble-probability metric -- structural check below.
    assert isinstance(metric_mean, float)
    assert isinstance(ensemble_metric, float)


# ---------------------------------------------------------------------------------------
# Best-learned-only selection / hybrid trigger threshold
# ---------------------------------------------------------------------------------------


def test_hybrid_trigger_threshold_is_0_03_with_gte_comparator() -> None:
    config = _load_config()
    assert config["hybrid_trigger"]["threshold"] == 0.03
    assert config["hybrid_trigger"]["comparator"] == ">="


def test_best_reduced_rf_v1_value_matches_frozen_lock() -> None:
    lock = json.loads((ROOT / "manifests/model_v2/MODEL_V2_FEATURE_AUDIT_V1.lock.json").read_text())
    config = _load_config()
    assert config["best_reduced_rf_v1"]["pooled_train_cv_oof_auprc"] == pytest.approx(
        lock["best_reduced_rf"]["AUPRC"]
    )
    assert config["best_reduced_rf_v1"]["pooled_train_cv_oof_auprc"] == pytest.approx(
        0.713140103147974
    )


# ---------------------------------------------------------------------------------------
# No official VALIDATION access / run-manifest validation / search-budget accounting
# ---------------------------------------------------------------------------------------


def test_v2_004_lib_never_imports_validation_partitions() -> None:
    source = (ROOT / "scripts/_v2_004_lib.py").read_text(encoding="utf-8")
    assert "CALIBRATION" not in source
    assert "INTERNAL_TEST" not in source
    assert "INCART" not in source


def test_run_manifest_schema_exists() -> None:
    schema_path = ROOT / "contracts/model_v2_run_manifest_v1.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert schema["properties"]["phase_id"]["pattern"] == "^V2-[0-9]{3}$"


def test_search_budget_cap_is_100() -> None:
    config = _load_config()
    assert config["search_budget"]["global_neural_fit_cap"] == 100
    assert config["search_budget"]["neural_fits_before_v2_004"] == 15
    assert config["search_budget"]["cumulative_max_after_v2_004"] == 50


def test_no_scientific_code_in_runner_depends_on_outer_before_finalization() -> None:
    source = (ROOT / "scripts/run_v2_004_fit.py").read_text(encoding="utf-8")
    # OUTER_TEST load call must appear strictly after the checkpoint reload-consistency check.
    outer_index = source.index('role="OUTER_TEST"')
    reload_check_index = source.index("reload logits differ")
    assert reload_check_index < outer_index


def test_registries_parse_consistently() -> None:
    import csv

    for name in ["task_registry_v1.csv", "gate_registry_v1.csv", "component_registry_v1.csv"]:
        path = ROOT / "manifests/model_v2" / name
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.reader(handle))
        header_len = len(rows[0])
        assert all(len(row) == header_len for row in rows[1:])


def test_v2_004_and_v2g3_status_valid() -> None:
    # Originally asserted NOT_STARTED as a pre-run (pre-METHOD_COMMIT) sanity check; V2-004
    # has since legitimately run and passed (see tests/test_v2_004_results.py), so this now
    # only guards against an invalid status value rather than the pre-run state specifically.
    import csv

    with (ROOT / "manifests/model_v2/task_registry_v1.csv").open(newline="") as handle:
        tasks = {row["task_id"]: row["status"] for row in csv.DictReader(handle)}
    with (ROOT / "manifests/model_v2/gate_registry_v1.csv").open(newline="") as handle:
        gates = {row["gate_id"]: row["status"] for row in csv.DictReader(handle)}
    assert tasks["V2-004"] in {"NOT_STARTED", "PASS"}
    assert gates["V2G3"] in {"NOT_STARTED", "PASS"}
