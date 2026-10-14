# ruff: noqa: E501
"""Real Atlas injection check; writes and cleans only documents tagged with this run in nhm_integration_test."""

from __future__ import annotations

import os
import tempfile
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pymongo import MongoClient

from capstone_persistence.store import CapstoneSqliteStore
from product.api.errors import ProductError
from product.hardware_telemetry import HardwareSessions, MongoTelemetry

COLLECTION = "nhm_integration_test"


def main() -> None:
    uri = os.environ["NHM_HARDWARE_MONGO_URI"]
    run = "NHM_SYNTHETIC_TEST_" + uuid.uuid4().hex
    client = MongoClient(uri, serverSelectionTimeoutMS=3000)
    col = client.health_db[COLLECTION]
    inserted = []

    def insert(*, missing_timestamp=False, **fields):
        doc = {
            "source": "NHM_SYNTHETIC_INTEGRATION_TEST",
            "test_run": run,
            "timestamp": datetime.now(UTC),
            **fields,
        }
        if missing_timestamp:
            del doc["timestamp"]
        result = col.insert_one(doc)
        inserted.append(result.inserted_id)
        return str(result.inserted_id)

    try:
        with tempfile.TemporaryDirectory() as tmp:
            store = CapstoneSqliteStore(Path(tmp) / "sessions.sqlite3")
            service = HardwareSessions(store, MongoTelemetry(uri, "health_db", COLLECTION))
            old = insert(ecg=1800, bpm=60, spo2=96)
            first = service.start("CLERK_USER_A")
            sid = first["session_id"]
            assert first["record_count"] == 0 and first["source_state"] == "WAITING FOR DATA"
            ids = [insert(ecg=1900 + i * 73, bpm=68 + i, spo2=96 + i % 3) for i in range(5)]
            invalid = insert(ecg="bad", bpm=70, spo2=97)
            missing_ecg = insert(bpm=70, spo2=97)
            missing_time = insert(ecg=2100, bpm=70, spo2=97, missing_timestamp=True)
            unavailable = insert(ecg=2300, bpm=0, spo2=0)
            delayed = insert(
                ecg=2400, bpm=77, spo2=98, timestamp=datetime.now(UTC) - timedelta(seconds=2)
            )
            live = service.poll(sid, "CLERK_USER_A")
            assert live["record_count"] == 7 and live["source_state"] == "LIVE DATA RECEIVED", live
            assert [r["id"] for r in live["readings"]] == [*ids, unavailable, delayed]
            assert old not in [r["id"] for r in live["readings"]]
            assert invalid not in [r["id"] for r in live["readings"]]
            assert missing_ecg not in [r["id"] for r in live["readings"]]
            assert missing_time not in [r["id"] for r in live["readings"]]
            assert live["readings"][-2]["bpm"] is None and live["readings"][-2]["spo2"] is None
            assert service.poll(sid, "CLERK_USER_A")["record_count"] == 7
            try:
                service.detail(sid, "CLERK_USER_B")
            except ProductError:
                pass
            else:
                raise AssertionError("cross-owner read allowed")
            time.sleep(5.2)
            assert service.detail(sid, "CLERK_USER_A")["source_state"] == "STALE DATA"
            recovered = insert(ecg=2500, bpm=78, spo2=99)
            resumed = service.poll(sid, "CLERK_USER_A", 7)
            assert resumed["record_count"] == 8 and resumed["readings"][0]["id"] == recovered
            stopped = service.stop(sid, "CLERK_USER_A")
            assert stopped["status"] == "STOPPED"
            extra = insert(ecg=2600, bpm=79, spo2=99)
            assert service.poll(sid, "CLERK_USER_A")["record_count"] == 8
            assert service.start("CLERK_USER_A")["record_count"] == 0
            service.source.close()
            restarted = HardwareSessions(store, MongoTelemetry(uri, "health_db", COLLECTION))
            assert restarted.detail(sid, "CLERK_USER_A")["record_count"] == 8
            assert restarted.detail(sid, "CLERK_USER_A")["readings"][0]["id"] == ids[0]
            restarted.source.close()
            store.close()
            print(
                "PASS real Atlas injection: high-water, 7 mapped records, invalid skip, zero unavailable, delayed time, dedupe, owner isolation, stale, recovery, stop, fresh start, restart history"
            )
            print("SESSION", sid)
            print("OLD_EXCLUDED", old, "INVALID_EXCLUDED", invalid, "STOPPED_EXCLUDED", extra)
            print("DISPLAY_MAPPING", [(ids[i], 1900 + i * 73, 68 + i) for i in range(5)])
    finally:
        if inserted:
            result = col.delete_many({"test_run": run, "_id": {"$in": inserted}})
            print("TEST_RECORDS_CLEANED", result.deleted_count, "OF", len(inserted))
        client.close()


if __name__ == "__main__":
    main()
