"""CAPSTONE_SQLITE_STORE_V1 -- stdlib ``sqlite3`` repository for the capstone product.

Connection discipline: ``PRAGMA foreign_keys = ON`` on every connection, ``journal_mode = WAL`` for
file databases, schema version in ``PRAGMA user_version`` (no metadata table). Product metadata and
history only: no raw 360 Hz sample table exists, no credentials are stored, FL tables stay empty.
Lifecycle timestamps are UTC epoch microseconds from an injectable clock; source/physiological time
is a separate field and is never mixed with them.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from product.auth.base import AuthIdentity
from product.persistence.schema import POLICY_PATH, SCHEMA_VERSION, ddl_statements
from product.session import (
    MonitoringSession,
    RuntimeIdentity,
    SessionState,
    SimulationProvenance,
)

NONTERMINAL_STATES = (SessionState.CREATED.value, SessionState.DEVICE_READY.value,
                      SessionState.MONITORING.value, SessionState.STOPPING.value)
DEFAULT_DB_PATH = "data/capstone/product.sqlite3"
ENV_DB_PATH = "NHM_PRODUCT_DB_PATH"
FUTURE_TABLES = ("session_summaries", "federation_runs", "federation_rounds",
                 "fl_client_statuses", "candidate_models", "governance_decisions")


class SchemaVersionError(RuntimeError):
    """The database carries a schema version this store does not understand."""


class StorageIntegrityError(RuntimeError):
    """A persistence invariant was violated (fail closed; never silently dropped)."""


def utc_micros() -> int:
    return time.time_ns() // 1000


class CapstoneSqliteStore:
    def __init__(self, path: str | Path = DEFAULT_DB_PATH, *,
                 clock: Callable[[], int] = utc_micros) -> None:
        self.path = str(path)
        self.clock = clock
        self._lock = threading.RLock()
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        if self.path != ":memory:":
            self._connection.execute("PRAGMA journal_mode = WAL")
        self._initialise()

    # ---- lifecycle ---------------------------------------------------------------------------
    def _initialise(self) -> None:
        version = self._connection.execute("PRAGMA user_version").fetchone()[0]
        if version == 0:
            existing = self._connection.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
            if existing:
                raise SchemaVersionError("UNVERSIONED_DATABASE_WITH_TABLES")
            policy = json.loads(POLICY_PATH.read_text())
            with self._lock, self._connection:
                for statement in ddl_statements(policy):
                    self._connection.execute(statement)
                self._connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        elif version != SCHEMA_VERSION:
            raise SchemaVersionError(f"UNSUPPORTED_SCHEMA_VERSION:{version}")

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def _run(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        with self._lock, self._connection:
            return self._connection.execute(sql, params)

    def _all(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._connection.execute(sql, params).fetchall()

    # ---- diagnostics -------------------------------------------------------------------------
    def pragma(self, name: str) -> Any:
        with self._lock:
            return self._connection.execute(f"PRAGMA {name}").fetchone()[0]

    def table_names(self) -> list[str]:
        rows = self._all("SELECT name FROM sqlite_master WHERE type='table' "
                         "AND name NOT LIKE 'sqlite_%' ORDER BY name")
        return [r["name"] for r in rows]

    def row_counts(self) -> dict[str, int]:
        return {t: self._all(f"SELECT count(*) AS n FROM {t}")[0]["n"] for t in self.table_names()}

    def integrity_check(self) -> list[str]:
        return [r[0] for r in self._all("PRAGMA integrity_check")]

    def foreign_key_check(self) -> list[tuple[Any, ...]]:
        return [tuple(r) for r in self._all("PRAGMA foreign_key_check")]

    def schema_dump(self) -> list[str]:
        return [r["sql"] for r in self._all(
            "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type, name")]

    # ---- users -------------------------------------------------------------------------------
    def upsert_user(self, identity: AuthIdentity) -> None:
        """Mirrors AuthIdentity metadata only: never a token, cookie, password or secret."""
        self._run(
            "INSERT INTO users (user_id, auth_provider, display_name, email, demo_mode,"
            " created_at_us) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET"
            " auth_provider=excluded.auth_provider, display_name=excluded.display_name,"
            " email=excluded.email, demo_mode=excluded.demo_mode",
            (identity.user_id, identity.auth_provider.value, identity.display_name, identity.email,
             int(identity.demo_mode), self.clock()))

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        rows = self._all("SELECT * FROM users WHERE user_id = ?", (user_id,))
        return dict(rows[0]) if rows else None

    # ---- devices -----------------------------------------------------------------------------
    def insert_device(self, *, device_id: str, user_id: str, display_name: str, adapter_type: str,
                      source_dataset_id: str | None, source_mode: str | None,
                      simulation_version: str | None, scenario_id: str | None,
                      capabilities: Mapping[str, Any]) -> None:
        self._run(
            "INSERT INTO devices (device_id, user_id, display_name, adapter_type,"
            " source_dataset_id, source_mode, simulation_version, scenario_id, capabilities_json,"
            " created_at_us) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (device_id, user_id, display_name, adapter_type, source_dataset_id, source_mode,
             simulation_version, scenario_id, json.dumps(capabilities, sort_keys=True),
             self.clock()))

    def list_device_rows(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self._all(
            "SELECT * FROM devices ORDER BY created_at_us, device_id")]

    def append_device_connection(self, *, device_id: str, session_id: str | None, event_type: str,
                                 device_state: str, sequence_index: int, reason_code: str | None,
                                 recoverable: bool) -> str:
        with self._lock:
            count = self._connection.execute(
                "SELECT count(*) FROM device_connections WHERE device_id = ?",
                (device_id,)).fetchone()[0]
            connection_id = f"{device_id}-CN{count + 1:08d}"
            self._run(
                "INSERT INTO device_connections (connection_id, device_id, session_id, event_type,"
                " device_state, sequence_index, reason_code, recoverable, at_us)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (connection_id, device_id, session_id, event_type, device_state, sequence_index,
                 reason_code, int(recoverable), self.clock()))
        return connection_id

    def list_device_connections(self, device_id: str) -> list[dict[str, Any]]:
        return [dict(r) for r in self._all(
            "SELECT * FROM device_connections WHERE device_id = ? ORDER BY connection_id",
            (device_id,))]

    # ---- sessions ----------------------------------------------------------------------------
    def insert_session(self, session: MonitoringSession) -> None:
        runtime, provenance = session.runtime, session.simulation_provenance
        self._run(
            "INSERT INTO monitoring_sessions (session_id, user_id, device_id, adapter_type,"
            " source_dataset_id, source_mode, scenario_id, scenario_seed, simulation_version,"
            " state, created_at_us, started_at_us, ended_at_us, model_id, calibration_id,"
            " preprocess_id, alert_policy_id, alert_policy_binding_id, gateway_artifact_id,"
            " api_contract_version, software_system_id)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (session.session_id, session.user_id, session.device_id,
             session.device_adapter_type.value, session.source_dataset_id, session.source_mode,
             provenance.scenario_id if provenance else None,
             provenance.seed if provenance else None,
             provenance.simulation_version if provenance else None, session.state.value,
             session.created_at_us, session.started_at_us, session.ended_at_us,
             runtime.model_id, runtime.calibration_id, runtime.preprocess_id,
             runtime.alert_policy_id, runtime.alert_policy_binding_id, runtime.gateway_artifact_id,
             runtime.api_contract_version, runtime.software_system_id))

    @staticmethod
    def _session_from_row(row: sqlite3.Row) -> MonitoringSession:
        provenance = None
        if row["scenario_id"] is not None:
            provenance = SimulationProvenance(
                scenario_id=row["scenario_id"], seed=row["scenario_seed"],
                simulation_version=row["simulation_version"])
        return MonitoringSession(
            session_id=row["session_id"], user_id=row["user_id"], device_id=row["device_id"],
            device_adapter_type=row["adapter_type"], source_dataset_id=row["source_dataset_id"],
            source_mode=row["source_mode"], created_at_us=row["created_at_us"],
            started_at_us=row["started_at_us"], ended_at_us=row["ended_at_us"],
            state=row["state"], simulation_provenance=provenance,
            runtime=RuntimeIdentity(
                model_id=row["model_id"], calibration_id=row["calibration_id"],
                preprocess_id=row["preprocess_id"], alert_policy_id=row["alert_policy_id"],
                alert_policy_binding_id=row["alert_policy_binding_id"],
                gateway_artifact_id=row["gateway_artifact_id"],
                api_contract_version=row["api_contract_version"],
                software_system_id=row["software_system_id"]))

    def get_session(self, session_id: str) -> MonitoringSession | None:
        rows = self._all("SELECT * FROM monitoring_sessions WHERE session_id = ?", (session_id,))
        return self._session_from_row(rows[0]) if rows else None

    def list_sessions(self, user_id: str) -> list[MonitoringSession]:
        rows = self._all("SELECT * FROM monitoring_sessions WHERE user_id = ?"
                         " ORDER BY created_at_us DESC, session_id DESC", (user_id,))
        return [self._session_from_row(r) for r in rows]

    def update_session_state(self, session_id: str, state: SessionState, *,
                             started_at_us: int | None = None,
                             ended_at_us: int | None = None) -> None:
        """Only lifecycle state/timestamps can change; runtime identity has no update path."""
        sets, params = ["state = ?"], [state.value]
        if started_at_us is not None:
            sets.append("started_at_us = ?")
            params.append(started_at_us)
        if ended_at_us is not None:
            sets.append("ended_at_us = ?")
            params.append(ended_at_us)
        cursor = self._run(f"UPDATE monitoring_sessions SET {', '.join(sets)} WHERE session_id = ?",
                           (*params, session_id))
        if cursor.rowcount != 1:
            raise StorageIntegrityError(f"UNKNOWN_SESSION:{session_id}")

    def recover_stale_sessions(self, now_us: int) -> list[dict[str, Any]]:
        """Set every persisted nonterminal session to FAILED (never resumed); returns the audit."""
        marks = ",".join("?" for _ in NONTERMINAL_STATES)
        with self._lock, self._connection:
            rows = self._connection.execute(
                "SELECT session_id, user_id, state FROM monitoring_sessions"
                f" WHERE state IN ({marks})"
                " ORDER BY session_id", NONTERMINAL_STATES).fetchall()
            for row in rows:
                self._connection.execute(
                    "UPDATE monitoring_sessions SET state = ?, ended_at_us = ?"
                    " WHERE session_id = ?",
                    (SessionState.FAILED.value, now_us, row["session_id"]))
        return [{"session_id": r["session_id"], "user_id": r["user_id"],
                 "previous_state": r["state"], "new_state": SessionState.FAILED.value,
                 "recovered_at_us": now_us, "reason": "RESTART_RECOVERY_STALE_NONTERMINAL_SESSION"}
                for r in rows]

    # ---- session evidence --------------------------------------------------------------------
    def insert_inference_event(self, *, session_id: str, sequence_index: int, timestamp_us: int,
                               model_id: str | None, calibration_domain: str | None,
                               ecg_quality: str, monitoring_state: str,
                               raw_probability: float | None,
                               calibrated_probability: float | None, threshold: float | None,
                               latency_ms: float | None, raw_context: Mapping[str, Any] | None
                               ) -> None:
        self._run(
            "INSERT INTO inference_events (inference_id, session_id, sequence_index, timestamp_us,"
            " model_id, calibration_domain, ecg_quality, monitoring_state, raw_probability,"
            " source_domain_calibrated_probability, threshold, latency_ms, context_json)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (f"{session_id}-INF{sequence_index:06d}", session_id, sequence_index, timestamp_us,
             model_id, calibration_domain, ecg_quality, monitoring_state, raw_probability,
             calibrated_probability, threshold, latency_ms,
             None if raw_context is None else json.dumps(raw_context, sort_keys=True)))

    def insert_monitoring_state_event(self, *, session_id: str, sequence_index: int,
                                      timestamp_us: int, monitoring_state: str,
                                      previous_state: str | None, reason_code: str | None) -> None:
        self._run(
            "INSERT INTO monitoring_state_events (event_id, session_id, sequence_index,"
            " timestamp_us, monitoring_state, previous_state, reason_code)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (f"{session_id}-MST{sequence_index:06d}", session_id, sequence_index, timestamp_us,
             monitoring_state, previous_state, reason_code))

    def insert_quality_event(self, *, session_id: str, sequence_index: int, timestamp_us: int,
                             ecg_quality: str, ppg_quality: str | None) -> None:
        self._run(
            "INSERT INTO signal_quality_events (event_id, session_id, sequence_index,"
            " timestamp_us, ecg_quality, ppg_quality) VALUES (?, ?, ?, ?, ?, ?)",
            (f"{session_id}-QLT{sequence_index:06d}", session_id, sequence_index, timestamp_us,
             ecg_quality, ppg_quality))

    def insert_context_snapshot(self, *, session_id: str, sequence_index: int, timestamp_us: int,
                                context: Mapping[str, Any]) -> None:
        self._run(
            "INSERT INTO context_snapshots (snapshot_id, session_id, sequence_index, timestamp_us,"
            " hr_ecg_bpm, pr_ppg_bpm, spo2_pct, spo2_valid, context_available, ppg_quality)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (f"{session_id}-CTX{sequence_index:06d}", session_id, sequence_index, timestamp_us,
             context.get("hr_ecg_bpm"), context.get("pr_ppg_bpm"), context.get("spo2_pct"),
             int(bool(context.get("spo2_valid"))), int(bool(context.get("context_available"))),
             context.get("ppg_quality")))

    def upsert_waveform_preview(self, *, session_id: str, channel: str, source_rate_hz: int,
                                decimation_factor: int, point_count: int, start_timestamp_us: int,
                                encoding: str, data: bytes) -> None:
        self._run(
            "INSERT INTO waveform_previews (preview_id, session_id, channel, source_rate_hz,"
            " decimation_factor, point_count, start_timestamp_us, encoding, data)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (f"{session_id}-WFP-{channel}", session_id, channel, source_rate_hz, decimation_factor,
             point_count, start_timestamp_us, encoding, data))

    def rows(self, table: str, where: str = "", params: tuple[Any, ...] = ()
             ) -> list[dict[str, Any]]:
        if table not in self.table_names():
            raise StorageIntegrityError(f"UNKNOWN_TABLE:{table}")
        sql = f"SELECT * FROM {table}" + (f" WHERE {where}" if where else "")
        return [dict(r) for r in self._all(sql, params)]
