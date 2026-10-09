# ruff: noqa: E501
"""Evaluation observer integrity (fast: small synthetic holdout, real model): digest verification, visible failures, no state mutation, restart behaviour,
fixed threshold / no calibration, and exact recomputation of every stored metric from the stored predictions."""

from __future__ import annotations

import copy
from types import SimpleNamespace

import numpy as np
import pytest

from federated.model_v2_fl import state_sha
from federated.wearable_fl_runner_v1 import new_session
from studio.holdout_cache import FrozenHoldout
from studio.observer import EvaluationObserver, read_predictions
from studio.records import EvaluationRecord


def small_holdout() -> FrozenHoldout:
    rng = np.random.default_rng(7)
    sets = []
    for k in range(3):
        n = 14
        labels = np.array([i % 3 == 0 for i in range(n)], dtype=np.float32)
        sets.append(SimpleNamespace(inputs=rng.standard_normal((n, 1, 2500)).astype(np.float32), labels=labels, participant_id=f"P{k}", client_id=f"H{k}"))
    labels = np.concatenate([d.labels for d in sets]).astype(int)
    owners = np.concatenate([[d.participant_id] * len(d.labels) for d in sets])
    inputs = np.concatenate([d.inputs for d in sets])
    return FrozenHoldout(tuple(sets), inputs, labels, owners, [], {}, {"uncertainty": {"replicates": 50, "seed": 1}}, "p" * 64, "m" * 64, "TEST_COHORT")


@pytest.fixture()
def observer(tmp_path):
    obs = EvaluationObserver(tmp_path, holdout_provider=small_holdout)
    yield obs
    obs.close()


def r0():
    state, _ = new_session()
    return state, state_sha(state)


def test_completed_record_is_strictly_typed_and_internally_consistent(observer):
    state, sha = r0()
    observer.declare_pair("R", 0, 0)
    observer.submit(run_id="R", run_length=3, round_id=0, state=state, expected_digest=sha)
    assert observer.wait_idle(120)
    rec = observer.get("R", 0)
    assert rec.evaluation_status == "COMPLETED" and rec.global_state_digest == sha and rec.threshold == 0.5 and rec.calibration == "NONE"
    assert rec.windows == 42 and rec.confusion_counts["TP"] + rec.confusion_counts["FN"] == rec.metric_result["positives"]
    assert rec.cohort_use.startswith("REUSED SYNTHETIC DIAGNOSTIC EVALUATION") and rec.claim_boundary.startswith("SYNTHETIC_ENGINEERING")
    EvaluationRecord.model_validate(rec.model_dump())            # round-trips through the strict model
    with pytest.raises(ValueError):                              # COMPLETED without metrics is impossible to construct
        EvaluationRecord(**{**rec.model_dump(), "metric_result": None})


def test_metrics_recompute_exactly_from_the_stored_predictions(observer):
    from final_showcase import metrics as base
    from fl10 import metrics

    state, sha = r0()
    observer.submit(run_id="R", run_length=3, round_id=0, state=state, expected_digest=sha)
    assert observer.wait_idle(120)
    rec = observer.get("R", 0)
    _owners, labels, logits = read_predictions((observer.run_dir("R") / rec.prediction_artifact_reference.path).read_bytes())
    again = metrics.full_metrics(labels, logits)
    for key in ("AUPRC", "AUROC", "F1", "BCE", "Brier", "TP", "FP", "TN", "FN", "precision", "recall", "specificity"):
        assert again[key] == rec.metric_result[key], key
    assert base.curves(labels, logits) is not None
    assert abs(rec.metric_result["BCE"] - float(np.mean(np.logaddexp(0, logits) - labels * logits))) < 1e-12
    assert abs(rec.metric_result["Brier"] - float(np.mean((1 / (1 + np.exp(-logits)) - labels) ** 2))) < 1e-12


def test_a_state_that_does_not_match_its_committed_digest_is_never_scored(observer):
    state, _sha = r0()
    rec = observer.submit(run_id="R", run_length=3, round_id=1, state=state, expected_digest="0" * 64)
    assert rec.evaluation_status == "FAILED" and rec.failure.code == "STATE_DIGEST_MISMATCH" and rec.metric_result is None
    assert observer.wait_idle(5) and observer.get("R", 1).metric_result is None


def test_submitting_does_not_mutate_the_callers_state_and_later_mutation_is_harmless(observer):
    state, sha = r0()
    snapshot = copy.deepcopy(state)
    observer.submit(run_id="R", run_length=3, round_id=0, state=state, expected_digest=sha)
    for key in state:                                             # caller keeps training and mutates its own arrays immediately after submit
        if np.issubdtype(state[key].dtype, np.floating):
            state[key] = state[key] + 1.0
    assert observer.wait_idle(120)
    assert observer.get("R", 0).evaluation_status == "COMPLETED"   # scored the private copy it verified
    assert all(np.array_equal(snapshot[k], v) for k, v in new_session()[0].items())


def test_evaluator_failure_is_visible_and_never_a_number(tmp_path):
    def boom(*args, **kwargs):
        raise RuntimeError("synthetic evaluator failure")

    obs = EvaluationObserver(tmp_path, holdout_provider=small_holdout, evaluator=boom)
    state, sha = r0()
    obs.submit(run_id="R", run_length=3, round_id=0, state=state, expected_digest=sha)
    assert obs.wait_idle(30)
    rec = obs.get("R", 0)
    assert rec.evaluation_status == "FAILED" and "synthetic evaluator failure" in rec.failure.message and rec.metric_result is None and rec.confusion_counts is None
    obs.close()


def test_duplicate_round_with_a_different_state_is_refused_and_same_state_is_idempotent(observer):
    state, sha = r0()
    first = observer.submit(run_id="R", run_length=3, round_id=0, state=state, expected_digest=sha)
    again = observer.submit(run_id="R", run_length=3, round_id=0, state=state, expected_digest=sha)
    assert again.global_state_digest == first.global_state_digest == sha and again.round_id == 0 and len(observer.records("R")) == 1
    with pytest.raises(ValueError):
        observer.submit(run_id="R", run_length=3, round_id=0, state=state, expected_digest="1" * 64)
    assert observer.wait_idle(120)


def test_runs_do_not_share_records(observer):
    state, sha = r0()
    observer.submit(run_id="A", run_length=3, round_id=0, state=state, expected_digest=sha)
    observer.submit(run_id="B", run_length=3, round_id=0, state=state, expected_digest=sha)
    assert observer.wait_idle(120)
    assert [r.run_id for r in observer.records("A")] == ["A"] and [r.run_id for r in observer.records("B")] == ["B"] and observer.records("C") == []


def test_restart_marks_unfinished_rounds_failed_instead_of_inventing_results(tmp_path):
    obs = EvaluationObserver(tmp_path, holdout_provider=small_holdout)
    _state, sha = r0()
    from studio.records import EvaluationRecord as R

    queued = R(run_id="X", run_length=3, round_id=2, global_state_digest=sha, cohort_id="C", evaluation_status="QUEUED", evaluation_queued_at="2026-01-01T00:00:00+00:00")
    obs._store(queued)
    obs.close()
    fresh = EvaluationObserver(tmp_path, holdout_provider=small_holdout)
    rec = fresh.get("X", 2)
    assert rec.evaluation_status == "FAILED" and rec.failure.code == "INTERRUPTED_BY_RESTART" and rec.metric_result is None
    fresh.close()
