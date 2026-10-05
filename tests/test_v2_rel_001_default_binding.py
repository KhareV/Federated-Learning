"""V2-REL-001 default-runtime tests: identity of the default and rollback stacks, import hygiene,
no public selector, the fail-closed tamper/misbinding matrix, V1/V2 mixed-stack rejection and
behavioural equivalence of the default app with the frozen API_RUNTIME_V2_1 research app."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.app_default import (
    DEFAULT_LOCK,
    ROLLBACK_LOCK,
    STACKS,
    DefaultBindingError,
    assert_no_public_selector,
    assert_stack_identity,
    create_default_app,
    create_rollback_v1_app,
    verify_binding,
)

ROOT = Path(__file__).resolve().parents[1]


def _events(name: str) -> list[dict]:
    bundle = json.loads((ROOT / f"frontend/static/replay/{name}.json").read_text())
    return sorted(bundle["events"], key=lambda e: e["sequence_index"])


def _body(event: dict, session: str, model_id: str | None = None) -> dict:
    return {"contract_version": "API_SCHEMA_V1", "session_id": session,
            "timestamp_us": event["timestamp_us"], "ecg": event["ecg"],
            "ecg_quality": event["ecg_quality"], "ppg_context": event["ppg_context"],
            "model_id": model_id or event["model_id"]}


@pytest.fixture(scope="module")
def default_client() -> TestClient:
    return TestClient(create_default_app())


def test_default_identity_is_exactly_the_v2_stack(default_client: TestClient) -> None:
    event = _events("WEARABLE_SIM_V2_REPLAY_V1")[0]
    response = default_client.post("/v1/infer-window", json=_body(event, "ident"))
    assert response.status_code == 200
    data = response.json()
    cal = json.loads((ROOT / "artifacts/CAL_V2.json").read_text())
    assert data["model_id"] == "MODEL_V2_FINAL" and data["calibration_id"] == "CAL_V2"
    assert data["calibration_domain"] == cal["calibration_domain"]
    assert data["threshold"] == cal["threshold"] and data["preprocess_version"] == "PREPROC_V1"
    assert data["alert_policy_id"] == "ALERT_POLICY_V1"
    assert default_client.app.state.profile == "default"
    assert default_client.app.state.runtime.policy.model_id == "MODEL_V2_FINAL"


def test_rollback_identity_is_exactly_the_v1_stack() -> None:
    app = create_rollback_v1_app()
    runtime = app.state.runtime
    assert (runtime.policy.model_id, runtime.policy.calibration_id) == ("MODEL_V1", "CAL_V1")
    assert app.state.profile == "rollback-v1"
    event = _events("PUBLIC_ECG_REPLAY_V1")[0]
    response = TestClient(app).post("/v1/infer-window", json=_body(event, "rb"))
    assert response.status_code in (200, 422)
    if response.status_code == 200:
        assert response.json()["model_id"] == "MODEL_V1"
        assert response.json()["calibration_id"] == "CAL_V1"


def test_no_public_selector_and_wrong_model_is_400(default_client: TestClient) -> None:
    assert_no_public_selector(default_client.app)
    event = _events("WEARABLE_SIM_V2_REPLAY_V1")[0]
    response = default_client.post("/v1/infer-window", json=_body(event, "sel", "MODEL_V1"))
    assert response.status_code == 400
    assert response.json()["error_type"] == "UNSUPPORTED_MODEL_ID"
    paths = {r.path for r in default_client.app.routes}
    assert "/v1/infer-window" in paths
    assert not any("model" in p for p in paths if p != "/v1/infer-window")


def test_selector_parameter_is_rejected() -> None:
    app = FastAPI()

    @app.post("/v1/infer-window")
    def route(model: str) -> dict:  # a public selector as a query parameter
        return {"model": model}

    with pytest.raises(DefaultBindingError, match="PUBLIC_SELECTOR"):
        assert_no_public_selector(app)
    extra = FastAPI()

    @extra.get("/v1/select-model")
    def select() -> dict:
        return {}

    with pytest.raises(DefaultBindingError, match="UNEXPECTED_ROUTE"):
        assert_no_public_selector(extra)


def test_default_module_does_not_import_v1_or_truth_at_import() -> None:
    code = ("import sys, api.app_default; bad=[m for m in sys.modules if m=='api.app' or "
            "'truth' in m or 'fl_cohort' in m or m=='api.runtime_v2' and False]; "
            "assert not bad, bad; assert 'api.app' not in sys.modules")
    subprocess.run([sys.executable, "-c", code], cwd=ROOT, check=True)


@pytest.mark.parametrize(("profile", "identity"), [
    ("default", {**STACKS["default"], "calibration_id": "CAL_V1"}),       # MODEL_V2 + CAL_V1
    ("default", {**STACKS["default"], "model_id": "MODEL_V1"}),            # MODEL_V1 + CAL_V2
    ("default", {**STACKS["default"], "gateway_artifact_id": "GATEWAY_ARTIFACT_V1"}),
    ("default", {**STACKS["default"], "alert_policy_binding_id": "ALERT_POLICY_V1"}),
    ("default", {**STACKS["default"], "api_contract_version": "API_SCHEMA_V2"}),
    ("default", {**STACKS["default"], "preprocess_id": "PREPROC_V2"}),
    ("rollback", {**STACKS["rollback"], "calibration_id": "CAL_V2"}),      # MODEL_V1 + CAL_V2
    ("rollback", {**STACKS["rollback"], "gateway_artifact_id": "GATEWAY_ARTIFACT_V2"}),
    ("rollback", {**STACKS["rollback"], "model_id": "MODEL_V2_FINAL"}),
])
def test_mixed_or_wrong_stack_identity_is_rejected(profile: str, identity: dict) -> None:
    with pytest.raises(DefaultBindingError):
        assert_stack_identity(profile, identity)
    assert_stack_identity("default", STACKS["default"])
    assert_stack_identity("rollback", STACKS["rollback"])


def _copy_root(tmp_path: Path, lock_relative: str) -> Path:
    lock = json.loads((ROOT / lock_relative).read_text())
    root = tmp_path / "root"
    for relative in [*lock["bound_artifacts"], lock_relative]:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    return root


@pytest.mark.parametrize("target", [
    "checkpoints/MODEL_V2_FINAL.pt",                                  # wrong MODEL_V2 checkpoint
    "artifacts/deployment/MODEL_V2_GATEWAY_FP32.ts",                  # wrong gateway artifact
    "artifacts/CAL_V2.json",                                          # wrong CAL_V2 / threshold
    "manifests/preprocessing/PREPROC_V1.lock.json",                   # wrong PREPROC lock
    "artifacts/ALERT_POLICY_V1_MODEL_V2_BINDING.lock.json",           # wrong alert binding
    "contracts/API_SCHEMA_V1.json",                                   # wrong API schema
    "api/runtime_v2.py", "api/app_v2.py", "api/app_default.py",
    "artifacts/SYSTEM_V2_RELEASE_DECISION_V1.lock.json",
    "artifacts/DASHBOARD_UI_V1_5.lock.json",
])
def test_default_binding_fails_closed_on_any_tamper(tmp_path: Path, target: str) -> None:
    root = _copy_root(tmp_path, DEFAULT_LOCK)
    verify_binding(root, DEFAULT_LOCK, "default")  # the untouched copy verifies
    victim = root / target
    victim.write_bytes(victim.read_bytes() + b"\n#tamper")
    with pytest.raises(DefaultBindingError, match="DEFAULT_BINDING_TAMPER"):
        verify_binding(root, DEFAULT_LOCK, "default")
    with pytest.raises(DefaultBindingError, match="DEFAULT_BINDING_TAMPER"):
        create_default_app(root)


def test_default_binding_missing_file_and_missing_lock(tmp_path: Path) -> None:
    root = _copy_root(tmp_path, DEFAULT_LOCK)
    (root / "artifacts/CAL_V2.json").unlink()
    with pytest.raises(DefaultBindingError, match="MISSING"):
        verify_binding(root, DEFAULT_LOCK, "default")
    with pytest.raises(DefaultBindingError, match="LOCK_MISSING"):
        verify_binding(tmp_path / "empty", DEFAULT_LOCK, "default")


def test_lock_with_mixed_identity_is_rejected(tmp_path: Path) -> None:
    root = _copy_root(tmp_path, DEFAULT_LOCK)
    path = root / DEFAULT_LOCK
    lock = json.loads(path.read_text())
    lock["identity"]["calibration_id"] = "CAL_V1"
    path.write_text(json.dumps(lock))
    with pytest.raises(DefaultBindingError, match=r"STACK_MISMATCH|MIXED"):
        verify_binding(root, DEFAULT_LOCK, "default")
    lock["identity"]["calibration_id"] = "CAL_V2"
    lock["public_model_selector"] = True
    path.write_text(json.dumps(lock))
    with pytest.raises(DefaultBindingError, match="SELECTOR"):
        verify_binding(root, DEFAULT_LOCK, "default")


@pytest.mark.parametrize("target", ["checkpoints/MODEL_V1.pt", "artifacts/CAL_V1.json",
                                    "artifacts/deployment/MODEL_V1_GATEWAY_FP32.ts",
                                    "artifacts/ALERT_POLICY_V1.lock.json", "api/app.py"])
def test_rollback_binding_fails_closed_on_tamper(tmp_path: Path, target: str) -> None:
    root = _copy_root(tmp_path, ROLLBACK_LOCK)
    verify_binding(root, ROLLBACK_LOCK, "rollback")
    victim = root / target
    victim.write_bytes(victim.read_bytes() + b"\n#tamper")
    with pytest.raises(DefaultBindingError, match="TAMPER"):
        verify_binding(root, ROLLBACK_LOCK, "rollback")


def test_default_equals_frozen_research_runtime_on_replay_fixtures(
        default_client: TestClient) -> None:
    from api.app_v2 import create_research_app
    from api.runtime_v2 import ResearchRuntimeV2

    research = TestClient(create_research_app(runtime=ResearchRuntimeV2()))
    fields = ("timestamp_us", "model_id", "raw_probability", "source_domain_calibrated_probability",
              "calibration_domain", "calibration_patient_count", "calibration_id", "threshold",
              "ecg_quality", "monitoring_state", "context", "preprocess_version", "alert_policy_id")
    compared = 0
    for name in ("WEARABLE_SIM_V2_REPLAY_V1", "WEARABLE_SIM_V2_REPLAY_V2_FLATLINE"):
        for event in _events(name):
            a = default_client.post("/v1/infer-window", json=_body(event, f"d-{name}"))
            b = research.post("/v1/infer-window", json=_body(event, f"d-{name}"))
            assert a.status_code == b.status_code, event["window_id"]
            if a.status_code == 200:
                assert {k: a.json()[k] for k in fields} == {k: b.json()[k] for k in fields}
            else:
                assert a.json() == b.json()
            compared += 1
    # schema / ordering error semantics are identical too
    event = _events("WEARABLE_SIM_V2_REPLAY_V1")[0]
    for payload in (_body(event, "x", "MODEL_V1"), {"bad": 1}):
        assert default_client.post("/v1/infer-window", json=payload).json() == research.post(
            "/v1/infer-window", json=payload).json()
    assert compared >= 100
