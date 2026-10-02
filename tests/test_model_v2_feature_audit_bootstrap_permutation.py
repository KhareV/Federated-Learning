"""V2-003 bootstrap-reuse and grouped-permutation tests: confirms the V2-002 bootstrap draws
are reused byte-identically (never a new RNG sequence), patient multiplicity is preserved in
the paired-bootstrap replicate expansion, and the grouped permutation shares one row
permutation across every column in a feature group (never independently shuffling columns).
"""

from __future__ import annotations

import json

import numpy as np

import scripts._v2_003_lib as lib
import scripts.grouped_permutation_v2003 as perm_mod
import scripts.paired_bootstrap_v2003 as bootstrap_mod

OUT_DIR = lib.ROOT / "reports/model_v2/v2_003"
V2_002_DIR = lib.ROOT / "reports/model_v2/v2_002"


def test_bootstrap_draws_file_is_v2_002s_not_regenerated() -> None:
    draws, patient_universe = bootstrap_mod.load_bootstrap_draws()
    v2002_draws = np.load(V2_002_DIR / "bootstrap_draws.npy")
    assert np.array_equal(draws, v2002_draws)
    assert len(patient_universe) == 27


def test_replicate_metrics_preserve_multiplicity() -> None:
    patient_universe = ["A", "B", "C"]
    rows = [
        {"participant_group_id": "A", "label": "1", "probability": "0.9"},
        {"participant_group_id": "A", "label": "0", "probability": "0.1"},
        {"participant_group_id": "B", "label": "1", "probability": "0.8"},
        {"participant_group_id": "C", "label": "0", "probability": "0.2"},
    ]
    # One replicate draws patient A twice and C once (never deduplicated).
    draws = np.asarray([[0, 0, 2]])
    replicates = bootstrap_mod.replicate_metrics_for_combo(rows, patient_universe, draws)
    assert replicates["AUPRC"][0] is not None  # both classes present (A has both labels)


def test_shared_row_permutation_within_group() -> None:
    rng_a = perm_mod._repetition_rng(outer_fold=0, group="STAT", repetition_index=0)
    rng_b = perm_mod._repetition_rng(outer_fold=0, group="STAT", repetition_index=0)
    permutation_a = rng_a.permutation(10)
    permutation_b = rng_b.permutation(10)
    assert np.array_equal(permutation_a, permutation_b)  # deterministic, reproducible

    features = np.arange(30).reshape(10, 3).astype(np.float64)
    group_indices = [0, 1]
    rng = perm_mod._repetition_rng(outer_fold=0, group="STAT", repetition_index=0)
    permutation = rng.permutation(features.shape[0])
    permuted = features.copy()
    permuted[:, group_indices] = features[permutation][:, group_indices]
    # Columns 0 and 1 must move together (same row order); column 2 untouched.
    for row in range(10):
        original_row_index = np.where(permutation == row)[0]
        assert permuted[original_row_index[0], 0] == features[row, 0]
        assert permuted[original_row_index[0], 1] == features[row, 1]
    assert np.array_equal(permuted[:, 2], features[:, 2])


def test_different_repetition_indices_give_different_permutations() -> None:
    rng0 = perm_mod._repetition_rng(outer_fold=0, group="RR", repetition_index=0)
    rng1 = perm_mod._repetition_rng(outer_fold=0, group="RR", repetition_index=1)
    assert not np.array_equal(rng0.permutation(50), rng1.permutation(50))


def test_different_folds_give_different_permutations() -> None:
    rng_f0 = perm_mod._repetition_rng(outer_fold=0, group="QRS", repetition_index=0)
    rng_f1 = perm_mod._repetition_rng(outer_fold=1, group="QRS", repetition_index=0)
    assert not np.array_equal(rng_f0.permutation(50), rng_f1.permutation(50))


def test_real_grouped_permutation_diagnostic_only_and_seeded() -> None:
    summary = json.loads((OUT_DIR / "grouped_permutation_summary.json").read_text())
    assert summary["diagnostic_only"] is True
    assert summary["base_seed"] == 20261003
    assert summary["repetitions_per_group_per_fold"] == 50
    assert summary["shared_row_permutation_within_group"] is True


def test_real_bootstrap_summary_reuses_v2_002_identity() -> None:
    summary = json.loads((OUT_DIR / "paired_variant_bootstrap_summary.json").read_text())
    assert summary["bootstrap_id"] == "MODEL_V2_BOOTSTRAP_DRAWS_V1"
    assert summary["reused_from"] == "V2-002"
    assert summary["bootstrap_seed"] == 20261002
    assert summary["replicates"] == 2000
