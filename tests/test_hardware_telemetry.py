"""Telemetry-only contract and authenticated REST lifecycle with a deterministic Mongo stub."""

from datetime import UTC, datetime

from bson import ObjectId
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from pymongo.errors import ServerSelectionTimeoutError

from capstone_persistence.store import CapstoneSqliteStore
from product.api.errors import ProductError
from product.auth.base import AuthIdentity, AuthProviderType
from api.hardware_telemetry_routes import install_hardware_routes
from product.hardware_telemetry import clean_document


def test_validation_keeps_low_rate_telemetry_out_of_scientific_contract():
    oid = ObjectId()
    stamp = datetime.now(UTC)
    assert (
        clean_document({"_id": oid, "timestamp": stamp, "ecg": 2048, "bpm": 0, "spo2": 0})["spo2"]
        is None
    )
    assert clean_document({"_id": oid, "timestamp": stamp, "ecg": "2048"}) is None
    assert clean_document({"_id": oid, "timestamp": stamp, "ecg": 4096}) is None
    assert clean_document({"_id": oid, "timestamp": stamp, "ecg": 2048.7}) is None
    assert clean_document({"_id": oid, "timestamp": stamp, "ecg": 2048.0})["ecg"] == 2048
    assert clean_document({"_id": oid, "ecg": 2048}) is None


def test_owner_scoped_rest_lifecycle(tmp_path):
    app = FastAPI()
    store = CapstoneSqliteStore(tmp_path / "hardware.sqlite3")
    user = "user_a"

    async def identity(_request):
        if user == "none":
            return None
        return AuthIdentity(
            user_id=user,
            auth_provider=AuthProviderType.CLERK,
            auth_session_id="test_session",
            demo_mode=False,
        )

    @app.exception_handler(ProductError)
    async def error(_request: Request, exc: ProductError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    install_hardware_routes(
        app,
        store,
        identity,
        {
            "NHM_HARDWARE_MONGO_ENABLED": "true",
            "NHM_HARDWARE_MONGO_URI": "mongodb://127.0.0.1:27017",
            "NHM_HARDWARE_MONGO_DATABASE": "health_db",
            "NHM_HARDWARE_MONGO_COLLECTION": "nhm_integration_test",
        },
    )

    class Source:
        collection_name = "nhm_integration_test"

        def __init__(self):
            self.docs = []
            self.unavailable = False

        def high_water(self):
            return self.docs[-1]["_id"] if self.docs else None

        def after(self, mark):
            if self.unavailable:
                raise ServerSelectionTimeoutError("test outage")
            return [d for d in self.docs if mark is None or d["_id"] > mark]

    source = Source()
    app.state.hardware_sessions.source = source
    client = TestClient(app)
    assert client.get("/product/v1/hardware/sessions").status_code == 200
    first = client.post("/product/v1/hardware/sessions").json()
    sid = first["session_id"]
    assert first["record_count"] == 0
    source.docs.append(
        {"_id": ObjectId(), "timestamp": datetime.now(UTC), "ecg": 2001, "bpm": 76, "spo2": 97}
    )
    received = client.get(f"/product/v1/hardware/sessions/{sid}/poll").json()
    assert received["record_count"] == 1 and received["readings"][0]["ecg"] == 2001
    assert client.get(f"/product/v1/hardware/sessions/{sid}/poll").json()["record_count"] == 1
    source.unavailable = True
    assert (
        client.get(f"/product/v1/hardware/sessions/{sid}/poll").json()["source_state"]
        == "MONGODB UNAVAILABLE"
    )
    source.unavailable = False
    assert client.get(f"/product/v1/hardware/sessions/{sid}/poll").json()["record_count"] == 1
    user = "user_b"
    assert client.get(f"/product/v1/hardware/sessions/{sid}").status_code == 403
    assert client.get("/product/v1/hardware/sessions").json() == []
    user = "none"
    assert client.get("/product/v1/hardware/sessions").status_code == 401
    user = "user_a"
    assert client.post(f"/product/v1/hardware/sessions/{sid}/stop").json()["status"] == "STOPPED"
    source.docs.append({"_id": ObjectId(), "timestamp": datetime.now(UTC), "ecg": 2020})
    assert client.get(f"/product/v1/hardware/sessions/{sid}/poll").json()["record_count"] == 1
    assert client.get(f"/product/v1/hardware/sessions/{sid}").json()["readings"][0]["ecg"] == 2001
    store.close()


def test_stop_counts_documents_already_stored_but_not_yet_polled_and_excludes_later_ones(tmp_path):
    """Pressing Stop does a final catch-up: documents stored before Stop are never lost to the 800 ms poll cadence; documents stored after Stop are not counted."""
    app = FastAPI()
    store = CapstoneSqliteStore(tmp_path / "hw.sqlite3")

    async def identity(_request):
        return AuthIdentity(user_id="u", auth_provider=AuthProviderType.CLERK, auth_session_id="s", demo_mode=False)

    install_hardware_routes(app, store, identity, {"NHM_HARDWARE_MONGO_ENABLED": "true", "NHM_HARDWARE_MONGO_URI": "mongodb://127.0.0.1:27017", "NHM_HARDWARE_MONGO_DATABASE": "health_db",
                                                   "NHM_HARDWARE_MONGO_COLLECTION": "nhm_integration_test"})

    class Source:
        collection_name = "nhm_integration_test"

        def __init__(self):
            self.docs = []

        def high_water(self):
            return self.docs[-1]["_id"] if self.docs else None

        def after(self, mark):
            return [d for d in self.docs if mark is None or d["_id"] > mark]

    source = Source()
    app.state.hardware_sessions.source = source
    client = TestClient(app)
    sid = client.post("/product/v1/hardware/sessions").json()["session_id"]
    for i in range(5):
        source.docs.append({"_id": ObjectId(), "timestamp": datetime.now(UTC), "ecg": 2000 + i, "bpm": 76, "spo2": 97})
    assert client.get(f"/product/v1/hardware/sessions/{sid}/poll").json()["record_count"] == 5
    for i in range(4):                                       # stored in MongoDB, but the browser has not polled again yet
        source.docs.append({"_id": ObjectId(), "timestamp": datetime.now(UTC), "ecg": 2100 + i, "bpm": 76, "spo2": 97})
    assert client.post(f"/product/v1/hardware/sessions/{sid}/stop").json()["record_count"] == 9
    source.docs.append({"_id": ObjectId(), "timestamp": datetime.now(UTC), "ecg": 2200})            # stored after Stop: not counted
    assert client.get(f"/product/v1/hardware/sessions/{sid}").json()["record_count"] == 9
    store.close()
