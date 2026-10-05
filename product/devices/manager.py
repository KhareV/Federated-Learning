"""CAPSTONE_DEVICE_MANAGER_V1 -- in-memory product service over the CAP-002 SimulatedWearableSource.

Reuses the CAP-002 source and VirtualEdgeNode unchanged (no copied lifecycle logic, no second
simulator). Every device has an ``owner_user_id``; cross-user access is FORBIDDEN. The underlying
source's lifecycle remains authoritative: an illegal command surfaces as INVALID_STATE and leaves
the source untouched. Pre-stream DeviceEvents are drained into the device's own ephemeral log (the
monitoring coordinator is the sole consumer of STREAM-time records/events).
"""

from __future__ import annotations

from product.api.errors import ProductError, ProductErrorCode
from product.contracts import IllegalTransitionError
from product.devices.base import DeviceDescriptor
from product.devices.scenarios import MONITORING_SCENARIO_IDS, TimingMode, load_scenarios
from product.devices.simulated import SimulatedWearableSource, UnknownDeviceError
from product.edge.virtual import VirtualEdgeNode, monitoring_edge_identity
from product.monitoring.runtime_state import DeviceEntry, RuntimeState

DEFAULT_SCENARIO_ID = "NORMAL_MONITORING"


class DeviceManager:
    def __init__(self, state: RuntimeState, *, timing_mode: TimingMode = TimingMode.ACCELERATED
                 ) -> None:
        self._state = state
        self._mode = timing_mode
        self._scenarios = load_scenarios()

    def _owned(self, owner_user_id: str, device_id: str) -> DeviceEntry:
        entry = self._state.devices.get(device_id)
        if entry is None:
            raise ProductError(ProductErrorCode.NOT_FOUND, f"unknown device {device_id}")
        if entry.owner_user_id != owner_user_id:
            raise ProductError(ProductErrorCode.FORBIDDEN, "device belongs to another user")
        return entry

    def owned_entry(self, owner_user_id: str, device_id: str) -> DeviceEntry:
        return self._owned(owner_user_id, device_id)

    async def _drain_pre_stream_events(self, entry: DeviceEntry) -> None:
        # no stream is active, so events() only drains already-buffered events (never pumps)
        entry.event_log.extend([e async for e in entry.source.events()])

    def create_simulated(self, owner_user_id: str, display_name: str | None,
                         scenario_id: str | None) -> DeviceDescriptor:
        scenario_id = scenario_id or DEFAULT_SCENARIO_ID
        if scenario_id not in MONITORING_SCENARIO_IDS:
            raise ProductError(ProductErrorCode.INVALID_REQUEST,
                               f"scenario {scenario_id!r} is not an implemented scenario")
        self._state.device_counter += 1
        device_id = f"NHM_VIRTUAL_WEARABLE_{self._state.device_counter:02d}"
        source = SimulatedWearableSource(
            self._scenarios[scenario_id], device_id=device_id,
            display_name=display_name or "NHM Virtual Wearable", mode=self._mode)
        node = VirtualEdgeNode(monitoring_edge_identity(device_id), source)
        self._state.devices[device_id] = DeviceEntry(
            owner_user_id=owner_user_id, device_id=device_id, scenario_id=scenario_id,
            source=source, node=node)
        return source.descriptor

    def list_devices(self, owner_user_id: str) -> list[DeviceDescriptor]:
        return [e.source.descriptor for e in self._state.devices.values()
                if e.owner_user_id == owner_user_id]

    async def scan(self, owner_user_id: str, device_id: str) -> DeviceDescriptor:
        entry = self._owned(owner_user_id, device_id)
        try:
            await entry.source.scan(0.0)
        except IllegalTransitionError as error:
            raise ProductError(ProductErrorCode.INVALID_STATE, str(error)) from error
        await self._drain_pre_stream_events(entry)
        return entry.source.descriptor

    async def connect(self, owner_user_id: str, device_id: str) -> DeviceDescriptor:
        entry = self._owned(owner_user_id, device_id)
        try:
            await entry.source.connect(device_id)
        except IllegalTransitionError as error:
            raise ProductError(ProductErrorCode.INVALID_STATE, str(error)) from error
        except UnknownDeviceError as error:  # pragma: no cover - ids are checked by _owned
            raise ProductError(ProductErrorCode.NOT_FOUND, str(error)) from error
        await self._drain_pre_stream_events(entry)
        return entry.source.descriptor

    async def disconnect(self, owner_user_id: str, device_id: str) -> DeviceDescriptor:
        entry = self._owned(owner_user_id, device_id)
        if entry.active_session_id is not None:
            raise ProductError(ProductErrorCode.INVALID_STATE,
                               "device is bound to an active monitoring session")
        try:
            await entry.source.disconnect()
        except IllegalTransitionError as error:
            raise ProductError(ProductErrorCode.INVALID_STATE, str(error)) from error
        await self._drain_pre_stream_events(entry)
        return entry.source.descriptor
