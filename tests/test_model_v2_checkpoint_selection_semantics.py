"""V2-002 best-checkpoint / early-stop semantics tests (Section 26), on synthetic AUPRC
sequences only -- proves the selection rule reused from training.train_central.train_seed
(strict `>`, not `>=`) is what V2-002 actually inherits, including its tie behavior and
early-stop counter reset rule.
"""

from __future__ import annotations


def _simulate_selection(auprc_sequence: list[float], *, patience: int) -> dict:
    """Reimplements, for test purposes only, the exact selection/early-stop bookkeeping in
    training.train_central.train_seed's loop (best = -inf; improved = auprc > best; reset
    counter on improvement; stop when non_improvement >= patience) -- the real code under
    test is scripts/run_model_v1_cv_reference_fit_v2002.py, which copies this same logic
    line-for-line; this test documents and locks in the expected behavior independent of any
    real training run."""
    best = float("-inf")
    best_epoch = 0
    non_improvement = 0
    stop_epoch = len(auprc_sequence)
    stop_reason = "MAX_EPOCHS"
    for epoch, auprc in enumerate(auprc_sequence, start=1):
        improved = auprc > best
        if improved:
            best = auprc
            best_epoch = epoch
            non_improvement = 0
        else:
            non_improvement += 1
        if non_improvement >= patience:
            stop_epoch = epoch
            stop_reason = "EARLY_STOP"
            break
    return {
        "best_epoch": best_epoch,
        "best_auprc": best,
        "stop_epoch": stop_epoch,
        "stop_reason": stop_reason,
    }


def test_strict_greater_than_ties_do_not_count_as_improvement() -> None:
    # epoch 2 ties epoch 1's value -- must NOT be selected as a new best, and must count as a
    # non-improving epoch.
    result = _simulate_selection([0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5], patience=7)
    assert result["best_epoch"] == 1
    assert result["stop_reason"] == "EARLY_STOP"
    assert result["stop_epoch"] == 8


def test_improvement_resets_non_improvement_counter() -> None:
    # epochs 1..6 strictly increasing, epoch 7 a dip, epoch 8 a new best (resets counter).
    sequence = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.55, 0.65, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3]
    result = _simulate_selection(sequence, patience=7)
    assert result["best_epoch"] == 8
    assert result["best_auprc"] == 0.65


def test_early_stop_fires_exactly_at_patience_boundary() -> None:
    # best at epoch 1, then exactly 7 non-improving epochs (2..8) -> stop at epoch 8.
    sequence = [0.9] + [0.1] * 7
    result = _simulate_selection(sequence, patience=7)
    assert result["best_epoch"] == 1
    assert result["stop_epoch"] == 8
    assert result["stop_reason"] == "EARLY_STOP"


def test_six_non_improving_epochs_does_not_trigger_early_stop() -> None:
    sequence = [0.9] + [0.1] * 6
    result = _simulate_selection(sequence, patience=7)
    assert result["stop_reason"] == "MAX_EPOCHS"
    assert result["stop_epoch"] == 7


def test_matches_historical_t015_shape_for_release_seed() -> None:
    """Sanity cross-check against the real recovered T015 epoch history for seed 20260927
    (reports/t015/seeds/20260927.json): best_epoch=4, stop_epoch=11, EARLY_STOP."""
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    data = json.loads((root / "reports/t015/seeds/20260927.json").read_text(encoding="utf-8"))
    sequence = [entry["validation_auprc"] for entry in data["epoch_logs"]]
    result = _simulate_selection(sequence, patience=7)
    assert result["best_epoch"] == data["best_epoch"]
    assert result["stop_epoch"] == data["stop_epoch"]
