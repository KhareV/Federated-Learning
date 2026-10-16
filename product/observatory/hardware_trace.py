# ruff: noqa: E501
"""Observatory views of RECORDED-HARDWARE sessions: a per-window signal trace and a session replay timeline.

Both are derived, read-only views of what the Monitor page already treats as EXPERIMENTAL: the recorded readings are resampled onto the V2 source grid
(``api.hardware_v2_experimental``: linear interpolation between real readings only, documented ADC-scaling ASSUMPTION) and the UNCHANGED canonical operators
(gap controller, causal resampler, ECG filter, ``PREPROC_V1`` windowing / quality gate) are observed with the same stage observers as the synthetic Observatory
(``product.observatory.pipeline.reconstruct_window``). Nothing here changes a frozen operator, trains, calibrates or claims validity: MODEL_V2_FINAL was validated on
MIT-BIH ECG, not on this signal chain.

* ``window_list`` / ``window_trace``: the windows a session emitted and the stage-by-stage trace of one of them, with the released model's result attached when the
  experimental scorer has produced one (cached per window content, shared with the Monitor page);
* ``timeline``: the SessionTimeline-shaped replay (quality, per-window model output and policy state, context) that the existing replay page renders. Policy states are the
  released service's per-window outputs; state CHANGES are derived from consecutive windows and labelled so. Windows the quality gate rejects have no model result and none is invented."""

from __future__ import annotations

import hashlib
import json
import threading
from collections import OrderedDict
from types import SimpleNamespace
from typing import Any

from api.hardware_v2_experimental import ASSUMPTIONS, LABEL, build_windows, readings_to_records, window_key
from typing import Literal

from product.observatory.models import PersistedInference, WindowTrace
from product.observatory.pipeline import reconstruct_window
from simulation.stream_runtime_v2013 import CADENCE_US, EMIT_MARGIN_US, FIRST_RIGHT_EDGE_US

class HardwareWindowTrace(WindowTrace):
    """``WindowTrace`` (a protected Observatory contract, deliberately not edited) with the two classification fields widened for recorded hardware."""

    classification: Literal["DETERMINISTIC_LOCAL_RECONSTRUCTION", "CAPTURED_LIVE_PREPROCESSING", "RECORDED_HARDWARE_RECONSTRUCTION"] = "RECORDED_HARDWARE_RECONSTRUCTION"  # type: ignore[assignment]
    source_kind: Literal["SYNTHETIC_VIRTUAL_WEARABLE", "RECORDED_HARDWARE_RESAMPLED"] = "RECORDED_HARDWARE_RESAMPLED"  # type: ignore[assignment]


SOURCE_KIND = "RECORDED_HARDWARE_RESAMPLED"
CLASSIFICATION = "RECORDED_HARDWARE_RECONSTRUCTION"
CLAIM_BOUNDARY = "RECORDED_HARDWARE_RESAMPLED_EXPERIMENTAL_NOT_VALID_NOT_DIAGNOSTIC"
TIMELINE_CLAIM = "RECORDED_HARDWARE_RESAMPLED_EXPERIMENTAL_DERIVED_TIMELINE_NOT_VALID_NOT_DIAGNOSTIC"
UNIT = "mV under ASSUMED AD8232 scaling (unverified)"
LIMITATIONS = [
    "Deterministic re-processing of your RECORDED readings (resampled from the low-rate telemetry onto the V2 source grid), not captured live intermediate arrays.",
    "Resampling is linear interpolation between real readings only; gaps longer than one second are never bridged.",
    "The ADC-to-millivolt scaling is an ASSUMPTION (AD8232 gain 100, 3.3 V reference, 12-bit); physical amplitude is not calibrated.",
    "MODEL_V2_FINAL was validated on MIT-BIH ECG, not on this signal chain: any model result shown is EXPERIMENTAL, not valid and not diagnostic.",
    "Displayed chart points are decimated from the actual selected arrays; no values are interpolated for display.",
]
_CACHE: OrderedDict[tuple[str, str], tuple[list[dict[str, Any]], dict[str, Any], list[Any]]] = OrderedDict()
_LOCK = threading.Lock()


def _prepared(sid: str, readings: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any], list[Any]]:
    """(emitted windows, summary, resampled records) of a session, memoised on (session, content digest of the readings), so a session that is still recording or was edited is never served stale."""
    digest = hashlib.sha256(json.dumps([[r["document_id"], r["ingested_at"], r["ecg"], r.get("bpm"), r.get("spo2")] for r in readings], separators=(",", ":")).encode()).hexdigest()
    key = (sid, digest)
    with _LOCK:
        if key in _CACHE:
            _CACHE.move_to_end(key)
            return _CACHE[key]
    windows, summary = build_windows(readings, sid, "MODEL_V2_FINAL")
    records, _ = readings_to_records(readings, sid)
    with _LOCK:
        _CACHE[key] = (windows, summary, records)
        while len(_CACHE) > 4:
            _CACHE.popitem(last=False)
    return windows, summary, records


def window_list(sid: str, readings: list[dict[str, Any]]) -> dict[str, Any]:
    windows, summary, _ = _prepared(sid, readings)
    return {"session_id": sid, "label": LABEL, "source_kind": SOURCE_KIND, "claim_boundary": CLAIM_BOUNDARY, "assumptions": ASSUMPTIONS, "input_readings": summary["input_readings"],
            "windows": [{"window_index": int(w["sequence_index"]), "window_id": w["window_id"], "right_timestamp_us": int(w["timestamp_us"]), "ecg_quality": w["ecg_quality"],
                         "quality_reasons": w["diagnostics"]["quality_reasons"]} for w in windows]}


def emitted_window(sid: str, readings: list[dict[str, Any]], window_index: int) -> dict[str, Any]:
    windows, _, _ = _prepared(sid, readings)
    found = next((w for w in windows if int(w["sequence_index"]) == window_index), None)
    if found is None:
        raise LookupError("this recorded session did not emit that window")
    return found


def window_trace(sid: str, readings: list[dict[str, Any]], window_index: int, inference: dict[str, Any] | None = None, *, evidence_status: str | None = None) -> HardwareWindowTrace:
    """Stage trace of one emitted window of a recorded session. ``inference`` is the released service's response (dict) for exactly this window, when one exists."""
    _, _, records = _prepared(sid, readings)
    if not records:
        raise LookupError("this recorded session has too few readings to resample")
    window = emitted_window(sid, readings, window_index)
    duration_s = int(records[-1].timestamp_us // 1_000_000) + 2
    scenario = SimpleNamespace(scenario_id=f"RECORDED_HARDWARE:{sid}", duration_s=duration_s, profile=lambda: None)
    right_us = FIRST_RIGHT_EDGE_US + window_index * CADENCE_US
    if right_us + EMIT_MARGIN_US >= duration_s * 1_000_000:
        raise ValueError("WINDOW_INDEX_OUT_OF_SESSION_RANGE")
    trace = reconstruct_window(scenario, window_index, session_id=sid, records_factory=lambda _profile: iter(records))  # type: ignore[arg-type]
    if trace.window_id != window["window_id"] or trace.quality_state != window["ecg_quality"]:
        raise RuntimeError("RECONSTRUCTED_WINDOW_MISMATCH")      # the observed run must equal the unobserved experimental windowing
    stages = [stage.model_copy(update={"unit": UNIT if stage.unit == "synthetic mV convention" else stage.unit}) for stage in trace.stages]
    persisted = None
    status = evidence_status or "NOT_ATTACHED_NO_MODEL_RESULT_FOR_THIS_WINDOW"
    if inference is not None:
        persisted = PersistedInference(model_id=inference.get("model_id"), calibration_domain=inference.get("calibration_domain"), raw_probability=inference.get("raw_probability"),
                                       source_domain_calibrated_probability=inference.get("source_domain_calibrated_probability"), threshold=inference.get("threshold"),
                                       monitoring_state=str(inference["monitoring_state"]), ecg_quality=str(inference["ecg_quality"]))
        status = evidence_status or "EXPERIMENTAL_MODEL_RESULT_SCORED_FROM_RESAMPLED_RECORDED_WINDOW"
    ctx = window.get("ppg_context")
    return HardwareWindowTrace(**trace.model_dump() | {
        "classification": CLASSIFICATION, "source_kind": SOURCE_KIND, "scenario_id": f"RECORDED_HARDWARE:{sid}", "session_id": sid, "stages": stages,
        "context_available": bool(ctx and (ctx.get("pr_bpm") or ctx.get("spo2_valid"))), "persisted_inference": persisted, "inference_evidence_status": status,
        "claim_boundary": CLAIM_BOUNDARY, "limitations": LIMITATIONS,
    })


def timeline(sid: str, readings: list[dict[str, Any]], results: dict[str, dict[str, Any]], *, started_at_us: int = 0) -> dict[str, Any]:
    """SessionTimeline-shaped replay. ``results`` maps ``window_key`` -> the experimental scorer's cached result (``{"outcome", "inference", ...}``).
    A window with no result contributes no INFERENCE record (nothing is invented); ``pending`` counts quality-eligible windows still waiting for a result."""
    windows, summary, _ = _prepared(sid, readings)
    items: list[dict[str, Any]] = []
    previous_quality: str | None = None
    previous_state: str | None = None
    previous_ctx: tuple[Any, ...] | None = None
    pending = scored = 0

    def add(kind: str, ts: int, payload: dict[str, Any]) -> None:
        items.append({"kind": kind, "sequence_index": len(items), "source_timestamp_us": ts, "payload": payload})

    for w in windows:
        ts = int(w["timestamp_us"])
        ctx = w.get("ppg_context") or {}
        snapshot = (ctx.get("pr_bpm"), ctx.get("spo2_pct"), bool(ctx.get("spo2_valid")))
        if snapshot != previous_ctx:
            add("CONTEXT_SNAPSHOT", ts, {"hr_ecg_bpm": None, "pr_ppg_bpm": ctx.get("pr_bpm"), "spo2_pct": ctx.get("spo2_pct"), "spo2_valid": bool(ctx.get("spo2_valid")),
                                        "context_available": bool(ctx.get("pr_bpm") or ctx.get("spo2_valid")), "ppg_quality": ctx.get("quality")})
            previous_ctx = snapshot
        quality = str(w["ecg_quality"])
        if quality != previous_quality:
            add("QUALITY_CHANGE", ts, {"ecg_quality": quality, "ppg_quality": ctx.get("quality"), "storage_basis": "CHANGE_ONLY"})
            previous_quality = quality
        result = results.get(window_key(w))
        response = (result or {}).get("inference")
        if quality == "UNUSABLE":
            continue                                   # the quality gate rejects the window before the model: there is no result to show, and none is invented
        if response is None:
            pending += 1
            continue
        scored += 1
        state = str(response["monitoring_state"])
        add("INFERENCE", ts, {"model_id": response.get("model_id"), "calibration_domain": response.get("calibration_domain"), "ecg_quality": str(response["ecg_quality"]), "monitoring_state": state,
                              "raw_probability": response.get("raw_probability"), "source_domain_calibrated_probability": response.get("source_domain_calibrated_probability"),
                              "threshold": response.get("threshold"), "latency_ms": response.get("latency_ms"), "probability_role": "RESEARCH_TECHNICAL_METADATA"})
        if state != previous_state:
            add("MONITORING_STATE_CHANGE", ts, {"monitoring_state": state, "previous_state": previous_state, "reason_code": "DERIVED_FROM_CONSECUTIVE_WINDOW_RESULTS"})
            previous_state = state
    return {"session_id": sid, "timeline_version": "CAPSTONE_SESSION_TIMELINE_V1", "source_timeline": items, "device_lifecycle": [], "waveform_previews": [],
            "time_domains": {"source_timeline": "SOURCE_TIMELINE", "device_lifecycle": "PRODUCT_CLOCK"},
            "time_domain_explanation": "Source time is measured from the first recorded reading of this hardware session; policy-state changes are derived from consecutive per-window results of the released service, not from a persisted monitoring state machine.",
            "claim_boundary": TIMELINE_CLAIM, "label": LABEL, "source_kind": SOURCE_KIND, "assumptions": ASSUMPTIONS,
            "windows_total": len(windows), "windows_scored": scored, "windows_pending": pending, "complete": pending == 0,
            "windows_unusable": sum(1 for w in windows if w["ecg_quality"] == "UNUSABLE")}
