"""EXPERIMENTAL, NOT VALID: MODEL_V2_FINAL analysis of resampled MongoDB hardware telemetry.

The ESP32 sketch transmits ~20 ECG ADC readings per second with no verified sampling rate and no
verified analogue scaling. The frozen V2 path expects 360 Hz source samples in millivolt-derived
counts. This module makes that mismatch explicit instead of hiding it:

* real readings are linearly interpolated onto a 360 Hz grid, only BETWEEN two real readings that are
  at most ``MAX_BRIDGE_US`` apart. Longer gaps stay gaps (the unchanged runtime flags them);
* ADC counts are mapped to counts-per-mV with a DOCUMENTED ASSUMPTION (AD8232 gain 100, 3.3 V / 12 bit);
* the unchanged ``WearableStreamRuntime`` (PREPROC_V1) builds the windows and the released inference
  service scores them. No frozen model, calibration or preprocessing code is modified.

Output is labelled EXPERIMENTAL / RESAMPLED / NOT VALID / NOT DIAGNOSTIC and is never mixed with
the simulated-wearable results.
"""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime
from typing import Any

import numpy as np

from simulation.stream_runtime_v2013 import WearableStreamRuntime
from simulation.types import ObservedRecord

SOURCE_HZ = 360
MAX_BRIDGE_US = 1_000_000  # same threshold the live chart uses to break the line
ADC_MIDPOINT = 2048
# 3.3 V / 4095 = 0.806 mV per ADC count at the pin; AD8232 gain 100 -> ~124 counts per 1 mV of ECG.
# The runtime counts are 1000 per mV, so one ADC count = 1000 / 124.1 ~= 8.06 runtime counts.
RUNTIME_COUNTS_PER_ADC = 8.06
MIN_SECONDS_FOR_FIRST_WINDOW = 15.0
LABEL = "EXPERIMENTAL · RESAMPLED FROM LOW-RATE MONGODB TELEMETRY · NOT VALID · NOT DIAGNOSTIC"
ASSUMPTIONS = {
    "source_rate": "not verified; ~20 readings/s observed (server ingestion time)",
    "resampling": f"linear interpolation to {SOURCE_HZ} Hz between real readings; gaps over {MAX_BRIDGE_US / 1e6:g} s are not bridged",
    "adc_scaling": "ASSUMED AD8232 gain 100, 3.3 V reference, 12-bit ADC, midpoint 2048 (unverified)",
    "runtime_counts_per_adc_count": RUNTIME_COUNTS_PER_ADC,
    "ppg_context": "device-reported BPM used as pulse rate; device SpO2 treated as valid only when > 0; PPG QUALITY IS AN ASSUMPTION: VALID while the device reports both a pulse rate and an SpO2 (finger present), absent otherwise; the sketch supplies no PPG signal quality",
    "validity": "MODEL_V2_FINAL was validated on MIT-BIH 360 Hz ECG, not on this signal chain",
}


def _parse(value: str) -> int:
    return int(datetime.fromisoformat(value).timestamp() * 1_000_000)


def readings_to_records(readings: list[dict[str, Any]], session_id: str) -> tuple[list[ObservedRecord], int]:
    """Return resampled records and the wall-clock microsecond of stream time zero."""
    pts: dict[int, dict[str, Any]] = {}
    for r in readings:
        pts[_parse(r["ingested_at"])] = r  # equal timestamps: keep the last reading
    stamps = sorted(pts)
    if len(stamps) < 2:
        return [], stamps[0] if stamps else 0
    t0 = stamps[0]
    rel = np.asarray([t - t0 for t in stamps], dtype=np.float64)
    adc = np.asarray([pts[t]["ecg"] for t in stamps], dtype=np.float64)
    records: list[ObservedRecord] = []
    last_n = -1
    for i in range(len(stamps) - 1):
        a, b = rel[i], rel[i + 1]
        if b - a > MAX_BRIDGE_US:
            continue
        n0 = int(np.ceil(a * SOURCE_HZ / 1e6))
        n1 = int(np.floor(b * SOURCE_HZ / 1e6))
        if n1 < n0:
            continue
        idx = np.arange(max(n0, last_n + 1), n1 + 1, dtype=np.int64)
        if idx.size == 0:
            continue
        times = idx * 1e6 / SOURCE_HZ
        values = np.interp(times, rel[i : i + 2], adc[i : i + 2])
        ref = pts[stamps[i]]
        bpm, spo2 = ref.get("bpm"), ref.get("spo2")
        for n, v in zip(idx.tolist(), values.tolist(), strict=True):
            records.append(
                ObservedRecord(
                    contract_version="SAMPLE_SCHEMA_V1",
                    participant_id="HARDWARE_SOURCE_UNKNOWN",
                    session_id=session_id,
                    timestamp_us=int(round(n * 1e6 / SOURCE_HZ)),
                    sample_index=n,
                    ecg_raw=int(round((v - ADC_MIDPOINT) * RUNTIME_COUNTS_PER_ADC)),
                    ppg_red_raw=None,
                    ppg_ir_raw=None,
                    spo2_pct=float(spo2) if spo2 else None,
                    spo2_valid=bool(spo2),
                    hr_ecg_bpm=None,
                    pr_ppg_bpm=float(bpm) if bpm else None,
                    ecg_quality="VALID",  # ignored: the runtime recomputes quality itself
                    ppg_quality="VALID" if bpm and spo2 else None,   # ASSUMED (see ASSUMPTIONS['ppg_context']): the device supplies no PPG quality
                    source="HARDWARE_MONGO_EXPERIMENTAL_RESAMPLED",
                    preprocess_version=None,
                )
            )
        last_n = int(idx[-1])
    return records, t0


def build_windows(readings: list[dict[str, Any]], session_id: str, model_id: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    records, t0 = readings_to_records(readings, session_id)
    summary = {
        "input_readings": len(readings),
        "resampled_records": len(records),
        "stream_start": datetime.fromtimestamp(t0 / 1e6).astimezone().isoformat() if t0 else None,
    }
    if not records:
        return [], summary
    runtime = WearableStreamRuntime(session_id=session_id, model_id=model_id, replay_id="HARDWARE_EXPERIMENTAL")
    events: list[dict[str, Any]] = []
    for start in range(0, len(records), SOURCE_HZ):
        events.extend(runtime.ingest(records[start : start + SOURCE_HZ]))
    events.extend(runtime.finish())
    for event in events:
        event["wall_time"] = datetime.fromtimestamp((t0 + event["timestamp_us"]) / 1e6).astimezone().isoformat()
    summary["windows"] = len(events)
    return events, summary


def window_key(window: dict[str, Any]) -> str:
    payload = json.dumps([window["ecg"]["samples"], window["ppg_context"], window["model_id"]], sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


class V2Cache:
    """Inference results keyed by window content, so a window is scored once per model identity."""

    def __init__(self, store: Any) -> None:
        self.store = store
        self.lock = threading.Lock()
        with store._lock, store._connection:
            store._connection.execute(
                """CREATE TABLE IF NOT EXISTS hardware_v2_experimental (
                session_id TEXT NOT NULL, window_key TEXT NOT NULL, payload TEXT NOT NULL,
                PRIMARY KEY(session_id, window_key))"""
            )

    def get(self, sid: str, key: str) -> dict[str, Any] | None:
        with self.store._lock:
            row = self.store._connection.execute(
                "SELECT payload FROM hardware_v2_experimental WHERE session_id=? AND window_key=?", (sid, key)
            ).fetchone()
        return json.loads(row["payload"]) if row else None

    def put(self, sid: str, key: str, payload: dict[str, Any]) -> None:
        with self.store._lock, self.store._connection:
            self.store._connection.execute(
                "INSERT OR REPLACE INTO hardware_v2_experimental VALUES (?,?,?)", (sid, key, json.dumps(payload))
            )
