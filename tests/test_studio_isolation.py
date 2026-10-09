# ruff: noqa: E501
"""Evaluation must never change training. The frozen trainer draws Dropout masks from torch's process-wide RNG; a model CONSTRUCTED on another thread (as
``final_showcase.evaluate.logits_for`` does) consumes that RNG and perturbs the update. ``studio.isolated_eval`` scores without any random draw."""

from __future__ import annotations

import threading
from functools import cache

import numpy as np
import pytest

from federated.model_v2_fl import state_sha, train_local_epoch_v2
from federated.wearable_fl_runner_v1 import (
    BASE_SEED,
    BATCH_SIZE,
    LEARNING_RATE,
    POS_WEIGHT,
    WEIGHT_DECAY,
    new_session,
)
from federated.wearable_fl_system_v1 import EXPERIMENT_ID
from final_showcase.evaluate import logits_for
from studio.isolated_eval import isolated_logits, prepare_template


@cache
def fixture():
    from federated.wearable_fl_runner_v1 import build_cohort

    _, datasets, _ = build_cohort()
    state, _ = new_session()
    return datasets[0], state


def train_digest() -> str:
    d, state = fixture()
    result = train_local_epoch_v2(global_state=state, inputs=d.inputs, labels=d.labels, site_id=d.client_id, round_number=1, experiment_id=EXPERIMENT_ID, base_seed=BASE_SEED,
                                  batch_size=BATCH_SIZE, learning_rate=LEARNING_RATE, weight_decay=WEIGHT_DECAY, pos_weight=POS_WEIGHT)
    return result.update.delta and state_sha({k: v for k, v in result.update.delta.items()})


def train_with_concurrent(scorer) -> str:
    d, state = fixture()
    stop, errors = threading.Event(), []
    inputs = d.inputs[:64]

    def hammer() -> None:
        try:
            while not stop.is_set():
                scorer(state, inputs)
        except Exception as error:  # pragma: no cover
            errors.append(error)

    thread = threading.Thread(target=hammer)
    thread.start()
    try:
        return train_digest()
    finally:
        stop.set()
        thread.join()
        assert not errors


def test_isolated_scoring_never_changes_training():
    prepare_template()
    baseline = train_digest()
    assert train_digest() == baseline                      # training itself is deterministic
    for _ in range(3):
        assert train_with_concurrent(isolated_logits) == baseline


def test_control_the_unisolated_evaluator_does_perturb_training():
    baseline = train_digest()
    differed = any(train_with_concurrent(logits_for) != baseline for _ in range(4))
    if not differed:
        pytest.skip("hazard did not manifest in this run (interleaving is timing dependent); the isolated path is asserted above")
    assert differed


def test_isolated_logits_equal_the_reference_evaluator_bit_for_bit():
    d, state = fixture()
    assert np.array_equal(isolated_logits(state, d.inputs), logits_for(state, d.inputs))
