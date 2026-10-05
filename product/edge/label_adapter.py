# ruff: noqa: E501
"""SIMULATION_LABEL_ADAPTER_V1 -- thin product wrapper over the existing client-local label adapter.

The ONLY simulation label contract is WEARABLE_SIM_EVENT_WINDOW_V1: positive = at least one scheduled
SYNTHETIC / ENGINEERING EVENT lies inside the 10 s window (frozen federated adapter). It is NOT
AAMI_SVF_WINDOW_V1 and carries no S/V/F, arrhythmia or clinical meaning.

This module deliberately imports NO truth-side module: the single sanctioned truth consumer stays
federated/wearable_sim_local_labels.py. Labels never come from model predictions, monitoring state or
thresholds; the label source is always SIMULATION_TRUTH_ENGINEERING.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np

from federated.wearable_sim_local_labels import LABEL_ID, SyntheticEventLabelProvider
from product.edge.buffer import LabelSource

ADAPTER_ID = "SIMULATION_LABEL_ADAPTER_V1"
LABEL_CONTRACT = LABEL_ID  # WEARABLE_SIM_EVENT_WINDOW_V1
LABEL_SOURCE = LabelSource.SIMULATION_TRUTH_ENGINEERING


class SimulationLabelAdapterV1:
    """Satisfies both product SimulationLabelAdapter and federated LocalTrainingLabelProvider."""

    adapter_id = ADAPTER_ID
    label_contract = LABEL_CONTRACT
    label_source = LABEL_SOURCE

    def __init__(self, profile: Any) -> None:
        self._inner = SyntheticEventLabelProvider(profile)

    def labels_for_windows(self, right_edges_us: Sequence[int]) -> np.ndarray:
        labels = self._inner.labels_for_windows(list(right_edges_us))
        if labels.shape != (len(right_edges_us),) or not np.isin(labels, (0.0, 1.0)).all():
            raise ValueError("LABELS_NOT_BINARY_OR_MISALIGNED")
        return labels
