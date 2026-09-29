from __future__ import annotations

from training.train_central import RELEASE_SEED, release_candidate_seed


def test_release_seed_cannot_be_replaced_by_higher_scoring_replicate() -> None:
    results = [
        {"seed": 20260927, "best_validation_auprc": 0.60},
        {"seed": 20260928, "best_validation_auprc": 0.99},
        {"seed": 20260929, "best_validation_auprc": 0.98},
    ]
    assert RELEASE_SEED == 20260927
    assert release_candidate_seed(results) == 20260927
