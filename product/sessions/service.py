"""CAPSTONE_SESSION_SERVICE_V1 -- persistent public session lifecycle around the UNCHANGED CAP-003
monitoring services.

Creation, listing and lookup are database-backed; start/stop delegate to the frozen
``MonitoringService`` (and therefore to the frozen coordinator, multiplexer and inference client).
This service never copies their logic. Device creation/commands wrap the frozen
``DeviceManager`` and
additionally persist device rows and connection history. Responses for sessions are always read from
the database so lifecycle timestamps (UTC microseconds) are never mixed with source-relative time.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from product.api.errors import ProductError, ProductErrorCode
from product.auth.base import AuthIdentity
from product.devices.base import DeviceDescriptor, DeviceState
from product.devices.manager import DeviceManager
from product.devices.simulated import SimulatedWearableSource
from product.monitoring.coordinator import MonitoringService
from product.monitoring.event_adapter import ProductEventAdapter
from product.monitoring.runtime_state import RuntimeState, SessionEntry
from product.persistence.bridge import PersistenceBridge, PersistingJournal, SessionMeta
from product.persistence.store import CapstoneSqliteStore
from product.session import (
    MonitoringSession,
    SessionState,
    SimulationProvenance,
    advance_session,
    default_runtime_identity,
)
from simulation import SIMULATION_VERSION

IdGenerator = Callable[[], str]


def default_session_id() -> str:
    return f"SESS-{uuid.uuid4().hex}"


class PersistentDeviceService:
    """Frozen DeviceManager + persistence of device rows and connection history."""

    def __init__(self, store: CapstoneSqliteStore, state: RuntimeState, manager: DeviceManager
                 ) -> None:
        self._store, self._state, self._manager = store, state, manager
        self._persisted_events: dict[str, int] = {}

    def _persist_new_events(self, device_id: str) -> None:
        entry = self._state.devices[device_id]
        done = self._persisted_events.get(device_id, 0)
        for event in entry.event_log[done:]:
            self._store.append_device_connection(
                device_id=device_id, session_id=None, event_type=event.event_type.value,
                device_state=event.device_state.value, sequence_index=event.sequence_index,
                reason_code=event.reason_code, recoverable=event.recoverable)
        self._persisted_events[device_id] = len(entry.event_log)

    def create_simulated(self, owner: AuthIdentity, display_name: str | None,
                         scenario_id: str | None) -> DeviceDescriptor:
        descriptor = self._manager.create_simulated(owner.user_id, display_name, scenario_id)
        entry = self._state.devices[descriptor.device_id]
        self._store.insert_device(
            device_id=descriptor.device_id, user_id=owner.user_id,
            display_name=descriptor.display_name, adapter_type=descriptor.adapter_type.value,
            source_dataset_id=descriptor.source_dataset_id, source_mode=descriptor.source_mode,
            simulation_version=descriptor.simulation_version, scenario_id=entry.scenario_id,
            capabilities=descriptor.capabilities.model_dump(mode="json"))
        return descriptor

    def list_devices(self, owner: AuthIdentity) -> list[DeviceDescriptor]:
        return self._manager.list_devices(owner.user_id)

    async def scan(self, owner: AuthIdentity, device_id: str) -> DeviceDescriptor:
        descriptor = await self._manager.scan(owner.user_id, device_id)
        self._persist_new_events(device_id)
        return descriptor

    async def connect(self, owner: AuthIdentity, device_id: str) -> DeviceDescriptor:
        descriptor = await self._manager.connect(owner.user_id, device_id)
        self._persist_new_events(device_id)
        return descriptor

    async def disconnect(self, owner: AuthIdentity, device_id: str) -> DeviceDescriptor:
        descriptor = await self._manager.disconnect(owner.user_id, device_id)
        self._persist_new_events(device_id)
        return descriptor


class SessionService:
    def __init__(self, store: CapstoneSqliteStore, state: RuntimeState, bridge: PersistenceBridge,
                 monitoring: MonitoringService, *, id_generator: IdGenerator = default_session_id
                 ) -> None:
        self._store, self._state, self._bridge = store, state, bridge
        self._monitoring, self._ids = monitoring, id_generator

    def _row(self, owner: AuthIdentity, session_id: str) -> MonitoringSession:
        session = self._store.get_session(session_id)
        if session is None:
            raise ProductError(ProductErrorCode.NOT_FOUND, f"unknown session {session_id}")
        if session.user_id != owner.user_id:
            raise ProductError(ProductErrorCode.FORBIDDEN, "session belongs to another user")
        return session

    def create(self, owner: AuthIdentity, device_id: str, scenario_id: str) -> MonitoringSession:
        device = self._state.devices.get(device_id)
        if device is None:
            raise ProductError(ProductErrorCode.NOT_FOUND, f"unknown device {device_id}")
        if device.owner_user_id != owner.user_id:
            raise ProductError(ProductErrorCode.FORBIDDEN, "device belongs to another user")
        if device.source.connection_state is not DeviceState.CONNECTED:
            raise ProductError(ProductErrorCode.INVALID_STATE,
                               f"device is {device.source.connection_state.value}, not CONNECTED")
        if scenario_id != device.scenario_id:
            raise ProductError(ProductErrorCode.INVALID_REQUEST,
                               "scenario_id does not match the device's scenario")
        source: SimulatedWearableSource = device.source
        session_id = self._ids()
        descriptor = source.descriptor
        created = MonitoringSession(
            session_id=session_id, user_id=owner.user_id, device_id=device_id,
            device_adapter_type=descriptor.adapter_type,
            source_dataset_id=descriptor.source_dataset_id, source_mode=descriptor.source_mode,
            created_at_us=self._store.clock(), state=SessionState.CREATED,
            runtime=default_runtime_identity(),
            simulation_provenance=SimulationProvenance(
                scenario_id=device.scenario_id, seed=source.scenario.seed,
                simulation_version=SIMULATION_VERSION))
        ready = advance_session(created, SessionState.DEVICE_READY, created.created_at_us)
        self._store.insert_session(ready)
        self._bridge.register(SessionMeta(
            session_id=session_id, device_id=device_id,
            total_source_samples=source.scenario.duration_s * 360))
        self._state.sessions[session_id] = SessionEntry(
            owner_user_id=owner.user_id, session=ready, device_id=device_id,
            journal=PersistingJournal(self._bridge, session_id),
            adapter=ProductEventAdapter(session_id))
        return ready

    def list(self, owner: AuthIdentity) -> list[MonitoringSession]:
        return self._store.list_sessions(owner.user_id)

    def get(self, owner: AuthIdentity, session_id: str) -> MonitoringSession:
        return self._row(owner, session_id)

    async def start(self, owner: AuthIdentity, session_id: str) -> MonitoringSession:
        self._row(owner, session_id)
        if session_id not in self._state.sessions:
            raise ProductError(ProductErrorCode.INVALID_STATE,
                               "session is not startable in this process")
        await self._monitoring.start(owner.user_id, session_id)  # frozen CAP-003 service
        self._store.update_session_state(session_id, SessionState.MONITORING,
                                         started_at_us=self._store.clock())
        return self._row(owner, session_id)

    async def stop(self, owner: AuthIdentity, session_id: str) -> MonitoringSession:
        self._row(owner, session_id)
        await self._monitoring.stop(owner.user_id, session_id)  # frozen CAP-003 service
        return self._row(owner, session_id)

    def journal_for(self, session_id: str) -> Any:
        entry = self._state.sessions.get(session_id)
        return entry.journal if entry is not None else None
