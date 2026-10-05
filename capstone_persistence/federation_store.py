# ruff: noqa: E501
"""CAPSTONE_FEDERATION_STORE_V1 -- the federation plane's rows in the SAME SQLite file as the product.

Populates ONLY the five frozen policy tables: federation_runs, federation_rounds, fl_client_statuses,
candidate_models, governance_decisions. No schema change, no per-event table, and no raw data, labels,
truth, tensors or candidate bytes ever enter SQL (candidate weights are files; the row holds a digest).
It opens its OWN connection to the database file (``foreign_keys = ON``, WAL) so federation writes never
share a cursor with the monitoring store.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from capstone_persistence.store import StorageIntegrityError, utc_micros

STORE_ID = "CAPSTONE_FEDERATION_STORE_V1"
TABLES = ("federation_runs", "federation_rounds", "fl_client_statuses", "candidate_models",
          "governance_decisions")


class FederationStore:
    def __init__(self, path: str | Path, *, clock: Callable[[], int] = utc_micros) -> None:
        if str(path) == ":memory:":
            raise StorageIntegrityError("FEDERATION_STORE_REQUIRES_A_DATABASE_FILE")
        self.path, self.clock = str(path), clock
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.path, check_same_thread=False, timeout=30)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA journal_mode = WAL")
        missing = [t for t in TABLES if not self._all(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,))]
        if missing:  # the product store (CAP-004) owns schema creation
            raise StorageIntegrityError(f"FEDERATION_TABLES_MISSING:{missing}")

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def _run(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        with self._lock, self._connection:
            return self._connection.execute(sql, params)

    def _all(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._connection.execute(sql, params).fetchall()

    def counts(self) -> dict[str, int]:
        return {t: self._all(f"SELECT count(*) AS n FROM {t}")[0]["n"] for t in TABLES}

    # ---- runs ------------------------------------------------------------------------------------
    def insert_run(self, *, run_id: str, user_id: str, run_type: str, base_model_id: str,
                   protocol_id: str, algorithm: str, secagg_mode: str, planned_rounds: int) -> None:
        self._run(
            "INSERT INTO federation_runs (run_id, user_id, run_type, base_model_id, "
            "federation_protocol_id, algorithm, secagg_mode, planned_rounds, current_round, status,"
            " started_at_us, completed_at_us, engineering_only, candidate_ids_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 'CREATED', NULL, NULL, 1, '[]')",
            (run_id, user_id, run_type, base_model_id, protocol_id, algorithm, secagg_mode,
             planned_rounds))

    def update_run(self, run_id: str, *, status: str | None = None, current_round: int | None = None,
                   started_at_us: int | None = None, completed_at_us: int | None = None,
                   candidate_ids: list[str] | None = None) -> None:
        sets, params = [], []
        for column, value in (("status", status), ("current_round", current_round),
                              ("started_at_us", started_at_us),
                              ("completed_at_us", completed_at_us)):
            if value is not None:
                sets.append(f"{column} = ?")
                params.append(value)
        if candidate_ids is not None:
            sets.append("candidate_ids_json = ?")
            params.append(json.dumps(candidate_ids))
        if sets:
            self._run(f"UPDATE federation_runs SET {', '.join(sets)} WHERE run_id = ?",
                      (*params, run_id))

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        rows = self._all("SELECT * FROM federation_runs WHERE run_id = ?", (run_id,))
        return dict(rows[0]) if rows else None

    def list_runs(self, user_id: str) -> list[dict[str, Any]]:
        return [dict(r) for r in self._all(
            "SELECT * FROM federation_runs WHERE user_id = ? ORDER BY rowid", (user_id,))]

    def runs_with_status(self, status: str, run_type: str | None = None) -> list[dict[str, Any]]:
        if run_type is None:
            rows = self._all("SELECT * FROM federation_runs WHERE status = ? ORDER BY rowid",
                             (status,))
        else:
            rows = self._all("SELECT * FROM federation_runs WHERE status = ? AND run_type = ? "
                             "ORDER BY rowid", (status, run_type))
        return [dict(r) for r in rows]

    def latest_completed_live_run(self, user_id: str, algorithm: str, secagg_mode: str,
                                  planned_rounds: int) -> dict[str, Any] | None:
        rows = self._all(
            "SELECT * FROM federation_runs WHERE user_id = ? AND run_type = 'LIVE_RUN' AND "
            "status = 'COMPLETED' AND algorithm = ? AND secagg_mode = ? AND planned_rounds = ? "
            "ORDER BY completed_at_us DESC, rowid DESC LIMIT 1",
            (user_id, algorithm, secagg_mode, planned_rounds))
        return dict(rows[0]) if rows else None

    # ---- rounds / client statuses ----------------------------------------------------------------
    def upsert_round(self, *, run_id: str, round_id: int, state: str, base_state_digest: str,
                     algorithm: str, accepted_update_count: int, candidate_id: str | None) -> None:
        pk = f"{run_id}-R{round_id}"
        self._run(
            "INSERT INTO federation_rounds (round_pk, run_id, round_id, state, base_state_digest, "
            "algorithm, accepted_update_count, candidate_id, updated_at_us) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(round_pk) DO UPDATE SET "
            "state = excluded.state, accepted_update_count = excluded.accepted_update_count, "
            "candidate_id = excluded.candidate_id, updated_at_us = excluded.updated_at_us",
            (pk, run_id, round_id, state, base_state_digest, algorithm, accepted_update_count,
             candidate_id, self.clock()))

    def list_rounds(self, run_id: str) -> list[dict[str, Any]]:
        return [dict(r) for r in self._all(
            "SELECT * FROM federation_rounds WHERE run_id = ? ORDER BY round_id", (run_id,))]

    def upsert_client_status(self, *, run_id: str, client_id: str, round_id: int,
                             client_state: str, local_example_count: int,
                             update_digest: str | None, reason_code: str | None) -> None:
        pk = f"{run_id}-R{round_id}-{client_id}"
        self._run(
            "INSERT INTO fl_client_statuses (status_pk, run_id, client_id, round_id, client_state, "
            "local_example_count, update_digest, reason_code, updated_at_us) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(status_pk) DO UPDATE SET "
            "client_state = excluded.client_state, local_example_count = excluded.local_example_count,"
            " update_digest = COALESCE(excluded.update_digest, fl_client_statuses.update_digest), "
            "reason_code = excluded.reason_code, updated_at_us = excluded.updated_at_us",
            (pk, run_id, client_id, round_id, client_state, local_example_count, update_digest,
             reason_code, self.clock()))

    def list_client_statuses(self, run_id: str, round_id: int | None = None) -> list[dict[str, Any]]:
        if round_id is None:
            rows = self._all("SELECT * FROM fl_client_statuses WHERE run_id = ? "
                             "ORDER BY round_id, client_id", (run_id,))
        else:
            rows = self._all("SELECT * FROM fl_client_statuses WHERE run_id = ? AND round_id = ? "
                             "ORDER BY client_id", (run_id, round_id))
        return [dict(r) for r in rows]

    def delete_after_round(self, run_id: str, last_committed_round: int) -> None:
        """Recovery only: discard the partial, uncommitted rounds of a resumed run."""
        self._run("DELETE FROM fl_client_statuses WHERE run_id = ? AND round_id > ?",
                  (run_id, last_committed_round))
        self._run("DELETE FROM federation_rounds WHERE run_id = ? AND round_id > ?",
                  (run_id, last_committed_round))

    # ---- candidates / governance -----------------------------------------------------------------
    def insert_candidate(self, *, candidate_id: str, parent_model_id: str, federation_run_id: str,
                         round_id: int, algorithm: str, client_count: int, state_digest: str,
                         validation_status: str, governance_status: str, sandbox_status: str,
                         claim_boundary: str) -> None:
        self._run(
            "INSERT INTO candidate_models (candidate_id, parent_model_id, federation_run_id, round,"
            " algorithm, client_count, created_at_us, state_digest, validation_status, "
            "governance_status, sandbox_status, production_deployed, claim_boundary) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)",
            (candidate_id, parent_model_id, federation_run_id, round_id, algorithm, client_count,
             self.clock(), state_digest, validation_status, governance_status, sandbox_status,
             claim_boundary))

    def update_candidate(self, candidate_id: str, *, validation_status: str, governance_status: str,
                         sandbox_status: str) -> None:
        self._run("UPDATE candidate_models SET validation_status = ?, governance_status = ?, "
                  "sandbox_status = ? WHERE candidate_id = ?",
                  (validation_status, governance_status, sandbox_status, candidate_id))

    def get_candidate(self, candidate_id: str) -> dict[str, Any] | None:
        rows = self._all("SELECT * FROM candidate_models WHERE candidate_id = ?", (candidate_id,))
        return dict(rows[0]) if rows else None

    def list_candidates(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self._all("SELECT * FROM candidate_models ORDER BY candidate_id")]

    def candidate_ids_for_run(self, run_id: str) -> list[str]:
        return [r["candidate_id"] for r in self._all(
            "SELECT candidate_id FROM candidate_models WHERE federation_run_id = ? "
            "ORDER BY candidate_id", (run_id,))]

    def max_candidate_number(self) -> int:
        rows = self._all("SELECT candidate_id FROM candidate_models")
        return max((int(r["candidate_id"].rsplit("_", 1)[1]) for r in rows), default=0)

    def insert_decision(self, *, decision_id: str, candidate_id: str, decision: str,
                        checks: list[dict[str, Any]]) -> None:
        self._run(
            "INSERT INTO governance_decisions (decision_id, candidate_id, decision, checks_json, "
            "decided_at_us, scientific_promotion, production_deployed) VALUES (?, ?, ?, ?, ?, 0, 0)",
            (decision_id, candidate_id, decision, json.dumps(checks, sort_keys=True), self.clock()))

    def list_decisions(self, candidate_id: str | None = None) -> list[dict[str, Any]]:
        if candidate_id is None:
            rows = self._all("SELECT * FROM governance_decisions ORDER BY rowid")
        else:
            rows = self._all("SELECT * FROM governance_decisions WHERE candidate_id = ? "
                             "ORDER BY rowid", (candidate_id,))
        return [dict(r) for r in rows]
