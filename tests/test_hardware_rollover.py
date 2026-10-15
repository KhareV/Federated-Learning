"""Daily collection discovery, midnight rollover, and bounded global cursor order."""

from datetime import UTC, datetime

from bson import ObjectId

from capstone_persistence.store import CapstoneSqliteStore
from product.hardware_telemetry import MAX_BATCH, HardwareSessions, MongoTelemetry


class Cursor:
    def __init__(self, documents):
        self.documents = documents

    def sort(self, key, direction):
        assert key == "_id" and direction == 1
        self.documents.sort(key=lambda doc: doc["_id"])
        return self

    def limit(self, count):
        assert count == MAX_BATCH
        return self.documents[:count]


class Collection:
    def __init__(self):
        self.docs = []

    def find_one(self, _query, _projection, *, sort):
        assert sort == [("_id", -1)]
        return max(self.docs, key=lambda doc: doc["_id"]) if self.docs else None

    def find(self, query):
        mark = query.get("_id", {}).get("$gt")
        return Cursor([dict(doc) for doc in self.docs if mark is None or doc["_id"] > mark])


class Database(dict):
    def __getitem__(self, name):
        return self.setdefault(name, Collection())

    def list_collection_names(self):
        return list(self)


class Client(dict):
    def __init__(self):
        super().__init__()
        self.db = Database()

    def __getitem__(self, _name):
        return self.db

    def close(self):
        pass


def oid(n):
    return ObjectId(f"{n:024x}")


def doc(n, ecg):
    return {
        "_id": oid(n),
        "ecg": ecg,
        "bpm": 72,
        "spo2": 97,
        "timestamp": datetime(2026, 10, 14, 0, 0, 0, tzinfo=UTC),
    }


def test_discovery_does_not_assume_utc_and_preserves_rollover_cursor(monkeypatch, tmp_path):
    client = Client()
    # Yesterday's older document must never animate at session start.
    client.db["records_2026-10-13"].docs.append(doc(10, 1900))
    client.db["records_2026-10-12"].docs.append(doc(5, 1800))
    # Unrelated collection is never read.
    client.db["nhm_integration_test"].docs.append(doc(1000, 3000))
    monkeypatch.setattr("product.hardware_telemetry.MongoClient", lambda *_a, **_k: client)
    source = MongoTelemetry("mongodb://unused", "health_db", "records_2026-10-13")
    store = CapstoneSqliteStore(tmp_path / "sessions.sqlite3")
    sessions = HardwareSessions(store, source)
    sid = sessions.start("owner")["session_id"]
    client.db["records_2026-10-13"].docs.append(doc(11, 2001))
    first = sessions.poll(sid, "owner")
    assert [x["id"] for x in first["readings"]] == [str(oid(11))]
    assert first["readings"][0]["collection"] == "records_2026-10-13"
    # New collection appears at rollover; force the scheduled discovery interval.
    client.db["records_2026-10-14"].docs.append(doc(13, 2203))
    client.db["records_2026-10-13"].docs.append(doc(12, 2102))
    source._discovered_at = 0
    second = sessions.poll(sid, "owner", 1)
    assert [(x["id"], x["ecg"], x["collection"]) for x in second["readings"]] == [
        (str(oid(12)), 2102, "records_2026-10-13"),
        (str(oid(13)), 2203, "records_2026-10-14"),
    ]
    assert sessions.poll(sid, "owner")["record_count"] == 3
    assert sessions.stop(sid, "owner")["record_count"] == 3
    # Another session marks all current records as old, including across collections.
    next_id = sessions.start("owner")["session_id"]
    assert sessions.poll(next_id, "owner")["record_count"] == 0
    store.close()


def test_global_batch_limit_does_not_skip_older_collection_backlog(monkeypatch):
    client = Client()
    monkeypatch.setattr("product.hardware_telemetry.MongoClient", lambda *_a, **_k: client)
    source = MongoTelemetry("mongodb://unused", "health_db", "records_*")
    source._collections()
    for n in range(1, MAX_BATCH + 101):
        client.db["records_2026-10-13"].docs.append(doc(n, 2000))
    client.db["records_2026-10-14"].docs.append(doc(MAX_BATCH + 101, 2100))
    source._discovered_at = 0
    first = source.after(None)
    assert len(first) == MAX_BATCH and first[-1]["_id"] == oid(MAX_BATCH)
    second = source.after(first[-1]["_id"])
    assert len(second) == 101 and second[-1]["_id"] == oid(MAX_BATCH + 101)
    assert [d["_id"] for d in first + second] == [oid(n) for n in range(1, MAX_BATCH + 102)]


def test_same_mongodb_id_copied_across_daily_collections_counts_once(monkeypatch, tmp_path):
    client = Client()
    monkeypatch.setattr("product.hardware_telemetry.MongoClient", lambda *_a, **_k: client)
    source = MongoTelemetry("mongodb://unused", "health_db", "records_*")
    client.db["records_2026-10-13"].docs.append(doc(10, 1800))
    source._collections()
    store = CapstoneSqliteStore(tmp_path / "dedupe.sqlite3")
    sessions = HardwareSessions(store, source)
    sid = sessions.start("owner")["session_id"]
    same = doc(11, 2100)
    client.db["records_2026-10-13"].docs.append(same)
    client.db["records_2026-10-14"].docs.append(dict(same))
    source._discovered_at = 0
    result = sessions.poll(sid, "owner")
    assert result["record_count"] == 1
    assert [x["id"] for x in result["readings"]] == [str(oid(11))]
    store.close()


def test_late_lower_object_id_is_consumed_but_pre_session_documents_stay_excluded(tmp_path):
    from datetime import UTC, datetime
    from bson import ObjectId
    from capstone_persistence.store import CapstoneSqliteStore
    from product.hardware_telemetry import HardwareSessions

    now = datetime.now(UTC)

    def oid(offset_ms: int, tail: int) -> ObjectId:
        base = ObjectId.from_datetime(now)
        return ObjectId(base.binary[:4] + (int.from_bytes(base.binary[4:], "big") + offset_ms * 1000 + tail).to_bytes(8, "big"))

    class Source:
        collection_name = "records_*"

        def __init__(self):
            self.docs = []

        def high_water(self):
            return max((d["_id"] for d in self.docs), default=None)

        def after(self, mark):
            return sorted((d for d in self.docs if mark is None or d["_id"] > mark), key=lambda d: d["_id"])

    def doc(i, ecg):
        return {"_id": i, "timestamp": now, "ecg": ecg, "bpm": 70, "spo2": 97}

    store = CapstoneSqliteStore(tmp_path / "late.sqlite3")
    source = Source()
    service = HardwareSessions(store, source)
    old = oid(0, 1)
    source.docs.append(doc(old, 1111))                      # exists before the session: must never appear
    sid = service.start("u")["session_id"]
    first, late, third = oid(10, 3), oid(10, 2), oid(10, 4)   # `late` has the LOWER id but becomes visible after `first`
    source.docs.append(doc(first, 2001))
    assert service.poll(sid, "u")["record_count"] == 1
    source.docs += [doc(late, 2002), doc(third, 2003)]
    body = service.poll(sid, "u")
    assert body["record_count"] == 3, "a lower _id committed after a higher one must still be consumed"
    assert sorted(r["ecg"] for r in body["readings"]) == [2001, 2002, 2003]
    assert 1111 not in {r["ecg"] for r in body["readings"]}
    assert service.poll(sid, "u")["record_count"] == 3     # repeated polls do not duplicate
    store.close()


def test_records_written_while_nobody_polls_are_caught_up_and_session_stays_active(tmp_path):
    """Lifecycle audit: no background collector exists; the saved mark makes the next poll catch up."""
    now = datetime.now(UTC)
    start = int(now.timestamp()) - 3600

    def make(n):
        # ~17 documents per wall-clock second, like the device, so the 5 s look-back window stays bounded.
        stamp = datetime.fromtimestamp(start + n // 17, UTC)
        raw = ObjectId.from_datetime(stamp).binary[:4] + n.to_bytes(8, "big")
        return {"_id": ObjectId(raw), "timestamp": stamp, "ecg": 1000 + n, "bpm": 70, "spo2": 97}

    class Source:
        collection_name = "records_*"

        def __init__(self):
            self.docs = []
            self.reads = 0

        def high_water(self):
            return max((d["_id"] for d in self.docs), default=None)

        def after(self, mark):
            self.reads += 1
            return sorted((d for d in self.docs if mark is None or d["_id"] > mark), key=lambda d: d["_id"])[:MAX_BATCH]

    store = CapstoneSqliteStore(tmp_path / "away.sqlite3")
    source = Source()
    service = HardwareSessions(store, source)
    sid = service.start("u")["session_id"]
    source.docs += [make(n) for n in range(1, 11)]
    assert service.poll(sid, "u")["record_count"] == 10
    reads_before = source.reads
    # Monitor page absent: documents arrive, no poll happens. Nothing is read and the session stays ACTIVE.
    source.docs += [make(n) for n in range(11, 11 + MAX_BATCH + 100)]
    assert source.reads == reads_before
    assert service.detail(sid, "u")["status"] == "ACTIVE"
    assert service.detail(sid, "u")["record_count"] == 10
    # Same session re-attached on return (idempotent start) and the missed records are counted exactly once.
    assert service.start("u")["session_id"] == sid
    service.poll(sid, "u")
    body = service.poll(sid, "u")
    assert body["record_count"] == 10 + MAX_BATCH + 100
    assert len({r["id"] for r in body["readings"]}) == len(body["readings"])
    assert service.poll(sid, "u")["record_count"] == 10 + MAX_BATCH + 100
    assert service.stop(sid, "u")["status"] == "STOPPED"
    store.close()
