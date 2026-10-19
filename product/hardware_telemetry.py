# ruff: noqa: E501
"""Telemetry-only MongoDB source. No scientific ObservedRecord or inference conversion."""

from __future__ import annotations

import hashlib
import re
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from bson import ObjectId
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from product.api.errors import ProductError, ProductErrorCode

STALE_SECONDS = 5.0  # > 100 expected 50 ms messages; allows Render/Atlas pauses
MAX_BATCH = 500
# A writer with several inserts in flight can make a lower _id become visible after a higher one. The cursor therefore
# re-reads this window below its high-water mark (never below the session's start mark); duplicates are dropped by
# the (session_id, document_id) primary key.
LOOKBACK_SECONDS = 5.0
MAX_TRACE = 12000  # about 10 min at 20 Hz: one recording can feed a pretrained-V2 run (16 train + 4 holdout 10 s windows)
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


def split_sessions(samples: list[dict[str, Any]], gap_seconds: float) -> list[list[dict[str, Any]]]:
    """Split time-ordered samples into recording sessions wherever consecutive readings are more than ``gap_seconds`` apart."""
    sessions: list[list[dict[str, Any]]] = []
    previous: datetime | None = None
    for sample in sorted(samples, key=lambda x: (x["ingested_at"], x["id"])):
        stamp = datetime.fromisoformat(sample["ingested_at"])
        if previous is None or (stamp - previous).total_seconds() > gap_seconds:
            sessions.append([])
        sessions[-1].append(sample)
        previous = stamp
    return sessions


class MongoTelemetry:
    def __init__(self, uri: str, database: str, collection: str, demo_database: str | None = None):
        self.client = MongoClient(
            uri,
            serverSelectionTimeoutMS=3000,
            connectTimeoutMS=3000,
            socketTimeoutMS=3000,
            maxPoolSize=3,
            tz_aware=True,
        )
        self.database = self.client[database]
        # Generated demonstration collections may live in their own database (NHM_HARDWARE_DEMO_DATABASE) so that real device telemetry and generated data never share one; unset = the same database as before.
        self.demo_database_name = demo_database or None
        self.demo_database = self.client[demo_database] if demo_database else self.database
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

    def frozen_collections(self, before: Any) -> list[str]:
        """Daily ``records_YYYY-MM-DD`` collections dated strictly before ``before`` (a date): finished days that can no longer receive live documents."""
        names = sorted(n for n in self.database.list_collection_names() if DAILY_COLLECTION.fullmatch(n))
        return [n for n in names if n.removeprefix("records_") < before.isoformat()]

    def current_collection(self, today: Any) -> str | None:
        """The daily ``records_YYYY-MM-DD`` collection of ``today`` (a date) when it exists: the one day ``frozen_collections`` leaves out because the device may still be writing it."""
        name = f"records_{today.isoformat()}"
        return name if name in self.database.list_collection_names() else None

    def latest_id(self, name: str) -> str | None:
        doc = self.database[name].find_one({}, {"_id": 1}, sort=[("_id", -1)])
        return str(doc["_id"]) if doc else None

    def read_collection(self, name: str) -> list[dict[str, Any]]:
        """Every document of one named collection in _id order (the prerecorded demo session; live monitoring never reads it)."""
        docs = list(self.database[name].find({}).sort("_id", 1))
        for doc in docs:
            doc["_nhm_collection"] = name
        return docs

    def read_demo_collection(self, name: str) -> list[dict[str, Any]]:
        """A prerecorded demonstration collection, read from the demo database when one is configured (else the main database). Never used for live monitoring or History import."""
        docs = list(self.demo_database[name].find({}).sort("_id", 1))
        for doc in docs:
            doc["_nhm_collection"] = name
        return docs

    def seed_demo_if_missing(self, name: str, make_documents: Any) -> int:
        return self._seed(self.demo_database[name], make_documents)

    def seed_if_missing(self, name: str, make_documents: Any) -> int:
        """Create a named collection from ``make_documents()`` only when it holds nothing yet. Never drops or overwrites; returns the number of documents written."""
        return self._seed(self.database[name], make_documents)

    @staticmethod
    def _seed(collection: Any, make_documents: Any) -> int:
        if collection.find_one({}, {"_id": 1}) is not None:
            return 0
        docs = make_documents()
        for start in range(0, len(docs), 1000):
            collection.insert_many(docs[start : start + 1000], ordered=True)
        return len(docs)

    def close(self) -> None:
        self.client.close()


class HardwareSessions:
    def __init__(self, store: Any, source: MongoTelemetry):
        self.store, self.source = store, source
        self.lock = threading.RLock()
        self.history_import = False                    # past daily collections of the database appear as saved hardware sessions (see ensure_history)
        self.history_gap_seconds = 30.0
        self._history_checked: dict[str, float] = {}
        self._today_settled: dict[tuple[str, str], str] = {}   # (owner, collection) -> newest document id at the last pass that left no segment open
        self._demo_collections: tuple[str, ...] = ()  # set from NHM_HARDWARE_DEMO_COLLECTION (comma separated): prerecorded demo sessions offered to every owner
        with store._lock, store._connection:
            store._connection.execute("CREATE TABLE IF NOT EXISTS hardware_history_imports (owner TEXT NOT NULL, collection TEXT NOT NULL, sessions INTEGER NOT NULL, PRIMARY KEY(owner, collection))")
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
            session_columns = {r[1] for r in store._connection.execute("PRAGMA table_info(hardware_sessions)")}
            if "start_mark" not in session_columns:
                store._connection.execute("ALTER TABLE hardware_sessions ADD COLUMN start_mark TEXT")
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
            # Idempotent: a second Start (double click, second tab, page refresh) re-attaches to the owner's
            # ACTIVE session instead of creating an orphan that keeps its own high-water mark.
            with self.store._lock:
                existing = self.store._connection.execute(
                    "SELECT id FROM hardware_sessions WHERE owner=? AND status='ACTIVE' ORDER BY started_at DESC LIMIT 1", (owner,)
                ).fetchone()
            if existing:
                return self.detail(existing["id"], owner, 0)
            try:
                mark = self.source.high_water()
            except PyMongoError as error:
                raise ProductError(
                    ProductErrorCode.INVALID_STATE, "MongoDB unavailable at session start"
                ) from error
            sid = "HW-" + uuid.uuid4().hex
            with self.store._lock, self.store._connection:
                self.store._connection.execute(
                    "INSERT INTO hardware_sessions (id,owner,collection,started_at,status,mark,start_mark) VALUES (?,?,?,?,?,?,?)",
                    (
                        sid,
                        owner,
                        self.source.collection_name,
                        datetime.now(UTC).isoformat(),
                        "ACTIVE",
                        str(mark) if mark else None,
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
        if row["status"] == "INTERRUPTED":
            state = "SESSION INTERRUPTED (BACKEND RESTARTED)"
        elif row["status"] != "ACTIVE":
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
            else "PRESET DEMO SESSION (generated in the ESP32 sketch's document format; not a live device recording)"
            if row["collection"] in self._demo_collections
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
                docs = self.source.after(self._query_floor(row))
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
                            str(max(docs[-1]["_id"], ObjectId(row["mark"])) if row["mark"] else docs[-1]["_id"]),
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

    @staticmethod
    def _query_floor(row: dict[str, Any]) -> ObjectId | None:
        """Exclusive lower bound for the next read: the high-water mark minus the look-back, never below the start mark."""
        if not row["mark"]:
            return None
        mark = ObjectId(row["mark"])
        seconds = int(mark.generation_time.timestamp()) - int(LOOKBACK_SECONDS)
        if seconds <= 0:  # not a real wall-clock ObjectId: strict cursor, no look-back
            return mark
        floor = ObjectId.from_datetime(datetime.fromtimestamp(seconds, UTC))
        start = row.get("start_mark")
        if start:
            floor = max(floor, ObjectId(start))
        return floor

    def stop(self, sid: str, owner: str) -> dict[str, Any]:
        with self.lock:
            row = self._row(sid, owner)
            if row["status"] == "ACTIVE":
                # Final catch-up: everything already STORED in MongoDB when Stop is pressed belongs to the session even if the last 800 ms poll has not seen it yet. A source outage here
                # never blocks Stop (poll reports it and ingests nothing); anything stored after this point is excluded, exactly as before.
                self.poll(sid, owner)
                row = self._row(sid, owner)
                with self.store._lock, self.store._connection:
                    self.store._connection.execute(
                        "UPDATE hardware_sessions SET status='STOPPED', stopped_at=? WHERE id=?",
                        (datetime.now(UTC).isoformat(), sid),
                    )
            return self.detail(sid, owner, 0)

    @property
    def demo_collection(self) -> str | None:
        return ",".join(self._demo_collections) or None

    @demo_collection.setter
    def demo_collection(self, value: str | None) -> None:
        self._demo_collections = tuple(name.strip() for name in (value or "").split(",") if name.strip())

    def seed_demo_collection(self) -> int:
        """On app start: make sure every prerecorded demo collection exists in the configured database (each created only when missing; a source outage seeds nothing and is retried at the next start)."""
        from product.hardware_demo_session import SHOWCASES, documents_for

        written = 0
        for name in self._demo_collections:
            if name not in SHOWCASES:
                continue
            try:
                seeder = getattr(self.source, "seed_demo_if_missing", None) or self.source.seed_if_missing
                written += seeder(name, lambda name=name: documents_for(name))
            except PyMongoError:
                continue
        return written

    def ensure_demo(self, owner: str) -> None:
        """Import each prerecorded demo session for this owner once (idempotent). Each is a STOPPED session built from its own separate collection, named HW-SHOWCASE-*; an unreachable or empty source imports nothing."""
        from product.hardware_demo_session import SHOWCASES, owner_session_id

        for name in self._demo_collections:
            if name not in SHOWCASES:
                continue
            sid = owner_session_id(owner, name)
            with self.lock:
                with self.store._lock:
                    if self.store._connection.execute("SELECT 1 FROM hardware_sessions WHERE id=?", (sid,)).fetchone():
                        continue
                try:
                    reader = getattr(self.source, "read_demo_collection", None) or self.source.read_collection        # the demo database when the source has one; a plain source keeps its single read
                    samples = [x for doc in reader(name) if (x := clean_document(doc))]
                except PyMongoError:
                    continue
                if not samples:
                    continue
                self._store_stopped(sid, owner, name, samples)

    def _store_stopped(self, sid: str, owner: str, collection: str, samples: list[dict[str, Any]]) -> None:
        """Save a finished session built from already-stored documents: every reading counts, the newest MAX_TRACE are kept in the trace."""
        kept = samples[-MAX_TRACE:]
        with self.store._lock, self.store._connection:
            self.store._connection.execute(
                "INSERT INTO hardware_sessions (id,owner,collection,started_at,stopped_at,status,mark,last_received_at,record_count,start_mark) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (sid, owner, collection, samples[0]["ingested_at"], samples[-1]["ingested_at"], "STOPPED", None, samples[-1]["ingested_at"], len(samples), None),
            )
            offset = len(samples) - len(kept)
            for i, x in enumerate(kept, start=offset + 1):
                self.store._connection.execute(
                    "INSERT OR IGNORE INTO hardware_trace VALUES (?,?,?,?,?,?,?,?)",
                    (sid, i, x["id"], x["ingested_at"], x["ecg"], x["bpm"], x["spo2"], x["collection"] or collection),
                )

    def ensure_history(self, owner: str) -> None:
        """Past days of the database appear in History as saved hardware sessions. Each finished daily collection (``records_YYYY-MM-DD`` dated before today, UTC) is read once per owner and split into
        sessions wherever the recording pauses for more than ``history_gap_seconds``; ids are ``HW-REC-<date>-<n>-<owner tag>``. A segment whose documents are already in one of the owner's own sessions
        (a live recording made in NHM earlier: its first or last document is already stored, since a long session keeps only its newest readings) is skipped. The current day is imported segment by segment:
        only a segment whose newest reading is older than the gap is imported, because no later reading can join it, so it can never grow; the segment still being written stays out until it settles, and the
        day is not marked as imported until it is over. Source outages import nothing and are retried."""
        if not self.history_import or not hasattr(self.source, "frozen_collections"):
            return
        now = time.monotonic()
        if now - self._history_checked.get(owner, -1e9) < 60.0:
            return
        self._history_checked[owner] = now
        tag = hashlib.sha256(owner.encode()).hexdigest()[:8]
        with self.lock:
            today = datetime.now(UTC).date()
            try:
                names = self.source.frozen_collections(today)
            except PyMongoError:
                self._history_checked.pop(owner, None)
                return
            for name in names:
                with self.store._lock:
                    if self.store._connection.execute("SELECT 1 FROM hardware_history_imports WHERE owner=? AND collection=?", (owner, name)).fetchone():
                        continue
                try:
                    samples = [x for doc in self.source.read_collection(name) if (x := clean_document(doc))]
                except PyMongoError:
                    self._history_checked.pop(owner, None)
                    return
                stored, _ = self._import_segments(owner, tag, name, samples, None)
                with self.store._lock, self.store._connection:
                    self.store._connection.execute("INSERT OR REPLACE INTO hardware_history_imports VALUES (?,?,?)", (owner, name, stored))
            if not self._import_today(owner, tag, today):
                self._history_checked.pop(owner, None)

    def _import_today(self, owner: str, tag: str, today: Any) -> bool:
        """Import the finished segments of today's collection. Returns False on a source outage (retried at once)."""
        if not hasattr(self.source, "current_collection"):
            return True
        try:
            name = self.source.current_collection(today)
            if name is None:
                return True
            newest = self.source.latest_id(name)
            if newest is None or self._today_settled.get((owner, name)) == newest:
                return True                                   # nothing new since a pass that left no segment open
            samples = [x for doc in self.source.read_collection(name) if (x := clean_document(doc))]
        except PyMongoError:
            return False
        _, still_open = self._import_segments(owner, tag, name, samples, datetime.now(UTC) - timedelta(seconds=self.history_gap_seconds))
        if still_open:
            self._today_settled.pop((owner, name), None)
        else:
            self._today_settled[(owner, name)] = newest
        return True

    def _import_segments(self, owner: str, tag: str, name: str, samples: list[dict[str, Any]], settled_before: datetime | None) -> tuple[int, bool]:
        """Store each not-yet-owned segment of one daily collection as a saved session. With ``settled_before`` set, a segment whose newest reading is not older than it is still open and is left out.
        Returns (segments stored, whether an open segment was left out)."""
        stored, still_open = 0, False
        for number, segment in enumerate(split_sessions(samples, self.history_gap_seconds), start=1):
            if settled_before is not None and datetime.fromisoformat(segment[-1]["ingested_at"]) >= settled_before:
                still_open = True
                continue
            sid = f"HW-REC-{name.removeprefix('records_')}-{number:02d}-{tag}"
            with self.store._lock:
                taken = self.store._connection.execute(
                    "SELECT 1 FROM hardware_trace t JOIN hardware_sessions s ON s.id=t.session_id WHERE s.owner=? AND t.document_id IN (?, ?)", (owner, segment[0]["id"], segment[-1]["id"])
                ).fetchone() or self.store._connection.execute("SELECT 1 FROM hardware_sessions WHERE id=?", (sid,)).fetchone()
            if taken:
                continue
            self._store_stopped(sid, owner, name, segment)
            stored += 1
        return stored, still_open

    def list(self, owner: str) -> list[dict[str, Any]]:
        self.ensure_history(owner)
        self.ensure_demo(owner)
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
