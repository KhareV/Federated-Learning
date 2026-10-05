"""CAPSTONE_EPHEMERAL_RUNTIME_STATE_V1 -- EPHEMERAL ENGINEERING STATE.

In-memory dictionaries only: devices, ownership, monitoring sessions, active tasks and event
journals. Nothing here touches a database or disk; it is REPLACED / BACKED BY CAP-004 PERSISTENCE
LATER.

``seed_engineering_session`` is a Python-only harness function. It is NOT an HTTP route, is not
reachable from a browser and is not product functionality: public session creation is CAP-004's.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from product.devices.base import DeviceEvent, DeviceState
from product.devices.simulated import SimulatedWearableSource
from product.edge.virtual import VirtualEdgeNode
from product.monitoring.event_adapter import ProductEventAdapter
from product.monitoring.event_journal import MonitoringEventJournal
from product.session import (
    MonitoringSession,
    SessionState,
    SimulationProvenance,
    advance_session,
    default_runtime_identity,
)
from simulation import SIMULATION_VERSION

PERSISTENCE_MODE = "EPHEMERAL_CAP003"


@dataclass
class DeviceEntry:
    owner_user_id: str
    device_id: str
    scenario_id: str
    source: SimulatedWearableSource
    node: VirtualEdgeNode
    event_log: list[DeviceEvent] = field(default_factory=list)
    active_session_id: str | None = None


@dataclass
class SessionEntry:
    owner_user_id: str
    session: MonitoringSession
    device_id: str
    journal: MonitoringEventJournal
    adapter: ProductEventAdapter
    coordinator: Any = None
    task: asyncio.Task[None] | None = None


@dataclass
class RuntimeState:
    devices: dict[str, DeviceEntry] = field(default_factory=dict)
    sessions: dict[str, SessionEntry] = field(default_factory=dict)
    device_counter: int = 0


def seed_engineering_session(state: RuntimeState, *, owner_user_id: str, device_id: str,
                             session_id: str, clock: Any = None) -> MonitoringSession:
    """Create the pre-existing DEVICE_READY session needed to exercise start/stop (harness only)."""
    device = state.devices.get(device_id)
    if device is None or device.owner_user_id != owner_user_id:
        raise ValueError("DEVICE_NOT_OWNED_BY_USER")
    if device.source.connection_state is not DeviceState.CONNECTED:
        raise ValueError("DEVICE_NOT_CONNECTED")
    if session_id in state.sessions:
        raise ValueError("SESSION_ALREADY_EXISTS")
    spec = device.source.scenario
    created = MonitoringSession(
        session_id=session_id, user_id=owner_user_id, device_id=device_id,
        device_adapter_type=device.source.descriptor.adapter_type,
        source_dataset_id=device.source.descriptor.source_dataset_id,
        source_mode=device.source.descriptor.source_mode, created_at_us=0,
        state=SessionState.CREATED, runtime=default_runtime_identity(),
        simulation_provenance=SimulationProvenance(
            scenario_id=spec.scenario_id, seed=spec.seed, simulation_version=SIMULATION_VERSION))
    ready = advance_session(created, SessionState.DEVICE_READY, 0)
    state.sessions[session_id] = SessionEntry(
        owner_user_id=owner_user_id, session=ready, device_id=device_id,
        journal=MonitoringEventJournal(), adapter=ProductEventAdapter(session_id, clock))
    return ready
