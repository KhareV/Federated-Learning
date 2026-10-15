# ruff: noqa: E501
"""Telemetry-only MongoDB source. No scientific ObservedRecord or inference conversion."""

from __future__ import annotations

import re
import threading
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from product.api.errors import ProductError, ProductErrorCode

STALE_SECONDS = 5.0  # > 100 expected 50 ms messages; allows Render/Atlas pauses
MAX_BATCH = 500
MAX_TRACE = 2000
DISCOVERY_INTERVAL_SECONDS = 2.0
DAILY_COLLECTION = re.compile(r"records_\d{4}-\d{2}-\d{2}$")


def clean_document(doc: dict[str, Any]) -> dict[str, Any] | None:
    """Reject malformed ECG; unavailable or implausible vital values remain null."""
    value = doc.get("ecg")
    stamp = doc.get("timestamp", doc.get("ingestedAt"))
    if (
        type(value) not in (int, float)
        or not 0 <= value <= 4095
        or (type(value) is float and not value.is_integer())
        or not isinstance(stamp, datetime)
    ):
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)  # PyMongo returns naive UTC by default

    def vital(name: str, low: int, high: int) -> int | None:
        v = doc.get(name)
        return int(v) if type(v) is int and low <= v <= high else None

    return {
        "id": str(doc["_id"]),
        "ingested_at": stamp.isoformat(),
        "ecg": int(value),
        "bpm": vital("bpm", 20, 255),
        "spo2": vital("spo2", 1, 100),
        "collection": doc.get("_nhm_collection"),
    }


class MongoTelemetry:
    def __init__(self, uri: str, database: str, collection: str):
        self.client = MongoClient(
            uri,
            serverSelectionTimeoutMS=3000,
            connectTimeoutMS=3000,
            socketTimeoutMS=3000,
            maxPoolSize=3,
            tz_aware=True,
        )
        self.database = self.client[database]
        self.daily = collection == "records_*" or bool(DAILY_COLLECTION.fullmatch(collection))
        self.collection_name = "records_*" if self.daily else collection
        self._names: list[str] = []
        self._discovered_at = 0.0

    def _collections(self) -> list[str]:
        if not self.daily:
            return [self.collection_name]
        now = time.monotonic()
        if not self._names or now - self._discovered_at >= DISCOVERY_INTERVAL_SECONDS:
            # Names are sorted by their own date convention. No host timezone is assumed.
            self._names = sorted(
                n for n in self.database.list_collection_names() if DAILY_COLLECTION.fullmatch(n)
            )[-2:]
            self._discovered_at = now
        return self._names

    def high_water(self) -> ObjectId | None:
        marks = [
            doc["_id"]
            for name in self._collections()
            if (doc := self.database[name].find_one({}, {"_id": 1}, sort=[("_id", -1)]))
        ]
        return max(marks, default=None)

    def after(self, mark: ObjectId | None) -> list[dict[str, Any]]:
        query = {"_id": {"$gt": mark}} if mark else {}
        docs: list[dict[str, Any]] = []
        for name in self._collections():
            for doc in self.database[name].find(query).sort("_id", 1).limit(MAX_BATCH):
                doc["_nhm_collection"] = name
                docs.append(doc)
        return sorted(docs, key=lambda doc: doc["_id"])[:MAX_BATCH]

    def close(self) -> None:
        self.client.close()


class HardwareSessions:
    def __init__(self, store: Any, source: MongoTelemetry):
        self.store, self.source = store, source
        self.lock = threading.RLock()
        with store._lock, store._connection:
            store._connection.execute("""CREATE TABLE IF NOT EXISTS hardware_sessions (
                id TEXT PRIMARY KEY, owner TEXT NOT NULL, collection TEXT NOT NULL,
                started_at TEXT NOT NULL, stopped_at TEXT, status TEXT NOT NULL,
                mark TEXT, last_received_at TEXT, record_count INTEGER NOT NULL DEFAULT 0)""")
            store._connection.execute("""CREATE TABLE IF NOT EXISTS hardware_trace (
                session_id TEXT NOT NULL, ordinal INTEGER NOT NULL, document_id TEXT NOT NULL,
                ingested_at TEXT NOT NULL, ecg INTEGER NOT NULL, bpm INTEGER, spo2 INTEGER,
                collection TEXT,
                PRIMARY KEY(session_id, document_id))""")
            columns = {r[1] for r in store._connection.execute("PRAGMA table_info(hardware_trace)")}
            if "collection" not in columns:
                store._connection.execute("ALTER TABLE hardware_trace ADD COLUMN collection TEXT")
            store._connection.execute(
                "UPDATE hardware_sessions SET status='INTERRUPTED', stopped_at=? WHERE status='ACTIVE'",
                (datetime.now(UTC).isoformat(),),
            )

    def _row(self, session_id: str, owner: str) -> dict[str, Any]:
        with self.store._lock:
            row = self.store._connection.execute(
                "SELECT * FROM hardware_sessions WHERE id=?", (session_id,)
            ).fetchone()
        if row is None:
            raise ProductError(ProductErrorCode.NOT_FOUND, "unknown hardware session")
        if row["owner"] != owner:
            raise ProductError(ProductErrorCode.FORBIDDEN, "session belongs to another user")
        return dict(row)

    def start(self, owner: str) -> dict[str, Any]:
        with self.lock:
            try:
                mark = self.source.high_water()
            except PyMongoError as error:
                raise ProductError(
                    ProductErrorCode.INVALID_STATE, "MongoDB unavailable at session start"
                ) from error
            sid = "HW-" + uuid.uuid4().hex
            with self.store._lock, self.store._connection:
                self.store._connection.execute(
                    "INSERT INTO hardware_sessions (id,owner,collection,started_at,status,mark) VALUES (?,?,?,?,?,?)",
                    (
                        sid,
                        owner,
                        self.source.collection_name,
                        datetime.now(UTC).isoformat(),
                        "ACTIVE",
                        str(mark) if mark else None,
                    ),
                )
            return self.detail(sid, owner, 0)

    def detail(self, sid: str, owner: str, after: int = 0) -> dict[str, Any]:
        row = self._row(sid, owner)
        with self.store._lock:
            samples = [
                dict(x)
                for x in self.store._connection.execute(
                    "SELECT ordinal, document_id AS id, ingested_at, ecg, bpm, spo2, collection FROM hardware_trace WHERE session_id=? AND ordinal>? ORDER BY ordinal LIMIT ?",
                    (sid, after, MAX_TRACE),
                ).fetchall()
            ]
        now = datetime.now(UTC)
        if row["status"] != "ACTIVE":
            state = "SESSION STOPPED"
        elif (
            row["last_received_at"]
            and (now - datetime.fromisoformat(row["last_received_at"])).total_seconds()
            <= STALE_SECONDS
        ):
            state = "LIVE DATA RECEIVED"
        elif row["record_count"]:
            state = "STALE DATA"
        else:
            state = "WAITING FOR DATA"
        return {
            "version": "HARDWARE_TELEMETRY_V1",
            "session_id": sid,
            "source": "SYNTHETIC TEST SOURCE"
            if row["collection"] == "nhm_integration_test"
            else "ESP32 via Render/MongoDB (unverified device provenance)",
            "collection": row["collection"],
            "started_at": row["started_at"],
            "stopped_at": row["stopped_at"],
            "status": row["status"],
            "source_state": state,
            "record_count": row["record_count"],
            "last_received_at": row["last_received_at"],
            "readings": samples,
            "trace_limit": MAX_TRACE,
            "stale_threshold_seconds": STALE_SECONDS,
        }

    def poll(self, sid: str, owner: str, after: int = 0) -> dict[str, Any]:
        with self.lock:
            row = self._row(sid, owner)
            if row["status"] != "ACTIVE":
                return self.detail(sid, owner, after)
            try:
                docs = self.source.after(ObjectId(row["mark"]) if row["mark"] else None)
            except PyMongoError:
                result = self.detail(sid, owner, after)
                result["source_state"] = "MONGODB UNAVAILABLE"
                return result
            # Advance over invalid rows too; otherwise one malformed document can be replayed forever.
            with self.store._lock, self.store._connection:
                count = row["record_count"]
                for doc in docs:
                    sample = clean_document(doc)
                    if sample:
                        inserted = self.store._connection.execute(
                            "INSERT OR IGNORE INTO hardware_trace VALUES (?,?,?,?,?,?,?,?)",
                            (
                                sid,
                                count + 1,
                                sample["id"],
                                sample["ingested_at"],
                                sample["ecg"],
                                sample["bpm"],
                                sample["spo2"],
                                sample["collection"] or self.source.collection_name,
                            ),
                        )
                        if inserted.rowcount:
                            count += 1
                if docs:
                    self.store._connection.execute(
                        "UPDATE hardware_sessions SET mark=?, record_count=?, last_received_at=? WHERE id=?",
                        (
                            str(docs[-1]["_id"]),
                            count,
                            datetime.now(UTC).isoformat()
                            if count > row["record_count"]
                            else row["last_received_at"],
                            sid,
                        ),
                    )
                    self.store._connection.execute(
                        "DELETE FROM hardware_trace WHERE session_id=? AND ordinal<=?",
                        (sid, max(0, count - MAX_TRACE)),
                    )
            return self.detail(sid, owner, after)

    def stop(self, sid: str, owner: str) -> dict[str, Any]:
        with self.lock:
            row = self._row(sid, owner)
            if row["status"] == "ACTIVE":
                with self.store._lock, self.store._connection:
                    self.store._connection.execute(
                        "UPDATE hardware_sessions SET status='STOPPED', stopped_at=? WHERE id=?",
                        (datetime.now(UTC).isoformat(), sid),
                    )
            return self.detail(sid, owner, 0)

    def list(self, owner: str) -> list[dict[str, Any]]:
        with self.store._lock:
            ids = [
                r[0]
                for r in self.store._connection.execute(
                    "SELECT id FROM hardware_sessions WHERE owner=? ORDER BY started_at DESC",
                    (owner,),
                )
            ]
        return [self.detail(sid, owner, 0) | {"readings": [], "summary": self._summary(sid)} for sid in ids]

    def _summary(self, sid: str) -> dict[str, Any]:
        """Descriptive aggregates of the stored (bounded) trace; no inference, no validity claim."""
        with self.store._lock:
            row = self.store._connection.execute(
                "SELECT COUNT(*) n, MIN(ingested_at) first, MAX(ingested_at) last, MIN(ecg) ecg_min, MAX(ecg) ecg_max,"
                " AVG(bpm) bpm_mean, COUNT(bpm) bpm_n, AVG(spo2) spo2_mean, COUNT(spo2) spo2_n"
                " FROM hardware_trace WHERE session_id=?",
                (sid,),
            ).fetchone()
        n = row["n"]
        span = None
        if n > 1:
            span = (datetime.fromisoformat(row["last"]) - datetime.fromisoformat(row["first"])).total_seconds()
        return {
            "stored_readings": n,
            "first_reading_at": row["first"],
            "last_reading_at": row["last"],
            "span_seconds": span,
            "arrival_hz": (n - 1) / span if span and span > 0 else None,
            "ecg_min": row["ecg_min"],
            "ecg_max": row["ecg_max"],
            "bpm_mean": round(row["bpm_mean"], 1) if row["bpm_n"] else None,
            "spo2_mean": round(row["spo2_mean"], 1) if row["spo2_n"] else None,
        }
