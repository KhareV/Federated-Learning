# ruff: noqa: E501
"""Generated demonstration collections can live in their own database (NHM_HARDWARE_DEMO_DATABASE), so real device telemetry and generated data never share one. Unset, nothing changes."""

from __future__ import annotations

import pytest

from capstone_persistence.store import CapstoneSqliteStore
from product import hardware_telemetry as ht
from product.hardware_demo_session import DEMO_COLLECTION, LONG_DEMO_COLLECTION, owner_session_id


class Cursor(list):
    def sort(self, key, direction=1):
        return Cursor(sorted(self, key=lambda d: d[key], reverse=direction < 0))

    def limit(self, n):
        return Cursor(self[:n])


class Collection:
    def __init__(self):
        self.docs: list[dict] = []

    def find(self, query=None, projection=None, sort=None):
        return Cursor(list(self.docs))

    def find_one(self, query=None, projection=None, sort=None):
        return self.docs[0] if self.docs else None

    def insert_many(self, docs, ordered=True):
        self.docs.extend(dict(d) for d in docs)


class Database(dict):
    def __missing__(self, name):
        self[name] = Collection()
        return self[name]

    def list_collection_names(self):
        return list(self)


class Client(dict):
    def __init__(self, *args, **kwargs):
        super().__init__()

    def __missing__(self, name):
        self[name] = Database()
        return self[name]

    def close(self):
        pass


@pytest.fixture
def fake_mongo(monkeypatch):
    monkeypatch.setattr(ht, "MongoClient", Client)


def test_demo_collections_go_to_the_demo_database_and_real_telemetry_stays_in_the_main_one(fake_mongo):
    source = ht.MongoTelemetry("mongodb://x", "health_db", "records_*", demo_database="nhm_demo")
    source.database["records_2026-10-17"].insert_many([{"_id": 1, "bpm": 70}])
    assert source.seed_demo_if_missing(DEMO_COLLECTION, lambda: [{"_id": 1, "bpm": 0}, {"_id": 2, "bpm": 0}]) == 2
    assert DEMO_COLLECTION in source.client["nhm_demo"] and DEMO_COLLECTION not in source.client["health_db"]      # generated data is not written next to the real telemetry
    assert source.seed_demo_if_missing(DEMO_COLLECTION, lambda: [{"_id": 9}]) == 0                                    # never overwrites
    assert [d["_id"] for d in source.read_demo_collection(DEMO_COLLECTION)] == [1, 2]
    assert source.frozen_collections(__import__("datetime").date(2026, 12, 1)) == ["records_2026-10-17"]              # History import still reads only the main database


def test_without_a_demo_database_everything_stays_where_it_was(fake_mongo):
    source = ht.MongoTelemetry("mongodb://x", "health_db", "records_*")
    assert source.demo_database_name is None and source.demo_database is source.database
    source.seed_demo_if_missing(DEMO_COLLECTION, lambda: [{"_id": 1}])
    assert DEMO_COLLECTION in source.client["health_db"]
    assert [d["_id"] for d in source.read_collection(DEMO_COLLECTION)] == [1]


def test_the_session_service_seeds_and_imports_through_the_demo_database(tmp_path, fake_mongo):
    source = ht.MongoTelemetry("mongodb://x", "health_db", "records_*", demo_database="nhm_demo")
    store = CapstoneSqliteStore(tmp_path / "p.sqlite3")
    sessions = ht.HardwareSessions(store, source)
    sessions.demo_collection = f"{DEMO_COLLECTION},{LONG_DEMO_COLLECTION}"
    assert sessions.seed_demo_collection() > 10_000
    assert {DEMO_COLLECTION, LONG_DEMO_COLLECTION} <= set(source.client["nhm_demo"]) and not ({DEMO_COLLECTION, LONG_DEMO_COLLECTION} & set(source.client["health_db"]))
    assert {r["session_id"] for r in sessions.list("user-a")} == {owner_session_id("user-a"), owner_session_id("user-a", LONG_DEMO_COLLECTION)}      # imported from the demo database
