"""CAPSTONE_SESSION_EVIDENCE_STORE_V1: owner-scoped views of existing SQLite evidence.

Only session_summaries is writable. In particular inference_events.context_json is never
selected: that column predates the public context-withholding projection.
"""

from __future__ import annotations

import json
import math
import sqlite3
import threading
from collections import Counter
from collections.abc import Callable
from pathlib import Path

from product.api.errors import ProductError, ProductErrorCode
from product.history.models import (
    ContextSnapshotPayload,
    DeviceLifecycleItem,
    InferencePayload,
    QualityChangePayload,
    SessionSummary,
    SessionTimeline,
    SourceTimelineItem,
    StateChangePayload,
    WaveformPreview,
)
from product.persistence.preview import MAX_POINTS, decode

SUMMARY_VERSION = "SESSION_SUMMARY_V1_INFERRED_WINDOWS"
KIND_ORDER = {"INFERENCE": 0, "MONITORING_STATE_CHANGE": 1,
              "QUALITY_CHANGE": 2, "CONTEXT_SNAPSHOT": 3}


def _finite(values: list[float | None]) -> tuple[float | None, float | None, float | None]:
    valid = [float(v) for v in values if v is not None and math.isfinite(v)]
    return (min(valid), sum(valid) / len(valid), max(valid)) if valid else (None, None, None)


class SessionEvidenceStore:
    """Thread-safe companion connection; WAL compatible; no schema ownership."""

    def __init__(self, path: str | Path, *, clock: Callable[[], int]) -> None:
        if str(path) == ":memory:":
            raise ValueError("SESSION_EVIDENCE_REQUIRES_SHARED_FILE_DATABASE")
        self._lock = threading.RLock()
        self._clock = clock
        self._db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None,
                                   timeout=30)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.execute("PRAGMA journal_mode = WAL")

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def _owner_session(self, session_id: str, user_id: str) -> sqlite3.Row:
        row = self._db.execute(
            "SELECT session_id, user_id, state, started_at_us, ended_at_us "
            "FROM monitoring_sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row is None:
            raise ProductError(ProductErrorCode.NOT_FOUND, "session not found")
        if row["user_id"] != user_id:
            raise ProductError(ProductErrorCode.FORBIDDEN, "session belongs to another user")
        return row

    def _summary_from_row(self, row: sqlite3.Row) -> SessionSummary:
        return SessionSummary(
            session_id=row["session_id"], summary_version=row["summary_version"],
            duration_ms=row["duration_ms"], windows_inferred=row["windows_inferred"],
            state_counts=json.loads(row["state_counts_json"]),
            quality_counts=json.loads(row["quality_counts_json"]),
            hr_min=row["hr_min"], hr_mean=row["hr_mean"], hr_max=row["hr_max"],
            spo2_min=row["spo2_min"], spo2_mean=row["spo2_mean"],
            spo2_max=row["spo2_max"], reconnect_count=row["reconnect_count"],
            disconnect_count=row["disconnect_count"], generated_at_us=row["generated_at_us"],
        )

    def summary(self, session_id: str, user_id: str) -> SessionSummary:
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                session = self._owner_session(session_id, user_id)
                if session["state"] != "COMPLETED":
                    raise ProductError(ProductErrorCode.INVALID_STATE,
                                       "completed-session summary unavailable for this state")
                row = self._db.execute(
                    "SELECT * FROM session_summaries WHERE session_id = ?", (session_id,)
                ).fetchone()
                if row is None:
                    # Count inference rows, never change-only quality rows.
                    inference = self._db.execute(
                        "SELECT monitoring_state, ecg_quality FROM inference_events "
                        "WHERE session_id = ? ORDER BY sequence_index, inference_id", (session_id,)
                    ).fetchall()
                    context = self._db.execute(
                        "SELECT hr_ecg_bpm, spo2_pct, spo2_valid FROM context_snapshots "
                        "WHERE session_id = ? ORDER BY sequence_index, snapshot_id", (session_id,)
                    ).fetchall()
                    hr = _finite([r["hr_ecg_bpm"] for r in context])
                    spo2 = _finite([r["spo2_pct"] if r["spo2_valid"] else None for r in context])
                    device = self._db.execute(
                        "SELECT event_type FROM device_connections WHERE session_id = ? "
                        "ORDER BY at_us, connection_id",
                        (session_id,),
                    ).fetchall()
                    counts = Counter(r["event_type"] for r in device)
                    duration = (session["ended_at_us"] - session["started_at_us"]) // 1000
                    if duration < 0:
                        raise ValueError("NEGATIVE_PRODUCT_LIFECYCLE_DURATION")
                    self._db.execute(
                        "INSERT INTO session_summaries (session_id, summary_version, duration_ms, "
                        "windows_inferred, state_counts_json, quality_counts_json, "
                        "hr_min, hr_mean, "
                        "hr_max, spo2_min, spo2_mean, spo2_max, reconnect_count, disconnect_count, "
                        "generated_at_us) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (session_id, SUMMARY_VERSION, duration, len(inference),
                         json.dumps(dict(sorted(Counter(
                             r["monitoring_state"] for r in inference).items())), sort_keys=True),
                         json.dumps(dict(sorted(Counter(
                             r["ecg_quality"] for r in inference).items())), sort_keys=True),
                         *hr, *spo2, counts["DEVICE_RECONNECTED"], counts["DEVICE_DISCONNECTED"],
                         self._clock()),
                    )
                    row = self._db.execute(
                        "SELECT * FROM session_summaries WHERE session_id = ?", (session_id,)
                    ).fetchone()
                result = self._summary_from_row(row)
                self._db.execute("COMMIT")
                return result
            except BaseException:
                self._db.execute("ROLLBACK")
                raise

    def timeline(self, session_id: str, user_id: str) -> SessionTimeline:
        with self._lock:
            self._owner_session(session_id, user_id)
            items: list[SourceTimelineItem] = []
            # Explicit column whitelist: never SELECT * from inference_events.
            for row in self._db.execute(
                "SELECT sequence_index, timestamp_us, model_id, calibration_domain, ecg_quality, "
                "monitoring_state, raw_probability, source_domain_calibrated_probability, "
                "threshold, latency_ms FROM inference_events WHERE session_id = ? "
                "ORDER BY sequence_index, inference_id", (session_id,)
            ):
                items.append(SourceTimelineItem(
                    kind="INFERENCE", sequence_index=row["sequence_index"],
                    source_timestamp_us=row["timestamp_us"],
                    payload=InferencePayload(**{key: row[key] for key in (
                        "model_id", "calibration_domain", "ecg_quality", "monitoring_state",
                        "raw_probability", "source_domain_calibrated_probability", "threshold",
                        "latency_ms")}),
                ))
            for row in self._db.execute(
                "SELECT sequence_index, timestamp_us, monitoring_state, "
                "previous_state, reason_code "
                "FROM monitoring_state_events WHERE session_id = ? "
                "ORDER BY sequence_index, event_id", (session_id,)
            ):
                items.append(SourceTimelineItem(
                    kind="MONITORING_STATE_CHANGE", sequence_index=row["sequence_index"],
                    source_timestamp_us=row["timestamp_us"],
                    payload=StateChangePayload(monitoring_state=row["monitoring_state"],
                                               previous_state=row["previous_state"],
                                               reason_code=row["reason_code"]),
                ))
            for row in self._db.execute(
                "SELECT sequence_index, timestamp_us, ecg_quality, ppg_quality "
                "FROM signal_quality_events WHERE session_id = ? "
                "ORDER BY sequence_index, event_id", (session_id,)
            ):
                items.append(SourceTimelineItem(
                    kind="QUALITY_CHANGE", sequence_index=row["sequence_index"],
                    source_timestamp_us=row["timestamp_us"],
                    payload=QualityChangePayload(ecg_quality=row["ecg_quality"],
                                                 ppg_quality=row["ppg_quality"]),
                ))
            # This is the PUBLIC projection, not inference_events.context_json.
            for row in self._db.execute(
                "SELECT sequence_index, timestamp_us, hr_ecg_bpm, pr_ppg_bpm, spo2_pct, "
                "spo2_valid, context_available, ppg_quality FROM context_snapshots "
                "WHERE session_id = ? ORDER BY sequence_index, snapshot_id", (session_id,)
            ):
                items.append(SourceTimelineItem(
                    kind="CONTEXT_SNAPSHOT", sequence_index=row["sequence_index"],
                    source_timestamp_us=row["timestamp_us"],
                    payload=ContextSnapshotPayload(
                        hr_ecg_bpm=row["hr_ecg_bpm"], pr_ppg_bpm=row["pr_ppg_bpm"],
                        spo2_pct=row["spo2_pct"], spo2_valid=bool(row["spo2_valid"]),
                        context_available=bool(row["context_available"]),
                        ppg_quality=row["ppg_quality"]),
                ))
            items.sort(key=lambda item: (item.sequence_index, KIND_ORDER[item.kind],
                                         item.source_timestamp_us))
            lifecycle = [DeviceLifecycleItem(
                event_type=row["event_type"], device_state=row["device_state"],
                reason_code=row["reason_code"],
                recoverable=None if row["recoverable"] is None else bool(row["recoverable"]),
                at_us=row["at_us"])
                for row in self._db.execute(
                    "SELECT event_type, device_state, reason_code, recoverable, at_us "
                    "FROM device_connections WHERE session_id = ? ORDER BY at_us, connection_id",
                    (session_id,))]
            previews: list[WaveformPreview] = []
            for row in self._db.execute(
                "SELECT channel, source_rate_hz, decimation_factor, point_count, "
                "start_timestamp_us, encoding, data FROM waveform_previews WHERE session_id = ? "
                "ORDER BY channel, preview_id", (session_id,)
            ):
                if row["encoding"] != "JSON_ZLIB_V1":
                    raise ValueError("UNSUPPORTED_PREVIEW_ENCODING")
                points = decode(row["data"])
                if row["point_count"] != len(points) or len(points) > MAX_POINTS:
                    raise ValueError("PREVIEW_BOUND_OR_COUNT_MISMATCH")
                previews.append(WaveformPreview(
                    channel=row["channel"], source_rate_hz=row["source_rate_hz"],
                    decimation_factor=row["decimation_factor"], point_count=row["point_count"],
                    start_timestamp_us=row["start_timestamp_us"], points=points))
            return SessionTimeline(session_id=session_id, source_timeline=items,
                                   device_lifecycle=lifecycle, waveform_previews=previews)
