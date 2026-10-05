"""CAPSTONE_RESTART_RECOVERY_V1 -- frozen startup recovery policy.

A process restart cannot resume an in-flight simulated source timeline (the transport is gone and
no raw stream was persisted), so at startup:

* devices are reconstructed from their rows and start DETACHED (history stays in
  device_connections);
* terminal sessions (COMPLETED/FAILED) are untouched;
* any persisted CREATED / DEVICE_READY / MONITORING / STOPPING session is set to FAILED with the
  explicit reason RESTART_RECOVERY_STALE_NONTERMINAL_SESSION (audit below + log), never resumed;
* nothing is regenerated, replayed or fabricated.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from capstone_persistence.store import CapstoneSqliteStore
from product.devices.scenarios import TimingMode, load_scenarios
from product.devices.simulated import SimulatedWearableSource
from product.edge.virtual import VirtualEdgeNode, monitoring_edge_identity
from product.monitoring.runtime_state import DeviceEntry, RuntimeState

LOGGER = logging.getLogger("nhm.product.recovery")
DEVICE_ID_PREFIX = "NHM_VIRTUAL_WEARABLE_"
POLICY = "FAIL_STALE_NONTERMINAL_SESSIONS_RECONSTRUCT_DEVICES_DETACHED"


@dataclass
class RecoveryReport:
    policy: str = POLICY
    recovered_sessions: list[dict[str, Any]] = field(default_factory=list)
    restored_devices: list[dict[str, Any]] = field(default_factory=list)


def restore_devices(store: CapstoneSqliteStore, state: RuntimeState,
                    *, timing_mode: TimingMode) -> list[dict[str, Any]]:
    scenarios = load_scenarios()
    restored = []
    highest = state.device_counter
    for row in store.list_device_rows():
        scenario_id = row["scenario_id"]
        if scenario_id not in scenarios:
            raise ValueError(f"PERSISTED_DEVICE_HAS_UNKNOWN_SCENARIO:{row['device_id']}")
        source = SimulatedWearableSource(
            scenarios[scenario_id], device_id=row["device_id"], display_name=row["display_name"],
            mode=timing_mode)
        node = VirtualEdgeNode(monitoring_edge_identity(row["device_id"]), source)
        history = store.list_device_connections(row["device_id"])
        entry = DeviceEntry(owner_user_id=row["user_id"], device_id=row["device_id"],
                            scenario_id=scenario_id, source=source, node=node)
        state.devices[row["device_id"]] = entry
        restored.append({"device_id": row["device_id"], "scenario_id": scenario_id,
                         "current_state": source.connection_state.value,
                         "historical_connection_rows": len(history),
                         "last_historical_state": history[-1]["device_state"] if history else None})
        if row["device_id"].startswith(DEVICE_ID_PREFIX):
            suffix = row["device_id"][len(DEVICE_ID_PREFIX):]
            if suffix.isdigit():
                highest = max(highest, int(suffix))
    state.device_counter = highest  # new devices never collide with persisted ids
    return restored


def recover(store: CapstoneSqliteStore, state: RuntimeState, *, timing_mode: TimingMode
            ) -> RecoveryReport:
    report = RecoveryReport()
    report.restored_devices = restore_devices(store, state, timing_mode=timing_mode)
    report.recovered_sessions = store.recover_stale_sessions(store.clock())
    for item in report.recovered_sessions:
        LOGGER.warning("restart recovery: session %s %s -> FAILED (%s)", item["session_id"],
                       item["previous_state"], item["reason"])
    return report
