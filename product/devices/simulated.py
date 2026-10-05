"""SIMULATED_WEARABLE_SOURCE_V1 -- a concrete DeviceSource over the existing WEARABLE_SIM generator.

This is a DEVICE SOURCE: it emits canonical ``simulation.types.ObservedRecord`` records and typed
``DeviceEvent``s, never model output, labels or SimulationTruth. The lifecycle is exactly the frozen
DEVICE_SOURCE_CONTRACT_V1 state machine; illegal transitions raise ``IllegalTransitionError`` and
leave state unchanged (fail closed). It is a simulation, not WEARABLE_V1 hardware: no BLE, no
battery, no verified sample rate (360 Hz is the existing simulation convention).

Delivery model (deterministic, pull-based): ``start_stream`` starts one ordered timeline of
device-event transitions and records. ``records()`` and ``events()`` are two views of that single
timeline, so ordering is identical however the consumers interleave. A link outage delivers NO
records between DEVICE_DISCONNECTED and the reconnect; nothing is buffered, replayed or fabricated
(the source clock keeps running, so sample indices/timestamps skip the outage). ``LIVE_SPEED`` paces
delivery to the source timestamps; ``ACCELERATED`` does not. Pacing never alters values, indices,
timestamps or event order.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Sequence
from typing import Any

from product.devices.base import (
    AdapterType,
    DeviceCapabilities,
    DeviceDescriptor,
    DeviceEvent,
    DeviceEventMetadata,
    DeviceEventType,
    DeviceState,
    event_state_effect,
    validate_device_transition,
)
from product.devices.scenarios import ScenarioSpec, TimingMode
from simulation import SIMULATION_VERSION
from simulation.profile_v2013 import SOURCE_MODE, SOURCE_RATE_HZ, iter_observed_records
from simulation.types import ObservedRecord
from simulation.wearable import DATASET_ID

DEFAULT_DEVICE_ID = "NHM_VIRTUAL_WEARABLE_00"
STREAM_CLOCK_BASE_US = 1_000_000  # logical product clock: stream events = base + source timestamp
PRE_STREAM_TICK_US = 1_000  # logical product clock: pre-stream events = sequence * tick


class UnknownDeviceError(ValueError):
    """A command addressed a device id this source does not represent."""


_Item = tuple[str, Any, int]  # (kind, payload, source timestamp us)


class SimulatedWearableSource:
    def __init__(
        self,
        scenario: ScenarioSpec,
        *,
        device_id: str = DEFAULT_DEVICE_ID,
        display_name: str = "NHM Virtual Wearable",
        mode: TimingMode = TimingMode.ACCELERATED,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._scenario = scenario
        self._device_id = device_id
        self._display_name = display_name
        self._mode = TimingMode(mode)
        self._sleep, self._clock = sleep, clock
        self._state = DeviceState.DETACHED
        self._sequence = 0
        self._session_id: str | None = None
        self._events: deque[DeviceEvent] = deque()
        self._records: deque[ObservedRecord] = deque()
        self._timeline: Iterator[_Item] | None = None
        self._pace_origin: float | None = None
        self._lock = asyncio.Lock()

    # ---- identity ---------------------------------------------------------------------------
    @property
    def scenario(self) -> ScenarioSpec:
        return self._scenario

    @property
    def mode(self) -> TimingMode:
        return self._mode

    @property
    def connection_state(self) -> DeviceState:
        return self._state

    @property
    def descriptor(self) -> DeviceDescriptor:
        return DeviceDescriptor(
            device_id=self._device_id, display_name=self._display_name,
            adapter_type=AdapterType.SIMULATED, source_dataset_id=DATASET_ID,
            source_mode=SOURCE_MODE, connection_state=self._state,
            capabilities=DeviceCapabilities(
                supports_ecg=True,
                # the generator emits no PPG waveform (ppg_*_raw is always None); it emits
                # device-reported PPG-derived context (pulse rate, SpO2, ppg quality)
                supports_ppg=False, supports_spo2_context=True, supports_device_events=True,
                nominal_source_rates_hz={"ECG_SIMULATION_CONVENTION": SOURCE_RATE_HZ}),
            simulation=True, simulation_version=SIMULATION_VERSION,
            hardware_specific_fields_status="NOT_APPLICABLE")

    # ---- event machinery --------------------------------------------------------------------
    def _apply(self, event_type: DeviceEventType, *, reason: str | None = None,
               recoverable: bool = True, source_ts_us: int | None = None) -> None:
        new_state = event_state_effect(event_type)
        validate_device_transition(self._state, new_state)  # raises, state unchanged
        in_stream = self._timeline is not None or source_ts_us is not None
        product_ts = (STREAM_CLOCK_BASE_US + (source_ts_us or 0)) if in_stream else (
            self._sequence * PRE_STREAM_TICK_US)
        event = DeviceEvent(
            event_id=f"{self._device_id}-EV{self._sequence:06d}", device_id=self._device_id,
            session_id=self._session_id, sequence_index=self._sequence, event_type=event_type,
            device_state=new_state, source=AdapterType.SIMULATED, source_timestamp_us=source_ts_us,
            product_timestamp_us=product_ts, reason_code=reason, recoverable=recoverable,
            metadata=DeviceEventMetadata(scenario_id=self._scenario.scenario_id))
        self._state = new_state
        self._sequence += 1
        self._events.append(event)

    # ---- DeviceSource commands --------------------------------------------------------------
    async def scan(self, timeout_s: float) -> Sequence[DeviceDescriptor]:
        validate_device_transition(self._state, DeviceState.SCANNING)
        self._session_id = None
        self._apply(DeviceEventType.SCAN_STARTED)
        self._apply(DeviceEventType.DEVICE_DISCOVERED)
        return [self.descriptor]

    async def connect(self, device_id: str) -> None:
        if device_id != self._device_id:
            raise UnknownDeviceError(device_id)
        if self._state is DeviceState.STOPPED:
            self._apply(DeviceEventType.DEVICE_CONNECTED, reason="LINK_KEPT_AFTER_STOP")
            return
        self._apply(DeviceEventType.PAIRING_STARTED)
        self._apply(DeviceEventType.DEVICE_CONNECTED)

    async def disconnect(self) -> None:
        if self._state is DeviceState.STREAMING:
            self._end_stream()
            self._apply(DeviceEventType.DEVICE_DISCONNECTED, reason="USER_DISCONNECT")
        self._apply(DeviceEventType.DEVICE_DETACHED, reason="USER_DETACH")

    async def start_stream(self, session_id: str) -> None:
        validate_device_transition(self._state, DeviceState.STREAMING)
        self._session_id = session_id
        self._last_source_ts = 0
        self._timeline = self._build_timeline()
        self._pace_origin = None
        self._apply(DeviceEventType.STREAM_STARTED, source_ts_us=0)

    async def stop_stream(self) -> None:
        validate_device_transition(self._state, DeviceState.STOPPED)
        last = self._last_source_ts
        self._end_stream()
        self._apply(DeviceEventType.STREAM_STOPPED, reason="USER_STOP", source_ts_us=last)

    def simulate_error(self, reason_code: str, *, recoverable: bool = False) -> None:
        """Engineering hook: raise DEVICE_ERROR where the frozen lifecycle allows it."""
        validate_device_transition(self._state, DeviceState.ERROR)
        self._end_stream()
        self._apply(DeviceEventType.DEVICE_ERROR, reason=reason_code, recoverable=recoverable)

    # ---- timeline ---------------------------------------------------------------------------
    _last_source_ts = 0

    def _end_stream(self) -> None:
        self._timeline = None

    def _build_timeline(self) -> Iterator[_Item]:
        outages = list(self._scenario.outage_intervals())
        for record in iter_observed_records(self._scenario.profile()):
            while outages and record.sample_index >= outages[0][1]:
                start, end = outages.pop(0)
                down_ts = round(start * 1_000_000 / SOURCE_RATE_HZ)
                up_ts = round(end * 1_000_000 / SOURCE_RATE_HZ)
                yield ("transition", (DeviceEventType.DEVICE_DISCONNECTED, "LINK_LOST"), down_ts)
                yield ("transition", (DeviceEventType.RECONNECT_STARTED, "AUTO_RECONNECT"),
                       down_ts)
                yield ("transition", (DeviceEventType.DEVICE_RECONNECTED, "LINK_RESTORED"), up_ts)
                yield ("transition", (DeviceEventType.STREAM_STARTED, "STREAM_RESUMED"), up_ts)
            yield ("record", record, record.timestamp_us)
        yield ("end", None, self._scenario.duration_s * 1_000_000)

    async def _pace(self, ts_us: int) -> None:
        if self._mode is not TimingMode.LIVE_SPEED:
            return
        if self._pace_origin is None:
            self._pace_origin = self._clock()
        delay = self._pace_origin + ts_us / 1_000_000 - self._clock()
        if delay > 0:
            await self._sleep(delay)

    async def _advance(self) -> None:
        """Pull one item off the shared timeline (caller holds the lock)."""
        if self._timeline is None:
            return
        kind, payload, ts_us = next(self._timeline)
        await self._pace(ts_us)
        if self._timeline is None:  # stopped while pacing
            return
        self._last_source_ts = ts_us
        if kind == "record":
            self._records.append(payload)
        elif kind == "transition":
            event_type, reason = payload
            self._apply(event_type, reason=reason, source_ts_us=ts_us)
        else:  # natural end of the scenario
            self._timeline = None
            self._apply(DeviceEventType.STREAM_STOPPED, reason="SCENARIO_COMPLETE",
                        source_ts_us=ts_us)

    # ---- DeviceSource streams ---------------------------------------------------------------
    async def records(self) -> AsyncIterator[ObservedRecord]:
        while True:
            if self._records:
                yield self._records.popleft()
                continue
            if self._timeline is None:
                return
            async with self._lock:
                if not self._records and self._timeline is not None:
                    await self._advance()

    async def events(self) -> AsyncIterator[DeviceEvent]:
        """Drains buffered events; while a stream is active, keeps pulling the timeline."""
        while True:
            if self._events:
                yield self._events.popleft()
                continue
            if self._timeline is None:
                return
            async with self._lock:
                if not self._events and self._timeline is not None:
                    await self._advance()
