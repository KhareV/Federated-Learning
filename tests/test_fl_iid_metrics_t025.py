from __future__ import annotations

import numpy as np
import pytest

from federated.evaluation import FL_METRIC_THRESHOLD, FL_METRIC_THRESHOLD_ID, evaluate_model
from federated.model_adapter import fresh_model_v1


def test_raw_sigmoid_half_threshold_and_partition_guard() -> None:
    assert FL_METRIC_THRESHOLD_ID == "FL_METRIC_THRESHOLD_V1"
    assert FL_METRIC_THRESHOLD == 0.5
    model = fresh_model_v1()
    inputs = np.zeros((4, 1, 2500), dtype=np.float32)
    labels = np.asarray([0, 1, 0, 1], dtype=np.int64)
    groups = np.asarray(["a", "a", "b", "b"])
    with pytest.raises(ValueError, match="forbidden"):
        evaluate_model(
            model,
            inputs,
            labels,
            groups,
            pos_weight=1.0,
            partition="INTERNAL_TEST",
        )

