"""Observatory views of RECORDED-HARDWARE sessions: window trace and replay timeline (read-only, experimental)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent))
from test_hardware_v2_run import store_with_sessions  # noqa: E402

import api.hardware_telemetry_routes as routes  # noqa: E402
from api.schemas import InferWindowResponse  # noqa: E402
from product.api.errors import ProductError  # noqa: E402
from product.auth.base import AuthIdentity, AuthProviderType  # noqa: E402
from product.inference.client import OutcomeKind  # noqa: E402
from product.observatory import hardware_trace  # noqa: E402

ENV = {"NHM_HARDWARE_MONGO_ENABLED": "true", "NHM_HARDWARE_MONGO_URI": "mongodb://127.0.0.1:27017", "NHM_HARDWARE_MONGO_DATABASE": "health_db", "NHM_HARDWARE_MONGO_COLLECTION": "nhm_integration_test"}


class FakeInference:
    """Stands in for the released inference service: scores each window deterministically from its content and counts calls."""

    calls = 0

    def __init__(self, _url: str) -> None:
        self._http = self

    def build_request(self, window, sid):
        outer = self

        class Request:
            def model_dump(self, mode="json"):
                return {"window_id": window["window_id"], "samples": len(window["ecg"]["samples"]), "sid": sid, "timestamp_us": window["timestamp_us"]}

        outer._last = window
        return Request()

    sessions: dict[str, int] = {}

    async def post(self, _path, json):
        FakeInference.calls += 1
        # the released service refuses a non-increasing timestamp inside one session id; the Observatory must therefore never reuse a session id across windows
        last = FakeInference.sessions.get(json["sid"])
        if last is not None and json["timestamp_us"] <= last:
            return {**json, "rejected": "NON_MONOTONIC_TIMESTAMP"}
        FakeInference.sessions[json["sid"]] = json["timestamp_us"]
        return json

    def _interpret(self, body):
        if body.get("rejected"):
            return SimpleOutcome(OutcomeKind.INTEGRATION_ERROR, None)
        index = int(body["window_id"].rsplit("W", 1)[1])
        state = "POTENTIAL_ECTOPY_ASSOCIATED_PATTERN" if index % 4 == 3 else "NORMAL_MONITORED_PATTERN"
        response = InferWindowResponse(timestamp_us=index * 5_000_000, model_id="MODEL_V2_FINAL", raw_probability=0.2 + 0.1 * (index % 5), source_domain_calibrated_probability=0.1 + 0.1 * (index % 5),
                                       calibration_domain="MITDB_SOURCE_DOMAIN", calibration_patient_count=44, calibration_id="CAL_V2", threshold=0.35, ecg_quality="VALID", monitoring_state=state,
                                       context=None, latency_ms=3.0, preprocess_version="PREPROC_V1", alert_policy_id="ALERT_POLICY_V1")
        return SimpleOutcome(OutcomeKind.OK, response)

    async def aclose(self) -> None:
        return None


class SimpleOutcome:
    def __init__(self, kind, response) -> None:
        self.kind, self.response, self.detail = kind, response, None


def make_app(tmp_path: Path, monkeypatch, *, amplitude: float = 120.0, sessions=("HW-V2-A",)):
    monkeypatch.setattr(routes, "CapstoneInferenceClient", FakeInference)
    FakeInference.calls = 0
    FakeInference.sessions = {}
    store, _ = store_with_sessions(tmp_path, amplitude=amplitude, sessions=sessions)
    app = FastAPI()
    user = {"id": "user-a"}

    async def identity(_request):
        return None if user["id"] == "none" else AuthIdentity(user_id=user["id"], auth_provider=AuthProviderType.CLERK, auth_session_id="s", demo_mode=False)

    @app.exception_handler(ProductError)
    async def error(_request: Request, exc: ProductError):
        return JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.code, "message": exc.message}})

    routes.install_hardware_routes(app, store, identity, ENV)
    return TestClient(app), user


BASE = "/product/v1/hardware/sessions/HW-V2-A/observatory"


def test_window_list_names_the_windows_a_recording_emitted(tmp_path, monkeypatch):
    client, _ = make_app(tmp_path, monkeypatch)
    body = client.get(f"{BASE}/windows").json()
    assert body["source_kind"] == "RECORDED_HARDWARE_RESAMPLED" and "NOT VALID" in body["label"] and "unverified" in body["assumptions"]["adc_scaling"]
    assert len(body["windows"]) >= 15 and [w["window_index"] for w in body["windows"]] == sorted(w["window_index"] for w in body["windows"])
    assert any(w["ecg_quality"] == "VALID" for w in body["windows"])


def test_window_trace_runs_the_unchanged_operators_on_recorded_samples_and_labels_them(tmp_path, monkeypatch):
    client, _ = make_app(tmp_path, monkeypatch)
    windows = client.get(f"{BASE}/windows").json()["windows"]
    valid = next(w for w in windows if w["ecg_quality"] == "VALID")
    trace = client.get(f"{BASE}/windows/{valid['window_index']}").json()
    assert trace["classification"] == "RECORDED_HARDWARE_RECONSTRUCTION" and trace["source_kind"] == "RECORDED_HARDWARE_RESAMPLED" and trace["session_id"] == "HW-V2-A"
    assert trace["scenario_id"] == "RECORDED_HARDWARE:HW-V2-A" and trace["claim_boundary"].startswith("RECORDED_HARDWARE_RESAMPLED_EXPERIMENTAL")
    assert [s["stage_id"] for s in trace["stages"]] == ["SOURCE_OBSERVED", "GAP_POLICY_V1", "MITDB_360_TO_250_V1", "PREPROC_V1_ECG_FILTER_V1", "PER_WINDOW_ZSCORE_V1"]
    assert all("ASSUMED AD8232" in s["unit"] for s in trace["stages"][:4]) and "synthetic" not in " ".join(trace["limitations"]).lower().replace("synthetic labels", "")
    assert trace["normalization"]["status"] == "RECONSTRUCTED_MODEL_INPUT" and trace["normalization"]["shape"] == [1, 2500]
    assert trace["persisted_inference"]["model_id"] == "MODEL_V2_FINAL" and trace["inference_evidence_status"].startswith("EXPERIMENTAL_MODEL_RESULT")
    assert trace["quality_state"] == valid["ecg_quality"] and trace["window_id"] == valid["window_id"]
    # a second request is served from the cache: the released service is asked once per window content
    before = FakeInference.calls
    client.get(f"{BASE}/windows/{valid['window_index']}")
    assert FakeInference.calls == before


def test_a_window_the_quality_gate_rejects_has_a_trace_but_no_invented_model_result(tmp_path, monkeypatch):
    client, _ = make_app(tmp_path, monkeypatch, amplitude=700.0)          # beyond the runtime rail: CLIPPING -> UNUSABLE
    windows = client.get(f"{BASE}/windows").json()["windows"]
    assert windows and all(w["ecg_quality"] == "UNUSABLE" and "CLIPPING" in w["quality_reasons"] for w in windows)
    trace = client.get(f"{BASE}/windows/{windows[0]['window_index']}").json()
    assert trace["persisted_inference"] is None and trace["normalization"]["status"] == "NOT_APPLIED_UNUSABLE" and trace["inference_evidence_status"].startswith("NOT_ATTACHED")
    assert FakeInference.calls == 0


def test_replay_timeline_is_scored_in_bounded_batches_and_never_invents_results(tmp_path, monkeypatch):
    client, _ = make_app(tmp_path, monkeypatch)
    first = client.get(f"{BASE}/timeline?budget=5").json()
    assert first["claim_boundary"].startswith("RECORDED_HARDWARE_RESAMPLED_EXPERIMENTAL") and first["timeline_version"] == "CAPSTONE_SESSION_TIMELINE_V1"
    assert first["windows_scored"] == 5 and first["windows_pending"] >= 5 and first["complete"] is False and FakeInference.calls == 5
    done = first
    for _ in range(30):
        done = client.get(f"{BASE}/timeline?budget=48").json()
        if done["complete"]:
            break
    assert done["complete"] and done["windows_pending"] == 0 and done["windows_scored"] >= 10
    kinds = [i["kind"] for i in done["source_timeline"]]
    assert kinds.count("INFERENCE") == done["windows_scored"] and "MONITORING_STATE_CHANGE" in kinds and "QUALITY_CHANGE" in kinds and "CONTEXT_SNAPSHOT" in kinds
    assert [i["sequence_index"] for i in done["source_timeline"]] == list(range(len(done["source_timeline"])))
    changes = [i["payload"] for i in done["source_timeline"] if i["kind"] == "MONITORING_STATE_CHANGE"]
    assert changes[0]["previous_state"] is None and all(c["reason_code"] == "DERIVED_FROM_CONSECUTIVE_WINDOW_RESULTS" for c in changes)
    calls = FakeInference.calls
    assert client.get(f"{BASE}/timeline").json()["windows_scored"] == done["windows_scored"] and FakeInference.calls == calls


def test_unusable_recordings_yield_a_timeline_with_quality_only(tmp_path, monkeypatch):
    client, _ = make_app(tmp_path, monkeypatch, amplitude=700.0)
    body = client.get(f"{BASE}/timeline").json()
    assert body["windows_scored"] == 0 and body["windows_pending"] == 0 and body["complete"] and body["windows_unusable"] == body["windows_total"] > 0
    assert {i["kind"] for i in body["source_timeline"]} <= {"QUALITY_CHANGE", "CONTEXT_SNAPSHOT"} and FakeInference.calls == 0


def test_sessions_are_owner_scoped_and_authenticated(tmp_path, monkeypatch):
    client, user = make_app(tmp_path, monkeypatch)
    user["id"] = "user-b"
    for path in ("windows", "windows/0", "timeline"):
        assert client.get(f"{BASE}/{path}").status_code == 403
    user["id"] = "none"
    assert client.get(f"{BASE}/windows").status_code == 401
    user["id"] = "user-a"
    assert client.get("/product/v1/hardware/sessions/NOPE/observatory/windows").status_code in (403, 404)


def test_out_of_range_window_is_not_found(tmp_path, monkeypatch):
    client, _ = make_app(tmp_path, monkeypatch)
    assert client.get(f"{BASE}/windows/9999").status_code == 404


@pytest.mark.parametrize("fn", ["window_list", "timeline"])
def test_too_short_a_recording_is_handled(fn):
    readings = [{"document_id": "d0", "ingested_at": "2026-10-15T00:00:00+00:00", "ecg": 2048, "bpm": 70, "spo2": 97}]
    out = getattr(hardware_trace, fn)("S", readings) if fn == "window_list" else getattr(hardware_trace, fn)("S", readings, {})
    assert (out["windows"] == []) if fn == "window_list" else out["windows_total"] == 0


def test_windows_can_be_traced_in_any_order_because_each_window_is_its_own_inference_session(tmp_path, monkeypatch):
    client, _ = make_app(tmp_path, monkeypatch)
    valid = [w for w in client.get(f"{BASE}/windows").json()["windows"] if w["ecg_quality"] == "VALID"]
    assert len(valid) >= 6
    for window in (valid[5], valid[1], valid[3], valid[0]):                # descending / shuffled: a shared session id would be refused as non-monotonic
        trace = client.get(f"{BASE}/windows/{window['window_index']}").json()
        assert trace["persisted_inference"] is not None, window
    done = client.get(f"{BASE}/timeline?budget=48").json()
    assert done["windows_pending"] == 0 and done["windows_scored"] == len(valid)
