"""CAP-009 owner, summary, time-domain, preview and raw-context exclusion controls."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from api.product_app_v1_3 import CAP009_ROUTES, create_product_app_v1_3
from capstone_persistence.store import CapstoneSqliteStore
from product.persistence.preview import ENCODING, encode
from product.session import SessionState
from scripts.capstone_cap003_test_identity import cap003_test_identity_resolver
from tests.capstone_federation_support import DESCRIPTION, USER_A, USER_B

BASE = "/product/v1"


def fixture_app(root: Path):
    store = CapstoneSqliteStore(root / "product.sqlite3", clock=lambda: 12_000_000)
    app = create_product_app_v1_3(
        store=store, identity_resolver=cap003_test_identity_resolver,
        auth_description=DESCRIPTION, federation_artifact_root=root / "federation",
        candidate_root=root / "candidates", auto_resume=False,
    )
    return app, store


def seed(client: TestClient, store: CapstoneSqliteStore, *, complete: bool = True) -> str:
    device = client.post(f"{BASE}/devices/simulated",
                         json={"scenario_id": "MIXED_MONITORING_SESSION"},
                         headers=USER_A).json()
    did = device["device_id"]
    assert client.post(f"{BASE}/devices/{did}/scan", headers=USER_A).status_code == 200
    assert client.post(f"{BASE}/devices/{did}/connect", headers=USER_A).status_code == 200
    created = client.post(f"{BASE}/sessions",
                          json={"device_id": did, "scenario_id": "MIXED_MONITORING_SESSION"},
                          headers=USER_A)
    assert created.status_code == 200, created.text
    sid = created.json()["session_id"]
    if complete:
        store.update_session_state(sid, SessionState.MONITORING, started_at_us=1_000_000)
        store.update_session_state(sid, SessionState.COMPLETED, ended_at_us=6_999_999)
    else:
        store.update_session_state(sid, SessionState.FAILED, ended_at_us=6_999_999)
    store.insert_inference_event(
        session_id=sid, sequence_index=1, timestamp_us=50_000_000,
        model_id="MODEL_V2_FINAL", calibration_domain="MIT-BIH-v1.0.0",
        ecg_quality="VALID", monitoring_state="NORMAL_MONITORED_PATTERN",
        raw_probability=.2, calibrated_probability=.3, threshold=.51, latency_ms=7,
        raw_context={"spo2_pct": 666.0, "secret_raw_context": "WITHHELD_SENTINEL"},
    )
    store.insert_quality_event(session_id=sid, sequence_index=2,
                               timestamp_us=51_000_000, ecg_quality="UNUSABLE",
                               ppg_quality=None)
    store.insert_context_snapshot(
        session_id=sid, sequence_index=1, timestamp_us=50_000_000,
        context={"hr_ecg_bpm": 72, "pr_ppg_bpm": None, "spo2_pct": None,
                 "spo2_valid": False, "context_available": False, "ppg_quality": None},
    )
    store.upsert_waveform_preview(
        session_id=sid, channel="ECG", source_rate_hz=360,
        decimation_factor=3, point_count=3, start_timestamp_us=49_000_000,
        encoding=ENCODING, data=encode([12, None, -3]),
    )
    return sid


def test_exact_cap009_routes_and_research_auth(tmp_path: Path) -> None:
    app, _ = fixture_app(tmp_path)
    routes = {(method, r.path.removeprefix(BASE)) for r in app.routes
              for method in (getattr(r, "methods", None) or ()) if r.path.startswith(BASE)}
    assert set(CAP009_ROUTES) <= routes
    assert len([r for r in routes if r in CAP009_ROUTES]) == 4
    with TestClient(app) as client:
        assert client.get(f"{BASE}/research/ml").status_code == 401
        ml = client.get(f"{BASE}/research/ml", headers=USER_A)
        fl = client.get(f"{BASE}/research/fl", headers=USER_B)
        assert ml.status_code == fl.status_code == 200
        assert ml.json()["evidence_domain"] == "ML"
        assert fl.json()["scientific_fl_phases"] == [
            "V2-FL-001", "V2-FL-002", "V2-FL-003", "V2-FL-EVAL-001", "V2-FL-004"]
        assert client.get(f"{BASE}/research/ml", headers=USER_B).json() == ml.json()


def test_summary_timeline_owner_context_and_restart(tmp_path: Path) -> None:
    app, store = fixture_app(tmp_path)
    with TestClient(app) as client:
        sid = seed(client, store)
        summary_url = f"{BASE}/sessions/{sid}/summary"
        timeline_url = f"{BASE}/sessions/{sid}/timeline"
        assert client.get(summary_url, headers=USER_B).status_code == 403
        assert client.get(timeline_url, headers=USER_B).status_code == 403
        assert client.get(f"{BASE}/sessions/UNKNOWN/summary", headers=USER_A).status_code == 404
        summary = client.get(summary_url, headers=USER_A).json()
        assert summary == client.get(summary_url, headers=USER_A).json()
        assert summary["duration_ms"] == 5999
        assert summary["duration_basis"] == "PRODUCT_LIFECYCLE_CLOCK"
        assert summary["windows_inferred"] == 1
        assert summary["state_counts"] == {"NORMAL_MONITORED_PATTERN": 1}
        assert summary["quality_counts"] == {"VALID": 1}  # change-only UNUSABLE is not a window
        assert summary["hr_min"] == summary["hr_mean"] == summary["hr_max"] == 72
        assert summary["spo2_min"] is None
        timeline = client.get(timeline_url, headers=USER_A).json()
        assert [x["kind"] for x in timeline["source_timeline"]] == [
            "INFERENCE", "CONTEXT_SNAPSHOT", "QUALITY_CHANGE"]
        assert timeline["time_domains"] == {
            "source_timeline": "SOURCE_TIMELINE", "device_lifecycle": "PRODUCT_CLOCK"}
        assert timeline["waveform_previews"][0]["points"] == [12, None, -3]
        assert "WITHHELD_SENTINEL" not in json.dumps(timeline)
        assert "666" not in json.dumps(timeline)
    with sqlite3.connect(store.path) as db:
        row = db.execute("SELECT count(*) FROM session_summaries WHERE session_id=?", (sid,))
        assert row.fetchone()[0] == 1
    app2, _ = fixture_app(tmp_path)
    with TestClient(app2) as client:
        assert client.get(summary_url, headers=USER_A).json() == summary
        assert client.get(timeline_url, headers=USER_A).json() == timeline


def test_failed_session_has_partial_timeline_but_no_summary(tmp_path: Path) -> None:
    app, store = fixture_app(tmp_path)
    with TestClient(app) as client:
        sid = seed(client, store, complete=False)
        response = client.get(f"{BASE}/sessions/{sid}/summary", headers=USER_A)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "INVALID_STATE"
        assert client.get(f"{BASE}/sessions/{sid}/timeline", headers=USER_A).status_code == 200
