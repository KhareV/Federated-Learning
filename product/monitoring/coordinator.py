"""CAPSTONE_MONITORING_COORDINATOR_V1 -- the ONLY consumer/orchestrator of a live DeviceSource.

For one monitoring session it owns, and nothing else may touch: DeviceSource record + event
consumption (through the deterministic multiplexer), source/event interleaving, waveform chunking,
WearableStreamRuntime ingestion, inference calls, product event sequencing and session completion.

    ObservedRecord --+--> UI waveform chunker (360 Hz, ADC counts, None gaps)   [UI only]
                     +--> unchanged WearableStreamRuntime (scientific 250 Hz) --> window
                          --> CapstoneInferenceClient --> HTTP --> released SOFTWARE_SYSTEM_V2

The same ObservedRecord objects feed both branches; UI ``None`` placeholders never enter the
scientific branch. No stage invokes a model directly. A 422 for an unusable window is an expected
contract outcome: it yields a quality.status and NO inference.result / monitoring.state.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable
from typing import Any

from product.api.errors import ProductError, ProductErrorCode
from product.contracts import IllegalTransitionError
from product.devices.base import DeviceEvent, DeviceEventType
from product.devices.replay import canonical_json
from product.inference.client import CapstoneInferenceClient, InferenceOutcome, OutcomeKind
from product.monitoring.mux import MuxItem, merge_source_streams
from product.monitoring.runtime_state import DeviceEntry, RuntimeState, SessionEntry
from product.monitoring.waveform import WaveformChunk, WaveformChunker, index_for_timestamp
from product.session import MonitoringSession, SessionState, advance_session
from simulation.stream_runtime_v2013 import CHUNK_RECORDS, WearableStreamRuntime
from simulation.types import ObservedRecord

REPLAY_ID = "CAPSTONE_MONITORING_COORDINATOR_V1"
BOUND_MODEL_LABEL = "MODEL_V2_FINAL"


class InferenceFailure(RuntimeError):
    """The released inference system failed or was integrated incorrectly (non-normal)."""

    def __init__(self, outcome: InferenceOutcome) -> None:
        super().__init__(f"{outcome.kind.value}:{outcome.status_code}:{outcome.detail}")
        self.outcome = outcome


class MonitoringCoordinator:
    def __init__(self, *, entry: SessionEntry, device: DeviceEntry,
                 inference: CapstoneInferenceClient, blocking_lookahead: bool = True) -> None:
        self._blocking_lookahead = blocking_lookahead
        self._entry, self._device, self._inference = entry, device, inference
        self._session_id = entry.session.session_id
        self._node = device.node
        self._adapter, self._journal = entry.adapter, entry.journal
        self._runtime = WearableStreamRuntime(session_id=self._session_id,
                                              model_id=BOUND_MODEL_LABEL, replay_id=REPLAY_ID)
        self._chunker = WaveformChunker()
        self._batch: list[ObservedRecord] = []
        self._stop_requested = False
        self._user_stop = False
        self._last_state: str | None = None
        self._source_ts_us = 0
        self._last_record_ts = -1
        self._started_ts_us = 0
        self._failed = False
        self.on_chunk: Callable[[WaveformChunk], None] | None = None
        self.scientific_records_seen: list[int] = []  # sample indices fed to the runtime
        self.telemetry: dict[str, Any] = {
            "windows": [], "device_states": [], "session_states": [], "monitoring_states": [],
            "context_availability": [], "http_statuses": [], "waveform_chunks": 0,
            "waveform_null_chunks": 0, "waveform_null_intervals": [], "waveform_first_indices": [],
            "scientific_record_count": 0, "expected_unusable_windows": 0,
            "discarded_future_events": 0, "context_values_withheld": 0}
        self._records_digest = hashlib.sha256()
        self._samples_digest = hashlib.sha256()
        self._open_null: list[int] | None = None

    # ---- public control -------------------------------------------------------------------
    @property
    def scientific_trace(self) -> dict[str, Any]:
        return {"record_count": self.telemetry["scientific_record_count"],
                "records_sha256": self._records_digest.hexdigest(),
                "window_count": len(self.telemetry["windows"]),
                "windows_samples_sha256": self._samples_digest.hexdigest()}

    async def stop(self) -> None:
        """Manual stop: halt the source, then let the coordinator wind down cleanly."""
        self._user_stop = True
        self._stop_requested = True
        try:
            await self._node.stop_live_monitoring()
        except IllegalTransitionError:
            # The source may be mid-outage or already finished (in ACCELERATED mode its timeline
            # can run ahead of the product), where STREAMING->STOPPED is not legal. The product
            # still stops consuming; the simulated device keeps its own link state and is released
            # by the owner via the device disconnect route. Nothing pulls the source afterwards.
            state = self._node.device_source.connection_state
            self.telemetry["stop_without_device_stop"] = state.value

    # ---- event helpers --------------------------------------------------------------------
    def _publish(self, event: Any) -> None:
        self._journal.append(event)

    def _transition(self, new_state: SessionState, reason: str | None = None) -> None:
        session: MonitoringSession = advance_session(self._entry.session, new_state,
                                                     self._source_ts_us)
        self._entry.session = session
        self.telemetry["session_states"].append(new_state.value)
        elapsed_ms = (self._source_ts_us - self._started_ts_us) // 1000
        self._publish(self._adapter.session_status(new_state, elapsed_ms, reason))

    def _emit_chunks(self, chunks: list[WaveformChunk]) -> None:
        for chunk in chunks:
            self._publish(self._adapter.waveform_chunk(chunk))
            self.telemetry["waveform_chunks"] += 1
            self.telemetry["waveform_first_indices"].append(chunk.first_sample_index)
            if chunk.null_count:
                self.telemetry["waveform_null_chunks"] += 1
            for offset, sample in enumerate(chunk.samples):
                index = chunk.first_sample_index + offset
                if sample is None:
                    if self._open_null is None:
                        self._open_null = [index, index]
                    else:
                        self._open_null[1] = index
                elif self._open_null is not None:
                    self.telemetry["waveform_null_intervals"].append(self._open_null)
                    self._open_null = None
            if self.on_chunk is not None:
                self.on_chunk(chunk)

    # ---- main loop ------------------------------------------------------------------------
    async def run(self) -> None:
        records = self._node.live_records()
        events = self._node.live_events()
        try:
            self._transition_initial()
            async for item in merge_source_streams(
                    records, events, should_stop=lambda: self._stop_requested,
                    blocking_lookahead=self._blocking_lookahead):
                if self._failed:
                    break
                await self._handle(item)
            if not self._failed:
                self._complete()
        except InferenceFailure as failure:
            self._fail("INFERENCE", "INFERENCE_SYSTEM_FAILURE"
                       if failure.outcome.kind is OutcomeKind.SYSTEM_FAILURE
                       else "INFERENCE_INTEGRATION_ERROR", str(failure))
        except asyncio.CancelledError:
            self._fail("PRODUCT_API", "MONITORING_CANCELLED", "monitoring task cancelled")
            raise
        except Exception as error:
            self._fail("PRODUCT_API", "INTERNAL_PRODUCT_ERROR", repr(error))
        finally:
            await asyncio.gather(records.aclose(), events.aclose(), return_exceptions=True)
            await self._inference.aclose()
            self._device.active_session_id = None
            self._journal.close()

    def _transition_initial(self) -> None:
        # the REST layer already moved DEVICE_READY -> MONITORING; announce it as event 0
        self.telemetry["session_states"].append(SessionState.MONITORING.value)
        self._publish(self._adapter.session_status(SessionState.MONITORING, 0, None))

    def _complete(self) -> None:
        if self._entry.session.state is SessionState.MONITORING:
            self._transition(SessionState.STOPPING, "USER_STOP" if self._user_stop
                             else "SCENARIO_COMPLETE")
            self._transition(SessionState.COMPLETED, None)

    def _fail(self, origin: str, code: str, message: str) -> None:
        if self._failed or self._entry.session.state in (SessionState.COMPLETED,
                                                         SessionState.FAILED):
            return
        self._failed = True
        try:
            self._publish(self._adapter.system_error(origin, code, message, recoverable=False))
            self._transition(SessionState.FAILED, code)
        except Exception:
            self._entry.session = self._entry.session.model_copy(
                update={"state": SessionState.FAILED})

    async def _handle(self, item: MuxItem) -> None:
        if item.kind == "record":
            await self._on_record(item.value)  # type: ignore[arg-type]
        else:
            await self._on_device_event(item.value)  # type: ignore[arg-type]

    # ---- records --------------------------------------------------------------------------
    async def _on_record(self, record: ObservedRecord) -> None:
        self._source_ts_us = self._last_record_ts = record.timestamp_us
        self._emit_chunks(self._chunker.add_record(record))  # UI branch (None gaps live here only)
        self._batch.append(record)  # scientific branch: the SAME unmodified record object
        if len(self._batch) >= CHUNK_RECORDS:
            await self._ingest()

    async def _ingest(self) -> None:
        batch, self._batch = self._batch, []
        for record in batch:
            self._records_digest.update(canonical_json(record.to_canonical_dict()) + b"\n")
            self.scientific_records_seen.append(record.sample_index)
        self.telemetry["scientific_record_count"] += len(batch)
        for window in self._runtime.ingest(batch):
            await self._on_window(window)

    async def _finish_scientific(self) -> None:
        if self._batch:
            await self._ingest()
        for window in self._runtime.finish():
            await self._on_window(window)

    # ---- windows / inference --------------------------------------------------------------
    async def _on_window(self, window: dict[str, Any]) -> None:
        samples = window["ecg"]["samples"]
        self._samples_digest.update(canonical_json(samples) + b"\n")
        row: dict[str, Any] = {
            "timestamp_us": window["timestamp_us"], "ecg_quality": window["ecg_quality"],
            "ecg_sample_count": len(samples), "ecg_target_hz": window["ecg"]["target_hz"],
            "window_seconds": window["ecg"]["window_seconds"],
            "context_present": window["ppg_context"] is not None,
            "quality_reasons": window["diagnostics"]["quality_reasons"],
            "missing_slots": window["diagnostics"]["missing_slots"]}
        self._publish(self._adapter.quality_status(window))  # quality = runtime/QUALITY_V1 only
        outcome = await self._inference.infer_window(window, self._session_id)
        self.telemetry["http_statuses"].append(outcome.status_code)
        if outcome.kind is OutcomeKind.EXPECTED_UNUSABLE_WINDOW:
            self.telemetry["expected_unusable_windows"] += 1
            row.update(http_status=422, outcome="EXPECTED_UNUSABLE_WINDOW")
        elif outcome.kind is OutcomeKind.OK and outcome.response is not None:
            response = outcome.response
            self._publish(self._adapter.context_snapshot(response))
            self._publish(self._adapter.inference_result(response))
            if response.monitoring_state.value != self._last_state:
                self._publish(self._adapter.monitoring_state(response, self._last_state))
                self._last_state = response.monitoring_state.value
                self.telemetry["monitoring_states"].append(self._last_state)
            if self._adapter.context_values_withheld(response):
                self.telemetry["context_values_withheld"] += 1
            context = self._adapter.context_payload(response)
            self.telemetry["context_availability"].append(context["context_available"])
            row.update(http_status=200, outcome="OK", model_id=response.model_id,
                       calibration_id=response.calibration_id,
                       monitoring_state=response.monitoring_state.value,
                       context_available=context["context_available"],
                       raw_probability=response.raw_probability,
                       calibrated_probability=response.source_domain_calibrated_probability)
        else:
            self.telemetry["windows"].append({**row, "http_status": outcome.status_code,
                                              "outcome": outcome.kind.value})
            raise InferenceFailure(outcome)
        self.telemetry["windows"].append(row)

    # ---- device events --------------------------------------------------------------------
    async def _on_device_event(self, event: DeviceEvent) -> None:
        ts = event.source_timestamp_us
        if (self._user_stop and ts is not None and ts > self._last_record_ts
                and not (event.reason_code or "").startswith("USER_")):
            # a source event the product never reached (the source timeline ran ahead): not shown
            self.telemetry["discarded_future_events"] += 1
            return
        if ts is not None:
            self._source_ts_us = max(self._source_ts_us, ts)
        if event.event_type is DeviceEventType.STREAM_STARTED and not self.telemetry[
                "device_states"]:
            self._started_ts_us = ts or 0
        if ts is not None and not self._user_stop:
            # known source gap up to this event's time (UI placeholders only)
            self._emit_chunks(self._chunker.advance_to(index_for_timestamp(ts)))
        if event.event_type in (DeviceEventType.STREAM_STOPPED, DeviceEventType.DEVICE_DETACHED):
            self._emit_chunks(self._chunker.flush())
            await self._finish_scientific()
            if self._open_null is not None:
                self.telemetry["waveform_null_intervals"].append(self._open_null)
                self._open_null = None
        self.telemetry["device_states"].append(event.device_state.value)
        self._publish(self._adapter.device_status(event))
        if event.event_type is DeviceEventType.DEVICE_ERROR and not event.recoverable:
            self._fail("DEVICE", "DEVICE_ERROR_UNRECOVERABLE", event.reason_code or "")


class MonitoringService:
    """REST-facing orchestration of session start/stop over the ephemeral state."""

    def __init__(self, state: RuntimeState,
                 inference_factory: Callable[[], CapstoneInferenceClient],
                 *, blocking_lookahead: bool = True) -> None:
        self._state = state
        self._inference_factory = inference_factory
        self._blocking_lookahead = blocking_lookahead

    def _owned(self, owner_user_id: str, session_id: str) -> SessionEntry:
        entry = self._state.sessions.get(session_id)
        if entry is None:
            raise ProductError(ProductErrorCode.NOT_FOUND, f"unknown session {session_id}")
        if entry.owner_user_id != owner_user_id:
            raise ProductError(ProductErrorCode.FORBIDDEN, "session belongs to another user")
        return entry

    async def start(self, owner_user_id: str, session_id: str) -> MonitoringSession:
        entry = self._owned(owner_user_id, session_id)
        if entry.session.state is not SessionState.DEVICE_READY:
            raise ProductError(ProductErrorCode.INVALID_STATE,
                               f"session is {entry.session.state.value}, not DEVICE_READY")
        device = self._state.devices.get(entry.device_id)
        if device is None or device.owner_user_id != owner_user_id:
            raise ProductError(ProductErrorCode.NOT_FOUND, "session device is unknown")
        if device.active_session_id is not None:
            raise ProductError(ProductErrorCode.INVALID_STATE, "device already in a session")
        try:
            await device.node.start_live_monitoring(session_id)
        except IllegalTransitionError as error:
            raise ProductError(ProductErrorCode.INVALID_STATE, str(error)) from error
        device.active_session_id = session_id
        entry.session = advance_session(entry.session, SessionState.MONITORING, 0)
        coordinator = MonitoringCoordinator(
            entry=entry, device=device, inference=self._inference_factory(),
            blocking_lookahead=self._blocking_lookahead)
        entry.coordinator = coordinator
        entry.task = asyncio.create_task(coordinator.run(), name=f"monitoring-{session_id}")
        return entry.session

    async def stop(self, owner_user_id: str, session_id: str) -> MonitoringSession:
        entry = self._owned(owner_user_id, session_id)
        if entry.session.state is not SessionState.MONITORING or entry.coordinator is None:
            raise ProductError(ProductErrorCode.INVALID_STATE,
                               f"session is {entry.session.state.value}, not MONITORING")
        await entry.coordinator.stop()
        assert entry.task is not None
        await entry.task
        return entry.session

    def get(self, owner_user_id: str, session_id: str) -> SessionEntry:
        return self._owned(owner_user_id, session_id)
