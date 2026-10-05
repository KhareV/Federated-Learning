"""CAPSTONE_PERSISTENCE_BRIDGE_V1 -- bounded writes derived from the live monitoring stream.

It observes (never alters, blocks, reorders or fabricates) the unchanged CAP-003 monitoring path:

* ``PersistingJournal`` is a ``MonitoringEventJournal`` that first appends the event exactly as the
  base journal does, then hands the same event to the bridge;
* ``ObservingInferenceClient`` wraps the unchanged ``CapstoneInferenceClient`` and records the typed
  ``InferWindowResponse`` it returned (raw context BEFORE the CAP-003 product projection), keyed by
  (session_id, response.timestamp_us), then reconciled with the real ``inference.result`` event.

Failure policy (frozen): a storage failure raises ``StoragePersistenceError`` from the journal
append; the unchanged coordinator turns that into a system.error and session FAILED. Nothing
is silently lost and the scientific inference result is never altered by storage.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from api.schemas import InferWindowResponse
from capstone_persistence.store import CapstoneSqliteStore, StorageIntegrityError
from product.events import MonitoringLiveEvent
from product.inference.client import InferenceOutcome, OutcomeKind
from product.monitoring.event_journal import MonitoringEventJournal
from product.persistence.preview import (
    CHANNEL,
    ENCODING,
    SOURCE_RATE_HZ,
    PreviewAccumulator,
    encode,
)
from product.session import SessionState

LOGGER = logging.getLogger("nhm.product.persistence")
TERMINAL = (SessionState.COMPLETED.value, SessionState.FAILED.value)


class StoragePersistenceError(RuntimeError):
    """A persistence write failed; the monitoring session is failed, never silently degraded."""


EVENT_TYPE_BY_STATE = {
    ("DISCONNECTED", "LINK_LOST"): "DEVICE_DISCONNECTED",
    ("DISCONNECTED", "USER_DISCONNECT"): "DEVICE_DISCONNECTED",
    ("RECONNECTING", None): "RECONNECT_STARTED",
    ("CONNECTED", "LINK_RESTORED"): "DEVICE_RECONNECTED",
    ("STREAMING", None): "STREAM_STARTED", ("STREAMING", "STREAM_RESUMED"): "STREAM_STARTED",
    ("STOPPED", None): "STREAM_STOPPED", ("DETACHED", None): "DEVICE_DETACHED",
    ("ERROR", None): "DEVICE_ERROR", ("FOUND", None): "DEVICE_DISCOVERED",
    ("SCANNING", None): "SCAN_STARTED", ("PAIRING", None): "PAIRING_STARTED",
    ("CONNECTED", None): "DEVICE_CONNECTED",
}


def device_event_type(device_state: str, reason_code: str | None) -> str:
    """``device.status`` carries no event type; derive it from (state, reason) deterministically."""
    exact = EVENT_TYPE_BY_STATE.get((device_state, reason_code))
    if exact:
        return exact
    for (state, _reason), value in EVENT_TYPE_BY_STATE.items():
        if state == device_state:
            return value
    raise StorageIntegrityError(f"UNMAPPED_DEVICE_STATE:{device_state}")


@dataclass
class SessionAudit:
    inference_rows: int = 0
    monitoring_state_rows: int = 0
    quality_events_seen: int = 0
    quality_rows: int = 0
    context_rows: int = 0
    device_rows: int = 0
    waveform_chunks_folded: int = 0
    withheld_context_timestamps: list[int] = field(default_factory=list)
    preview: dict[str, Any] | None = None
    errors: list[str] = field(default_factory=list)


@dataclass
class SessionMeta:
    session_id: str
    device_id: str
    total_source_samples: int


class PersistenceBridge:
    def __init__(self, store: CapstoneSqliteStore) -> None:
        self._store = store
        self._raw: dict[tuple[str, int], dict[str, Any] | None] = {}
        self._meta: dict[str, SessionMeta] = {}
        self._last_quality: dict[str, tuple[str, str | None]] = {}
        self._preview: dict[str, PreviewAccumulator] = {}
        self.audit: dict[str, SessionAudit] = {}

    def register(self, meta: SessionMeta) -> None:
        self._meta[meta.session_id] = meta
        self.audit.setdefault(meta.session_id, SessionAudit())
        self._preview[meta.session_id] = PreviewAccumulator(meta.total_source_samples)

    # ---- raw response observation ------------------------------------------------------------
    def observe_response(self, session_id: str, response: InferWindowResponse) -> None:
        key = (session_id, response.timestamp_us)
        if key in self._raw:
            raise StorageIntegrityError(f"DUPLICATE_RAW_RESPONSE:{key}")
        self._raw[key] = None if response.context is None else dict(response.context)

    # ---- event mapping -----------------------------------------------------------------------
    def on_event(self, session_id: str, event: MonitoringLiveEvent) -> None:
        audit = self.audit.setdefault(session_id, SessionAudit())
        kind = event.event_type
        payload = event.payload
        try:
            if kind == "device.status":
                self._store.append_device_connection(
                    device_id=payload.device_id, session_id=session_id,
                    event_type=device_event_type(payload.device_state.value, payload.reason_code),
                    device_state=payload.device_state.value, sequence_index=event.sequence_index,
                    reason_code=payload.reason_code, recoverable=payload.recoverable)
                audit.device_rows += 1
            elif kind == "session.status":
                self._on_session_status(session_id, payload.session_state.value)
            elif kind == "inference.result":
                self._on_inference(session_id, event.sequence_index, payload, audit)
            elif kind == "monitoring.state":
                self._store.insert_monitoring_state_event(
                    session_id=session_id, sequence_index=event.sequence_index,
                    timestamp_us=event.source_timestamp_us or 0,
                    monitoring_state=payload.monitoring_state.value,
                    previous_state=payload.previous_state.value if payload.previous_state else None,
                    reason_code=payload.reason_code)
                audit.monitoring_state_rows += 1
            elif kind == "quality.status":
                audit.quality_events_seen += 1
                state = (payload.ecg_quality.value,
                         payload.ppg_quality.value if payload.ppg_quality else None)
                if self._last_quality.get(session_id) != state:  # CHANGE-ONLY storage
                    self._store.insert_quality_event(
                        session_id=session_id, sequence_index=event.sequence_index,
                        timestamp_us=event.source_timestamp_us or 0, ecg_quality=state[0],
                        ppg_quality=state[1])
                    self._last_quality[session_id] = state
                    audit.quality_rows += 1
            elif kind == "context.snapshot":
                self._store.insert_context_snapshot(
                    session_id=session_id, sequence_index=event.sequence_index,
                    timestamp_us=event.source_timestamp_us or 0,
                    context=payload.model_dump(mode="json"))
                audit.context_rows += 1
            elif kind == "waveform.chunk":
                accumulator = self._preview.get(session_id)
                if accumulator is not None and payload.channel == CHANNEL:
                    accumulator.add_chunk(payload.first_sample_index,
                                          payload.first_sample_timestamp_us, list(payload.samples))
                    audit.waveform_chunks_folded += 1  # folded in memory: NO relational rows
            elif kind == "system.error":
                LOGGER.error("monitoring system.error session=%s origin=%s code=%s", session_id,
                             payload.origin, payload.error_code)
        except Exception as error:
            audit.errors.append(repr(error))
            if kind in ("system.error",) or (kind == "session.status"
                                             and payload.session_state.value == "FAILED"):
                LOGGER.error("persistence error while recording a failure event: %r", error)
                return  # never mask the original failure with a second storage error
            raise StoragePersistenceError(f"{kind}: {error!r}") from error

    def _on_session_status(self, session_id: str, state: str) -> None:
        now = self._store.clock()
        if state == SessionState.MONITORING.value:
            self._store.update_session_state(session_id, SessionState.MONITORING, started_at_us=now)
        elif state == SessionState.STOPPING.value:
            self._store.update_session_state(session_id, SessionState.STOPPING)
        elif state in TERMINAL:
            self._store.update_session_state(session_id, SessionState(state), ended_at_us=now)
            self._flush_preview(session_id)

    def _flush_preview(self, session_id: str) -> None:
        accumulator = self._preview.pop(session_id, None)
        if accumulator is None or accumulator.source_samples_seen == 0:
            return
        points = accumulator.finish()
        self._store.upsert_waveform_preview(
            session_id=session_id, channel=CHANNEL, source_rate_hz=SOURCE_RATE_HZ,
            decimation_factor=accumulator.factor, point_count=len(points),
            start_timestamp_us=accumulator.start_timestamp_us or 0, encoding=ENCODING,
            data=encode(points))
        self.audit[session_id].preview = accumulator.describe()

    def _on_inference(self, session_id: str, sequence_index: int, payload: Any,
                      audit: SessionAudit) -> None:
        key = (session_id, payload.timestamp_us)
        if key not in self._raw:
            raise StorageIntegrityError(f"UNMATCHED_INFERENCE_EVENT:{key}")
        raw = self._raw.pop(key)
        self._store.insert_inference_event(
            session_id=session_id, sequence_index=sequence_index,
            timestamp_us=payload.timestamp_us, model_id=payload.model_id,
            calibration_domain=payload.calibration_domain, ecg_quality=payload.ecg_quality.value,
            monitoring_state=payload.monitoring_state.value,
            raw_probability=payload.raw_probability,
            calibrated_probability=payload.source_domain_calibrated_probability,
            threshold=payload.threshold, latency_ms=payload.latency_ms, raw_context=raw)
        audit.inference_rows += 1
        product = payload.context.model_dump(mode="json") if payload.context else None
        if raw is not None and product is not None and not raw.get("context_available") and any(
                raw.get(k) not in (None, False) for k in ("pr_ppg_bpm", "spo2_pct", "spo2_valid")):
            audit.withheld_context_timestamps.append(payload.timestamp_us)

    @property
    def unmatched_raw_responses(self) -> list[tuple[str, int]]:
        return sorted(self._raw)


class PersistingJournal(MonitoringEventJournal):
    """The base journal behaviour is unchanged; each appended event is then persisted."""

    def __init__(self, bridge: PersistenceBridge, session_id: str) -> None:
        super().__init__()
        self._bridge, self._session_id = bridge, session_id

    def append(self, event: MonitoringLiveEvent) -> None:
        super().append(event)  # the live stream is never delayed, reordered or altered by storage
        self._bridge.on_event(self._session_id, event)


class ObservingInferenceClient:
    """Duck-typed wrapper over the unchanged CapstoneInferenceClient (same interface)."""

    def __init__(self, inner: Any, bridge: PersistenceBridge) -> None:
        self._inner, self._bridge = inner, bridge

    @property
    def bound_model_id(self) -> str:
        return self._inner.bound_model_id

    @property
    def attempts(self) -> list[dict[str, Any]]:
        return self._inner.attempts

    def build_request(self, window: Any, session_id: str) -> Any:
        return self._inner.build_request(window, session_id)

    async def infer_window(self, window: Any, session_id: str) -> InferenceOutcome:
        outcome = await self._inner.infer_window(window, session_id)
        if outcome.kind is OutcomeKind.OK and outcome.response is not None:
            self._bridge.observe_response(session_id, outcome.response)
        return outcome

    async def aclose(self) -> None:
        await self._inner.aclose()


def observing_factory(inner_factory: Callable[[], Any], bridge: PersistenceBridge
                      ) -> Callable[[], ObservingInferenceClient]:
    return lambda: ObservingInferenceClient(inner_factory(), bridge)
