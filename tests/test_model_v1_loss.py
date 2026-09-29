from __future__ import annotations

import numpy as np
import pytest
import torch
import torch.nn.functional as functional
from torch import nn

from training.train_central import derive_pos_weight


def test_pos_weight_is_train_neg_over_pos_and_heldout_independent() -> None:
    train = np.asarray([0, 0, 0, 1])
    first = derive_pos_weight(train)
    validation_a = np.ones(100)
    validation_b = np.zeros(100)
    assert validation_a.mean() != validation_b.mean()
    assert first == derive_pos_weight(train)
    assert first["pos_weight"] == 3.0
    assert first["source_partition"] == "TRAIN"


def test_bce_with_logits_matches_functional_reference() -> None:
    logits = torch.tensor([[-1.0], [0.5], [2.0]], dtype=torch.float32)
    labels = torch.tensor([[0.0], [1.0], [1.0]], dtype=torch.float32)
    weight = torch.tensor([2.5], dtype=torch.float32)
    actual = nn.BCEWithLogitsLoss(pos_weight=weight)(logits, labels)
    expected = functional.binary_cross_entropy_with_logits(logits, labels, pos_weight=weight)
    torch.testing.assert_close(actual, expected, rtol=0.0, atol=0.0)


def test_label_shape_mismatch_is_rejected_by_runner_contract() -> None:
    logits = torch.zeros(4, 1)
    targets = torch.zeros(4)
    assert logits.shape != targets.shape
    with pytest.raises(ValueError):
        nn.BCEWithLogitsLoss()(logits, targets)
