"""CAPSTONE_PRODUCT_EVENT_ADAPTER_V1 -- real upstream values -> PRODUCT_LIVE_EVENT_V1.

One centralised sequencer assigns ``sequence_index`` 0,1,2,... across ALL monitoring event kinds and
deterministic ids ``<session_id>-PEV<sequence:06d>``. Every event is validated against the frozen
monitoring union before it leaves this module. Nothing is derived by a frontend and nothing is
fabricated: scientific values come only from a real InferWindowResponse; quality comes only from the
existing runtime window; device state comes only from a CAP-002 DeviceEvent.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from api.schemas import InferWindowResponse, QualityState
from product.devices.base import AdapterType, DeviceEvent
from product.events import (
    MONITORING_ADAPTER,
    QUALITY_UI_LABELS,
    MonitoringLiveEvent,
)
from product.monitoring.waveform import WaveformChunk
from product.session import SessionState


class LogicalClock:
    """Deterministic product clock for canonical replay: strictly increasing, no wall time."""

    def __init__(self, step_us: int = 1000) -> None:
        self._now = 0
        self._step = step_us

    def __call__(self) -> int:
        self._now += self._step
        return self._now


class ProductEventAdapter:
    def __init__(self, session_id: str, clock: Callable[[], int] | None = None) -> None:
        self._session_id = session_id
        self._clock = clock or LogicalClock()
        self._sequence = 0

    @property
    def next_sequence(self) -> int:
        return self._sequence

    def _make(self, event_type: str, payload: Mapping[str, Any],
              source_timestamp_us: int | None = None) -> MonitoringLiveEvent:
        body = {
            "contract_version": "PRODUCT_LIVE_EVENT_V1", "event_id": self.event_id(self._sequence),
            "sequence_index": self._sequence, "emitted_at_us": self._clock(),
            "session_id": self._session_id, "source_timestamp_us": source_timestamp_us,
            "event_type": event_type, "payload": dict(payload),
        }
        event = MONITORING_ADAPTER.validate_python(body)
        self._sequence += 1
        return event

    def event_id(self, sequence: int) -> str:
        return f"{self._session_id}-PEV{sequence:06d}"

    def session_status(self, state: SessionState, elapsed_ms: int,
                       reason_code: str | None = None) -> MonitoringLiveEvent:
        return self._make("session.status", {"session_state": state.value,
                                             "elapsed_ms": max(0, elapsed_ms),
                                             "reason_code": reason_code})

    def device_status(self, event: DeviceEvent) -> MonitoringLiveEvent:
        return self._make("device.status", {
            "device_id": event.device_id, "device_state": event.device_state.value,
            "adapter_type": AdapterType(event.source).value, "reason_code": event.reason_code,
            "recoverable": event.recoverable}, event.source_timestamp_us)

    def waveform_chunk(self, chunk: WaveformChunk) -> MonitoringLiveEvent:
        return self._make("waveform.chunk", {
            "channel": "ECG", "unit": "ADC_COUNTS", "source_rate_hz": 360,
            "first_sample_index": chunk.first_sample_index,
            "first_sample_timestamp_us": chunk.first_sample_timestamp_us,
            "sample_count": len(chunk.samples), "samples": list(chunk.samples)},
            chunk.first_sample_timestamp_us)

    def quality_status(self, window: Mapping[str, Any]) -> MonitoringLiveEvent:
        quality = QualityState(window["ecg_quality"])
        context = window["ppg_context"]
        ppg = context["quality"] if context else None
        return self._make("quality.status", {
            "ecg_quality": quality.value, "ppg_quality": ppg,
            "ui_label": QUALITY_UI_LABELS[quality]}, window["timestamp_us"])

    @staticmethod
    def context_payload(response: InferWindowResponse) -> dict[str, Any]:
        """Context exactly as the released response decided it (no second definition)."""
        context = response.context or {}
        available = bool(context.get("context_available"))
        payload = {
            "hr_ecg_bpm": context.get("hr_ecg_bpm"), "pr_ppg_bpm": context.get("pr_ppg_bpm"),
            "spo2_pct": context.get("spo2_pct"), "spo2_valid": bool(context.get("spo2_valid")),
            "context_available": available, "ppg_quality": context.get("ppg_quality")}
        if not available:
            # CAPSTONE_LIVE_STREAM_BINDING_V1 clarification: the frozen PRODUCT_LIVE_EVENT_V1
            # forbids PPG-derived values on an unavailable context, while the released system can
            # report context_available=False with a pulse rate present (e.g. invalid SpO2). The
            # values are WITHHELD (never altered or invented) and every occurrence is counted.
            payload.update(pr_ppg_bpm=None, spo2_pct=None, spo2_valid=False)
        return payload

    @staticmethod
    def context_values_withheld(response: InferWindowResponse) -> bool:
        context = response.context or {}
        return (not context.get("context_available")) and (
            context.get("pr_ppg_bpm") is not None or context.get("spo2_pct") is not None
            or bool(context.get("spo2_valid")))

    def context_snapshot(self, response: InferWindowResponse) -> MonitoringLiveEvent:
        return self._make("context.snapshot", self.context_payload(response),
                          response.timestamp_us)

    def inference_result(self, response: InferWindowResponse) -> MonitoringLiveEvent:
        return self._make("inference.result", {
            "timestamp_us": response.timestamp_us, "model_id": response.model_id,
            "calibration_id": response.calibration_id,
            "calibration_domain": response.calibration_domain,
            "preprocess_version": response.preprocess_version,
            "alert_policy_id": response.alert_policy_id,
            "ecg_quality": response.ecg_quality.value,
            "monitoring_state": response.monitoring_state.value,
            "context": self.context_payload(response), "latency_ms": response.latency_ms,
            "raw_probability": response.raw_probability,
            "source_domain_calibrated_probability": response.source_domain_calibrated_probability,
            "threshold": response.threshold}, response.timestamp_us)

    def monitoring_state(self, response: InferWindowResponse,
                         previous: str | None) -> MonitoringLiveEvent:
        return self._make("monitoring.state", {
            "monitoring_state": response.monitoring_state.value, "previous_state": previous,
            "reason_code": None}, response.timestamp_us)

    def system_error(self, origin: str, error_code: str, message: str,
                     recoverable: bool = False) -> MonitoringLiveEvent:
        return self._make("system.error", {"error_code": error_code, "message": message[:300],
                                           "recoverable": recoverable, "origin": origin})
