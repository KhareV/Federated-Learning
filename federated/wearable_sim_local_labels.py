"""CLIENT-LOCAL engineering label adapter for WEARABLE_SIM_EVENT_WINDOW_V1 (the ONLY module in
the federated package allowed to import SimulationTruth-side code).

Label contract (engineering only; NOT AAMI_SVF_WINDOW_V1, no S/V/F annotation equivalence): for a
trainable 10 s window ending at t, positive = at least one scheduled SYNTHETIC / ENGINEERING EVENT
timestamp lies in [t - 10 s, t]; negative otherwise."""

from __future__ import annotations

import numpy as np

from simulation.fl_cohort_truth_v1 import LABEL_CONTRACT_ID, scheduled_event_times_us
from simulation.fl_cohort_v1 import ClientProfile, iter_observed_records

WINDOW_US = 10_000_000
LABEL_ID = LABEL_CONTRACT_ID


class SyntheticObservedSource:
    """ObservedRecordSource over the synthetic generator (observed side only)."""

    def __init__(self, profile: ClientProfile) -> None:
        self.profile = profile
        self.client_id, self.participant_id = profile.client_id, profile.participant_id
        self.session_id = profile.session_id

    def records(self):
        return iter_observed_records(self.profile)


class SyntheticEventLabelProvider:
    def __init__(self, profile: ClientProfile) -> None:
        self._events = np.asarray(scheduled_event_times_us(profile), dtype=np.int64)

    def labels_for_windows(self, right_edges_us: list[int]) -> np.ndarray:
        out = np.zeros(len(right_edges_us), dtype=np.float32)
        for i, end in enumerate(right_edges_us):
            out[i] = float(np.any((self._events >= end - WINDOW_US) & (self._events <= end)))
        return out
