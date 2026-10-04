"""WEARABLE_SIM_FL_COHORT_V1 SimulationTruth side: scheduled synthetic event timestamps.

Importable ONLY by the client-local engineering label adapter
(federated/wearable_sim_local_labels.py) and verification tests. Forbidden consumers: federated
server/router/aggregator, SecAgg server interface, API, gateway, fusion logic, dashboard and the
production stream runtime (static + behavioral tests enforce this)."""

from __future__ import annotations

from simulation.fl_cohort_v1 import ClientProfile

LABEL_CONTRACT_ID = "WEARABLE_SIM_EVENT_WINDOW_V1"


def scheduled_event_times_us(profile: ClientProfile) -> tuple[int, ...]:
    return tuple(round(event.time_s * 1_000_000) for event in profile.events)
