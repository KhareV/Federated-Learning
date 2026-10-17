"""The prerecorded DEMO hardware session: sketch-format documents in their own collection, imported as a STOPPED session, usable by replay and by both federated paths."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from capstone_persistence.store import CapstoneSqliteStore  # noqa: E402
from product.hardware_demo_session import DEMO_COLLECTION, DEMO_SECONDS, generate_documents, owner_session_id  # noqa: E402
from product.hardware_telemetry import MAX_TRACE, HardwareSessions, clean_document  # noqa: E402
from product.observatory import hardware_trace  # noqa: E402
from studio import hardware_v2  # noqa: E402
from studio.hardware_demo import HardwareDemoService  # noqa: E402


@pytest.fixture(scope="module")
def docs():
    return generate_documents()


class Source:
    collection_name = "records_*"

    def __init__(self, docs):
        self.docs, self.reads = docs, 0

    def read_collection(self, name):
        self.reads += 1
        assert name == DEMO_COLLECTION
        return [d | {"_nhm_collection": name} for d in self.docs]


def service(tmp_path, docs):
    store = CapstoneSqliteStore(tmp_path / "p.sqlite3")
    svc = HardwareSessions(store, Source(docs))
    svc.demo_collection = DEMO_COLLECTION
    return store, svc


def test_documents_have_exactly_the_sketch_server_shape_and_are_deterministic(docs):
    assert docs == generate_documents()
    assert all(set(d) == {"_id", "bpm", "spo2", "ecg", "timestamp"} for d in docs)
    assert all(0 <= d["ecg"] <= 4095 and clean_document(d) is not None for d in docs)
    assert [d["_id"] for d in docs] == sorted(d["_id"] for d in docs)
    assert not re.fullmatch(r"records_\d{4}-\d{2}-\d{2}", DEMO_COLLECTION)          # live monitoring can never ingest it
    rate = (len(docs) - 1) / (docs[-1]["timestamp"] - docs[0]["timestamp"]).total_seconds()
    assert 14 < rate < 20 and len(docs) <= MAX_TRACE
    settle, rest = [d for d in docs if d["bpm"] == 0 and d["spo2"] == 0 and d["ecg"] == 2048], docs[400:]
    assert 20 < len(settle) < 120 and all(d["bpm"] >= 72 for d in rest[:50])
    gaps = [(b["timestamp"] - a["timestamp"]).total_seconds() for a, b in zip(docs, docs[1:], strict=False)]
    assert max(gaps) < 1.0 and DEMO_SECONDS >= 300


def test_import_is_a_stopped_demo_session_once_per_owner_and_private(tmp_path, docs):
    store, svc = service(tmp_path, docs)
    listed = svc.list("user-a")
    assert [s["session_id"] for s in listed] == [owner_session_id("user-a")] and listed[0]["session_id"].startswith("HW-SHOWCASE-")
    assert listed[0]["source_state"] == "SESSION STOPPED" and "PRESET DEMO SESSION" in listed[0]["source"] and listed[0]["collection"] == DEMO_COLLECTION and listed[0]["record_count"] == len(docs)
    svc.list("user-a")
    assert svc.source.reads == 1                                                    # idempotent
    assert [s["session_id"] for s in svc.list("user-b")] == [owner_session_id("user-b")]
    assert owner_session_id("user-a") != owner_session_id("user-b")
    with store._lock:
        assert store._connection.execute("SELECT COUNT(*) FROM hardware_trace WHERE session_id=?", (owner_session_id("user-a"),)).fetchone()[0] == len(docs)


def test_without_the_setting_nothing_is_imported(tmp_path, docs):
    _, svc = service(tmp_path, docs)
    svc.demo_collection = None
    assert svc.list("user-a") == [] and svc.source.reads == 0


def test_the_one_demo_session_feeds_replay_and_both_federated_paths(tmp_path, docs):
    store, svc = service(tmp_path, docs)
    sid = svc.list("user-a")[0]["session_id"]
    demo = HardwareDemoService(store, tmp_path / "runs")
    assert next(s for s in demo.eligible_sessions("user-a") if s["id"] == sid)["eligible"] is True
    readings = demo._records("user-a", [sid])
    listing = hardware_trace.window_list(sid, readings)
    assert len(listing["windows"]) >= 25
    trace = hardware_trace.window_trace(sid, readings, 3)
    assert trace.model_dump()
    info = hardware_v2.preview(readings, [sid])
    assert info["eligible"] is True and info["train_windows"] >= 16 and info["holdout_windows"] >= 4
    tabular = demo.prepare("user-a", session_ids=[sid], rounds=3, algorithm="FEDAVG", secagg_mode="PLAIN", label_seed=1)
    assert tabular["session_ids"] == [sid]
    v2 = demo.prepare("user-a", session_ids=[sid], rounds=3, algorithm="FEDAVG", secagg_mode="PLAIN", label_seed=1, initialisation="MODEL_V2_FINAL")
    assert v2["engine"] == "HARDWARE_V2" and v2["dataset"]["training_windows"] >= 16


def test_app_init_seeds_the_collection_only_when_it_is_missing(tmp_path, docs):
    class Seeding(Source):
        stored: list = []

        def seed_if_missing(self, name, make_documents):
            if self.stored:
                return 0
            self.stored = make_documents()
            return len(self.stored)

    _, svc = service(tmp_path, docs)
    svc.source = Seeding(docs)
    assert svc.seed_demo_collection() == len(docs) and svc.seed_demo_collection() == 0
    svc.demo_collection = None
    assert svc.seed_demo_collection() == 0


# ---- past days of the database as saved hardware sessions -------------------------------------------------------------------------------------------------------------------------

from datetime import UTC, date, datetime, timedelta  # noqa: E402

from bson import ObjectId  # noqa: E402

from product.hardware_telemetry import split_sessions  # noqa: E402


def _day(day: str, bursts: list[tuple[float, int]]) -> list[dict]:
    """Documents of one day: each burst is (start second of day, number of ~17 Hz readings)."""
    base = datetime.fromisoformat(day + "T09:00:00+00:00")
    docs, n = [], 0
    for start, count in bursts:
        for i in range(count):
            stamp = base + timedelta(seconds=start + i * 0.0585)
            n += 1
            docs.append({"_id": ObjectId(int(stamp.timestamp()).to_bytes(4, "big") + n.to_bytes(8, "big")), "bpm": 74, "spo2": 97, "ecg": 1900 + i % 50, "timestamp": stamp})
    return docs


class DaySource:
    collection_name = "records_*"

    def __init__(self, days: dict[str, list[dict]]):
        self.days, self.reads = days, []

    def frozen_collections(self, before: date) -> list[str]:
        return [n for n in sorted(self.days) if n.removeprefix("records_") < before.isoformat()]

    def read_collection(self, name):
        self.reads.append(name)
        return [d | {"_nhm_collection": name} for d in self.days[name]]


def history_service(tmp_path, days):
    store = CapstoneSqliteStore(tmp_path / "h.sqlite3")
    svc = HardwareSessions(store, DaySource(days))
    svc.history_import = True
    return store, svc


def test_split_sessions_cuts_where_the_recording_pauses():
    docs = [x for d in _day("2026-09-14", [(0, 300), (200, 500), (900, 100)]) if (x := clean_document(d))]
    parts = split_sessions(docs, 30.0)
    assert [len(p) for p in parts] == [300, 500, 100] and split_sessions(docs, 1e6) == [sorted(docs, key=lambda x: (x["ingested_at"], x["id"]))]


def test_finished_days_appear_as_saved_hardware_sessions_and_today_never_does(tmp_path):
    today = datetime.now(UTC).date().isoformat()
    days = {"records_2026-09-14": _day("2026-09-14", [(0, 400), (300, 800)]), "records_2026-09-15": _day("2026-09-15", [(0, 200)]), f"records_{today}": _day(today, [(0, 300)])}
    _, svc = history_service(tmp_path, days)
    listed = svc.list("user-a")
    ids = sorted(s["session_id"] for s in listed)
    assert len(ids) == 3 and all(i.startswith("HW-REC-2026-09-1") for i in ids) and not any(today in i for i in ids)
    assert {s["collection"] for s in listed} == {"records_2026-09-14", "records_2026-09-15"} and all(s["source_state"] == "SESSION STOPPED" for s in listed)
    assert sorted(s["record_count"] for s in listed) == [200, 400, 800]
    assert "ESP32 via Render/MongoDB" in listed[0]["source"]                      # genuine telemetry labelling: recorded days are real device data
    svc._history_checked.clear()
    svc.list("user-a")
    assert svc.source.reads.count("records_2026-09-14") == 1                       # a frozen day is read once per owner
    assert len(svc.list("user-b")) == 3 and {s["session_id"] for s in svc.list("user-b")}.isdisjoint(ids)


def test_a_day_already_recorded_live_by_the_owner_is_not_duplicated(tmp_path):
    days = {"records_2026-09-14": _day("2026-09-14", [(0, 400)])}
    store, svc = history_service(tmp_path, days)
    first = [x for d in days["records_2026-09-14"] if (x := clean_document(d))]
    svc._store_stopped("HW-live-earlier", "user-a", "records_*", first)
    assert [s["session_id"] for s in svc.list("user-a")] == ["HW-live-earlier"]


def test_history_import_is_off_unless_enabled(tmp_path):
    _, svc = history_service(tmp_path, {"records_2026-09-14": _day("2026-09-14", [(0, 400)])})
    svc.history_import = False
    assert svc.list("user-a") == []


def test_a_live_session_that_kept_only_the_newest_readings_still_prevents_a_duplicate(tmp_path):
    days = {"records_2026-09-14": _day("2026-09-14", [(0, 400)])}
    _, svc = history_service(tmp_path, days)
    samples = [x for d in days["records_2026-09-14"] if (x := clean_document(d))]
    svc._store_stopped("HW-live-earlier", "user-a", "records_*", samples[-50:])       # the first documents of the day were pruned from the live trace
    assert [s["session_id"] for s in svc.list("user-a")] == ["HW-live-earlier"]
