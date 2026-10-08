# ruff: noqa: E501
"""NHM-FINAL-SHOWCASE-001 workstream B: protocol, separation and metric negative tests (no model training)."""

from __future__ import annotations

import json
from dataclasses import replace
from functools import cache

import numpy as np
import pytest

from federated.wearable_fl_runner_v1 import build_cohort
from final_showcase import evaluate as ev
from final_showcase import metrics
from final_showcase.holdout import build_holdout_dataset, holdout_profiles


@cache
def _holdout():
    return [build_holdout_dataset(p) for p in holdout_profiles()]


@cache
def _training():
    return build_cohort()[1]


def test_protocol_and_manifest_hash_bound():
    protocol = json.loads(ev.PROTOCOL.read_text())
    assert protocol["holdout"]["manifest_sha256"] == ev.sha256_file(ev.MANIFEST)
    assert protocol["decision_threshold"] == {"rule": "positive iff raw sigmoid(logit) >= 0.5", "predeclared": True, "tuned": False, "calibrated": False}
    assert "CAL_V2" in protocol["forbidden"]


def test_holdout_matches_manifest_and_is_disjoint():
    protocol = json.loads(ev.PROTOCOL.read_text())
    sep = ev.check_manifest(protocol, _holdout(), _training())
    assert sep["participant_overlap"] == sep["session_overlap"] == sep["window_input_overlap"] == 0


def test_participant_overlap_rejected():
    held = [replace(_holdout()[0], participant_id=_training()[0].participant_id), *_holdout()[1:]]
    with pytest.raises(ev.EvaluationError, match="PARTICIPANT_OVERLAP"):
        ev.separation(held, _training())


def test_session_and_window_overlap_rejected():
    with pytest.raises(ev.EvaluationError, match="SESSION_OVERLAP"):
        ev.separation([replace(_holdout()[0], session_id=_training()[0].session_id)], _training())
    with pytest.raises(ev.EvaluationError, match="WINDOW_INPUT_OVERLAP"):
        ev.separation([replace(_holdout()[0], inputs=_training()[0].inputs)], _training())


def test_altered_labels_detected_by_manifest():
    protocol = json.loads(ev.PROTOCOL.read_text())
    flipped = replace(_holdout()[0], labels=1 - _holdout()[0].labels)
    with pytest.raises(ev.EvaluationError, match="HOLDOUT_DATASET_DIFFERS_FROM_MANIFEST"):
        ev.check_manifest(protocol, [flipped, *_holdout()[1:]], _training())


def test_missing_class_rejected():
    only_neg = [replace(d, labels=np.zeros_like(d.labels)) for d in _holdout()]
    with pytest.raises(ev.EvaluationError, match="MISSING_CLASS_IN_HOLDOUT"):
        ev.require_both_classes(only_neg)


def test_changed_candidate_hash_rejected():
    with pytest.raises(ev.EvaluationError, match="STATE_DIGEST_MISMATCH"):
        ev.digest_check("round_3_candidate", {"a": np.zeros(2, dtype=np.float32)}, "3f0b7762" + "0" * 56)


def test_changed_protocol_after_freeze_rejected(tmp_path, monkeypatch):
    monkeypatch.chdir(ev.PROTOCOL.parent.parent.parent)
    with pytest.raises(Exception):  # noqa: B017 — unknown commit => git failure, never a silent pass
        ev.verify_method_freeze("0" * 40)


def test_undefined_metrics_are_none_with_reason():
    y = np.zeros(10, dtype=int)
    m = metrics.classification_metrics(y, np.full(10, -3.0))
    assert m["AUPRC"] is None and m["AUROC"] is None and m["recall"] is None and m["F1"] is None and "AUPRC" in m["undefined"]
    allpos = metrics.classification_metrics(np.ones(4, dtype=int), np.full(4, 3.0))
    assert allpos["specificity"] is None and allpos["recall"] == 1.0


def test_metrics_match_reference_implementation():
    from evaluation.metrics import pooled_binary_metrics  # frozen reference

    rng = np.random.default_rng(3)
    y = (rng.random(300) < 0.3).astype(int)
    z = rng.normal(size=300) + 1.2 * y
    ours = metrics.classification_metrics(y, z)
    p = 1.0 / (1.0 + np.exp(-z))
    ref = pooled_binary_metrics(y, p, (p >= 0.5).astype(int), np.array(["P"] * 300))
    assert abs(ours["AUPRC"] - ref["AUPRC"]) < 1e-12 and abs(ours["AUROC"] - ref["AUROC"]) < 1e-12 and abs(ours["F1"] - ref["pooled_F1"]) < 1e-12


def test_threshold_and_no_calibration_constants():
    assert metrics.THRESHOLD == 0.5
    m = metrics.classification_metrics(np.array([0, 1]), np.array([0.0, 0.0]))  # p == 0.5 is positive
    assert m["TP"] == 1 and m["FP"] == 1
