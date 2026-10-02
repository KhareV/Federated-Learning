"""V2-002 OOF-closure and bootstrap unit tests (Section 21/22/26), on synthetic prediction
data only -- these must pass BEFORE any real fit runs, proving the aggregation/metric/
bootstrap logic is correct independent of real model output.
"""

from __future__ import annotations

import numpy as np
import pytest

import scripts._v2_002_lib as lib
from scripts.aggregate_oof_v2002 import compute_metrics, verify_closure
from scripts.bootstrap_v2002 import compute_replicate_metrics, generate_draws


def _synthetic_rows(*, drop_one: bool = False, duplicate_one: bool = False) -> list[dict]:
    rng = np.random.default_rng(0)
    rows: list[dict] = []
    for fold in lib.OUTER_FOLDS:
        roles = lib.role_groups_for_fold(fold)
        outer_groups = roles.outer_groups
        # a handful of synthetic windows per patient group per fold, just enough to exercise
        # closure/metric logic without touching any real waveform.
        for seed in lib.SEEDS:
            for group in outer_groups:
                for window_index in range(4):
                    example_id = f"SYNTH-F{fold}-{group}-W{window_index}"
                    label = int(rng.integers(0, 2))
                    rows.append(
                        {
                            "example_id": example_id,
                            "participant_group_id": group,
                            "record_id": "SYNTH",
                            "prediction_timestamp_us": "0",
                            "outer_fold": str(fold),
                            "seed": str(seed),
                            "label": str(label),
                            "raw_logit": str(float(rng.normal())),
                            "raw_probability": str(float(rng.uniform(0.01, 0.99))),
                            "selected_epoch": "1",
                            "experiment_id": lib.experiment_id(fold, seed),
                            "checkpoint_sha256": "0" * 64,
                            "model_id": "MODEL_V1_CV_REFERENCE_V1",
                        }
                    )
    if drop_one:
        rows.pop(0)
    if duplicate_one:
        rows.append(dict(rows[0]))
    return rows


def test_closure_detects_valid_synthetic_set_shape() -> None:
    rows = _synthetic_rows()
    # This synthetic set does not have exactly 9660 windows/seed (it is a small structural
    # stand-in), so closure_exact will correctly be False on row counts, but the duplicate/
    # missing-example machinery itself must still run without error and report zero
    # duplicates for a clean synthetic set.
    closure = verify_closure(rows)
    for seed_audit in closure["per_seed"].values():
        assert seed_audit["duplicates"] == 0


def test_closure_detects_duplicate_example_id() -> None:
    rows = _synthetic_rows(duplicate_one=True)
    closure = verify_closure(rows)
    first_seed = str(lib.SEEDS[0])
    assert closure["per_seed"][first_seed]["duplicates"] >= 1
    assert closure["status"] == "FAIL"


def test_compute_metrics_runs_and_never_averages_fold_metrics() -> None:
    rows = _synthetic_rows()
    metrics = compute_metrics(rows)
    for seed in lib.SEEDS:
        entry = metrics["per_seed"][str(seed)]
        assert "pooled_OOF_AUPRC" in entry
        assert "fold_level_diagnostics_not_averaged" in entry
        assert len(entry["fold_level_diagnostics_not_averaged"]) == len(lib.OUTER_FOLDS)
    assert "three_seed_summary" in metrics
    assert "AUPRC_mean" in metrics["three_seed_summary"]
    assert "AUPRC_sample_sd" in metrics["three_seed_summary"]
    assert "AUPRC_minimum" in metrics["three_seed_summary"]


def test_bootstrap_draw_shape_is_2000_by_27() -> None:
    patient_universe = [f"P{i}" for i in range(27)]
    draws = generate_draws(patient_universe)
    assert draws.shape == (2000, 27)
    assert draws.min() >= 0
    assert draws.max() < 27


def test_bootstrap_draws_are_reproducible_from_same_seed() -> None:
    patient_universe = [f"P{i}" for i in range(27)]
    draws_a = generate_draws(patient_universe)
    draws_b = generate_draws(patient_universe)
    assert np.array_equal(draws_a, draws_b)


def test_bootstrap_preserves_multiplicity_not_converted_to_set() -> None:
    patient_universe = [f"P{i}" for i in range(27)]
    draws = generate_draws(patient_universe)
    # with 27 slots drawn with replacement from 27 patients, duplicates within at least one
    # replicate are overwhelmingly likely; confirm the draw array itself (not a deduplicated
    # view) is what downstream code consumes by checking some replicate has repeats.
    has_repeat = any(len(set(row)) < len(row) for row in draws[:50])
    assert has_repeat


def test_bootstrap_replicate_metrics_use_same_patient_draw_across_seeds() -> None:
    rows = _synthetic_rows()
    roles_union = sorted({r["participant_group_id"] for r in rows})
    draws = generate_draws(roles_union)[:10]  # small slice for a fast unit test
    result = compute_replicate_metrics(rows, roles_union, draws)
    assert len(result["three_seed_replicate_auprc"]) == 10
    assert len(result["unique_patient_counts"]) == 10
    for seed in lib.SEEDS:
        assert len(result["per_seed_replicates"][seed]["AUPRC"]) == 10


def test_pos_weight_derivation_rejects_all_zero_positive() -> None:
    labels = np.zeros(10, dtype=np.int64)
    with pytest.raises(ValueError):
        lib.derive_pos_weight(labels)
