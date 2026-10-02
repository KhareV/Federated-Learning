"""V2-002 pre-training configuration/manifest tests (Section 11/26).

Metadata-only and synthetic checks: CV-role closure for all 5 outer folds, experiment-ID
coverage of the full 5x3=15 matrix, config parsing, and fresh-initialization behavior. None of
these read real waveform data except role closure (which reads only the frozen CSV manifests
-- participant_group_id/role columns, no ECG floats)."""

from __future__ import annotations

import itertools

import torch
import yaml

import scripts._v2_002_lib as lib

V2_CONFIG = yaml.safe_load(lib.V2_CONFIG_PATH.read_text(encoding="utf-8"))


def test_role_closure_holds_for_every_outer_fold() -> None:
    for fold in lib.OUTER_FOLDS:
        roles = lib.role_groups_for_fold(fold)
        lib.verify_role_closure(roles)
        assert len(roles.inner_groups) == 4
        assert set(roles.optimise_groups).isdisjoint(roles.inner_groups)
        assert set(roles.optimise_groups).isdisjoint(roles.outer_groups)
        assert set(roles.inner_groups).isdisjoint(roles.outer_groups)


def test_optimise_patient_counts_match_expected() -> None:
    expected = {0: 17, 1: 17, 2: 18, 3: 18, 4: 18}
    for fold, count in expected.items():
        roles = lib.role_groups_for_fold(fold)
        assert len(roles.optimise_groups) == count


def test_outer_patient_counts_match_expected() -> None:
    expected = {0: 6, 1: 6, 2: 5, 3: 5, 4: 5}
    for fold, count in expected.items():
        roles = lib.role_groups_for_fold(fold)
        assert len(roles.outer_groups) == count


def test_experiment_matrix_has_exactly_15_unique_ids() -> None:
    ids = {lib.experiment_id(fold, seed) for fold in lib.OUTER_FOLDS for seed in lib.SEEDS}
    assert len(ids) == 15


def test_each_seed_covers_all_five_folds_no_fourth_seed() -> None:
    assert len(lib.SEEDS) == 3
    assert set(lib.SEEDS) == {20260927, 20260928, 20260929}
    ids = {lib.experiment_id(fold, seed) for fold in lib.OUTER_FOLDS for seed in lib.SEEDS}
    for seed in lib.SEEDS:
        folds_covered = {
            eid for eid in ids if eid.endswith(f"S{seed}")
        }
        assert len(folds_covered) == len(lib.OUTER_FOLDS)


def test_predeclared_run_order_matches_matrix() -> None:
    run_order = V2_CONFIG["run_order"]
    assert len(run_order) == 15
    pairs = [(entry["outer_fold"], entry["seed"]) for entry in run_order]
    assert pairs == list(itertools.product(lib.OUTER_FOLDS, lib.SEEDS))


def test_config_binds_expected_ids() -> None:
    assert V2_CONFIG["reference_id"] == "MODEL_V1_CV_REFERENCE_V1"
    assert V2_CONFIG["research_protocol_id"] == "MODEL_V2_RESEARCH_PROTOCOL_V1"
    assert V2_CONFIG["outer_cv_manifest_id"] == "MITDB_TRAIN_CV_V2_V1"
    assert V2_CONFIG["inner_cv_manifest_id"] == "MITDB_TRAIN_INNER_V2_V1"
    assert V2_CONFIG["seeds"] == [20260927, 20260928, 20260929]
    assert V2_CONFIG["total_fits"] == 15
    assert V2_CONFIG["not_calibrated"] is True
    assert V2_CONFIG["not_a_release_model"] is True
    assert V2_CONFIG["no_held_out_official_partition_accessed"] is True


def test_training_contract_matches_t015_semantics() -> None:
    contract = V2_CONFIG["training_contract"]
    assert contract["loss"] == "BCEWithLogitsLoss"
    assert contract["optimizer"] == "AdamW"
    assert contract["learning_rate"] == 0.001
    assert contract["weight_decay"] == 0.0001
    assert contract["batch_size"] == 64
    assert contract["max_epochs"] == 50
    assert contract["early_stopping_patience"] == 7
    assert contract["scheduler"] == "ReduceLROnPlateau"
    assert contract["fresh_initialization"] is True
    assert contract["load_model_v1_checkpoint"] is False
    assert contract["pos_weight_source"] == "OPTIMISE_SUBSET_ONLY"


def test_augmentation_scope_is_optimise_only() -> None:
    pipeline = V2_CONFIG["input_pipeline"]
    assert pipeline["augmentation_scope"] == "OPTIMISE_ONLY"
    assert pipeline["inner_validation_augmentation"] is False
    assert pipeline["outer_test_augmentation"] is False
    assert pipeline["execution_order"] == "FILTERED_WINDOW_THEN_AUGMENT_THEN_PER_WINDOW_ZSCORE"
    assert pipeline["normalization_epsilon"] == 1.0e-8


def test_model_v1_exact_parameter_count() -> None:
    model = lib.build_model_v1()
    params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    assert params == 13185


def test_fresh_initialization_never_loads_checkpoint(monkeypatch) -> None:
    """build_model_v1() must never read checkpoints/MODEL_V1.pt -- confirmed both by not
    calling torch.load anywhere in its implementation and by two fresh constructions
    producing different initial weights."""
    import models.ecg_cnn as ecg_cnn

    called = {"torch_load": False}
    original_load = torch.load

    def _tracking_load(*args, **kwargs):
        called["torch_load"] = True
        return original_load(*args, **kwargs)

    monkeypatch.setattr(torch, "load", _tracking_load)
    model = ecg_cnn.build_model_v1()
    assert called["torch_load"] is False
    assert isinstance(model, ecg_cnn.ModelV1)


def test_two_fresh_initializations_without_seed_differ() -> None:
    import models.ecg_cnn as ecg_cnn

    torch.manual_seed(1)
    a = ecg_cnn.build_model_v1()
    torch.manual_seed(2)
    b = ecg_cnn.build_model_v1()
    weight_a = next(a.parameters()).detach().clone()
    weight_b = next(b.parameters()).detach().clone()
    assert not torch.allclose(weight_a, weight_b)


def test_bootstrap_config_matches_protocol() -> None:
    bootstrap = V2_CONFIG["bootstrap"]
    assert bootstrap["replicates"] == 2000
    assert bootstrap["bootstrap_seed"] == 20261002
    assert bootstrap["source_clusters"] == 27
    assert bootstrap["slots_per_replicate"] == 27
    assert bootstrap["multiplicity_preserved"] is True
    assert bootstrap["window_bootstrap"] is False
    assert bootstrap["rejection_redraw"] is False


def test_search_budget_matches_protocol() -> None:
    budget = V2_CONFIG["search_budget"]
    assert budget["first_line_neural_fit_cap"] == 100
    assert budget["v2_002_fits"] == 15
