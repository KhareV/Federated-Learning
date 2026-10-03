"""V2-013: API_RUNTIME_V2 binding, identity, differential equality against the V1 app code path,
error semantics, C032 branch separation, alert-policy binding and V1-default preservation."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

import api.app as v1_app_module
import api.app_v2 as v2_app_module
import api.runtime_v2 as v2_runtime_module
from api.app import create_app as create_v1_style_app
from api.app_v2 import create_research_app
from api.runtime_v2 import ResearchRuntimeV2
from fusion.alert_policy_v2_binding import binding_payload, load_alert_policy_v2_binding
from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = 2500


@pytest.fixture(scope="module")
def runtime() -> ResearchRuntimeV2:
    return ResearchRuntimeV2(ROOT, verify="manifest")


def _wave(scale: float = 1.0, offset: float = 0.0) -> list[float]:
    t = np.arange(SAMPLES) / 250.0
    return (scale * np.sin(2 * np.pi * 1.2 * t) * (1 + 0.3 * np.sin(2 * np.pi * 7 * t))
            + offset).tolist()


def _body(session: str, ts: int, *, model_id: str, samples: list[float] | None = None,
          quality: str = "VALID", ppg: dict | None = None) -> dict:
    return {"contract_version": "API_SCHEMA_V1", "session_id": session, "timestamp_us": ts,
            "ecg": {"samples": samples if samples is not None else _wave(),
                    "target_hz": 250, "window_seconds": 10},
            "ecg_quality": quality, "ppg_context": ppg, "model_id": model_id}


def test_runtime_binds_v2_identities_from_frozen_artifacts(runtime: ResearchRuntimeV2) -> None:
    cal = json.loads((ROOT / "artifacts/CAL_V2.json").read_text())
    assert runtime.runtime_id == "API_RUNTIME_V2"
    assert runtime.bound_model_id == "MODEL_V2_FINAL"
    assert runtime.preprocess_id == "PREPROC_V1"
    assert runtime.calibration_patient_count == cal["calibration_patient_count"] == 3
    assert runtime.policy.model_id == "MODEL_V2_FINAL"
    assert runtime.policy.calibration_id == "CAL_V2"
    assert runtime.policy.threshold == cal["threshold"]
    assert runtime.policy.threshold_comparator == ">="


def test_v2_app_serves_v2_identity_and_rejects_v1_model_id(runtime: ResearchRuntimeV2) -> None:
    client = TestClient(create_research_app(runtime=runtime))
    ok = client.post("/v1/infer-window", json=_body("S-ID", 1_000_000, model_id="MODEL_V2_FINAL"))
    assert ok.status_code == 200
    body = ok.json()
    assert (body["model_id"], body["calibration_id"], body["alert_policy_id"]) == (
        "MODEL_V2_FINAL", "CAL_V2", "ALERT_POLICY_V1")
    assert body["calibration_domain"] == "MIT-BIH-v1.0.0"
    assert body["contract_version"] == "API_SCHEMA_V1"
    rejected = client.post("/v1/infer-window", json=_body("S-ID2", 1, model_id="MODEL_V1"))
    assert rejected.status_code == 400


def test_no_public_runtime_model_selector(runtime: ResearchRuntimeV2) -> None:
    client = TestClient(create_research_app(runtime=runtime))
    for field, value in (("checkpoint", "x.pt"), ("temperature", 1.0), ("threshold", 0.1),
                         ("model_path", "/tmp/m.ts")):
        body = _body(f"S-SEL-{field}", 1_000_000, model_id="MODEL_V2_FINAL")
        body[field] = value
        assert client.post("/v1/infer-window", json=body).status_code == 400
    source = Path(v2_app_module.__file__).read_text()
    request_fields = json.loads((ROOT / "contracts/API_SCHEMA_V1.json").read_text())["$defs"][
        "inferWindowRequest"]["properties"]
    assert not {"checkpoint", "temperature", "threshold", "model_path"} & set(request_fields)
    assert "os.environ" not in source


def test_differential_equality_with_v1_app_code_path_on_same_runtime(
        runtime: ResearchRuntimeV2) -> None:
    """The V1 app factory with the V2 runtime differs only by its hard-coded MODEL_V1 request
    check; sending MODEL_V1 to that app and MODEL_V2_FINAL to the V2 app over the same ordered
    inputs must give identical response bodies."""
    ppg = {"quality": "VALID", "pr_bpm": 72.0, "spo2_pct": 97.0, "spo2_valid": True}
    v1_style = TestClient(create_v1_style_app(runtime=ResearchRuntimeV2(ROOT, verify="manifest")))
    v2 = TestClient(create_research_app(runtime=runtime))
    for i, (scale, offset) in enumerate(((0.5, 0.0), (1.0, 0.3), (2.0, -1.0), (5.0, 2.0))):
        samples = _wave(scale, offset)
        ts = 10_000_000 + 5_000_000 * i
        a = v1_style.post("/v1/infer-window", json=_body(
            "DIFF", ts, model_id="MODEL_V1", samples=samples, ppg=ppg))
        b = v2.post("/v1/infer-window", json=_body(
            "DIFF", ts, model_id="MODEL_V2_FINAL", samples=samples, ppg=ppg))
        assert a.status_code == b.status_code == 200
        assert _semantic(a.json()) == _semantic(b.json())


def _semantic(body: dict) -> dict:
    return {k: v for k, v in body.items() if k != "latency_ms"}


def test_error_semantics_400_422_500(runtime: ResearchRuntimeV2) -> None:
    client = TestClient(create_research_app(runtime=runtime))
    assert client.post("/v1/infer-window", json={"bad": 1}).status_code == 400
    short = _body("S-E1", 1, model_id="MODEL_V2_FINAL", samples=[0.0] * 10)
    v1_short = _body("S-E1", 1, model_id="MODEL_V1", samples=[0.0] * 10)
    v1_status = TestClient(v1_app_module.app).post("/v1/infer-window", json=v1_short).status_code
    assert client.post("/v1/infer-window", json=short).status_code == v1_status == 422
    unusable = client.post("/v1/infer-window", json=_body(
        "S-E2", 1_000_000, model_id="MODEL_V2_FINAL", quality="UNUSABLE"))
    assert unusable.status_code == 422
    assert unusable.json()["error_type"] == "UNUSABLE_OR_INCOMPLETE_SIGNAL_WINDOW"
    assert "MODEL_V1" not in unusable.json()["message"]

    class Boom(ResearchRuntimeV2):
        def infer(self, ecg_samples):  # type: ignore[no-untyped-def]
            raise RuntimeError("secret internal detail")

    boom = TestClient(create_research_app(runtime=Boom(ROOT, verify="manifest")),
                      raise_server_exceptions=False)
    response = boom.post("/v1/infer-window", json=_body("S-E3", 1, model_id="MODEL_V2_FINAL"))
    assert response.status_code == 500
    assert "secret" not in response.text and "Traceback" not in response.text


def test_unusable_window_never_reaches_inference(runtime: ResearchRuntimeV2) -> None:
    calls = {"infer": 0, "hr": 0}

    class Spy(ResearchRuntimeV2):
        def infer(self, ecg_samples):  # type: ignore[no-untyped-def]
            calls["infer"] += 1
            return super().infer(ecg_samples)

        def estimate_ecg_hr(self, ecg_samples, *, timestamp_us):  # type: ignore[no-untyped-def]
            calls["hr"] += 1
            return super().estimate_ecg_hr(ecg_samples, timestamp_us=timestamp_us)

    client = TestClient(create_research_app(runtime=Spy(ROOT, verify="manifest")))
    response = client.post("/v1/infer-window", json=_body(
        "S-U", 1_000_000, model_id="MODEL_V2_FINAL", quality="UNUSABLE"))
    assert response.status_code == 422
    assert calls == {"infer": 0, "hr": 0}


def test_c032_branch_separation_hr_gets_unnormalized_gateway_gets_zscore(
        monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, np.ndarray] = {}
    runtime = ResearchRuntimeV2(ROOT, verify="manifest")
    real_gateway_infer = runtime.gateway.infer
    real_hr = v2_runtime_module.estimate_hr

    def spy_gateway(x):  # type: ignore[no-untyped-def]
        seen["gateway"] = np.array(x, dtype=np.float64).ravel()
        return real_gateway_infer(x)

    def spy_hr(array, **kwargs):  # type: ignore[no-untyped-def]
        seen["hr"] = np.array(array, dtype=np.float64)
        return real_hr(array, **kwargs)

    monkeypatch.setattr(runtime.gateway, "infer", spy_gateway)
    monkeypatch.setattr(v2_runtime_module, "estimate_hr", spy_hr)
    samples = _wave(scale=3.0, offset=0.7)
    client = TestClient(create_research_app(runtime=runtime))
    assert client.post("/v1/infer-window", json=_body(
        "S-C032", 15_000_000, model_id="MODEL_V2_FINAL", samples=samples)).status_code == 200
    original = np.asarray(samples, dtype=np.float64)
    np.testing.assert_array_equal(seen["hr"], original)
    assert abs(seen["gateway"].mean()) < 1e-5
    assert abs(seen["gateway"].std() - 1.0) < 1e-3
    assert not np.allclose(seen["gateway"], original)


def test_alert_policy_binding_keeps_locked_semantics() -> None:
    policy = load_alert_policy_v2_binding(ROOT)
    cal = json.loads((ROOT / "artifacts/CAL_V2.json").read_text())
    payload = binding_payload(ROOT)
    assert payload["policy_id"] == "ALERT_POLICY_V1"
    assert payload["binding_id"] == "ALERT_POLICY_V1_MODEL_V2_BINDING"
    assert payload["policy_changed"] is False and payload["new_clinical_policy"] is False
    assert (policy.required_open, policy.required_close) == (2, 2)
    assert policy.cooldown_us == 30_000_000
    assert policy.threshold == cal["threshold"] and policy.threshold_comparator == ">="
    assert (policy.model_id, policy.calibration_id) == ("MODEL_V2_FINAL", "CAL_V2")
    assert payload["threshold_source"] == "CAL_V2"


def test_alert_policy_v1_config_and_engine_unchanged_by_binding() -> None:
    lock = json.loads((ROOT / "artifacts/ALERT_POLICY_V1.lock.json").read_text())
    assert hash_file(ROOT / "configs/alert_policy_v1.yaml") == lock["config_sha256"]
    assert hash_file(ROOT / "fusion/episode_manager.py") == lock["episode_manager_sha256"]
    assert hash_file(ROOT / "fusion/state_machine.py") == lock["state_machine_sha256"]


def test_v1_remains_the_operational_default() -> None:
    client = TestClient(v1_app_module.app)
    response = client.post("/v1/infer-window", json=_body("S-V1", 1_000_000, model_id="MODEL_V1"))
    assert response.status_code == 200
    assert response.json()["model_id"] == "MODEL_V1"
    assert response.json()["calibration_id"] == "CAL_V1"
    assert client.post("/v1/infer-window", json=_body(
        "S-V1B", 1, model_id="MODEL_V2_FINAL")).status_code == 400


def _imports(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_v1_modules_do_not_reference_v2_runtime_or_binding() -> None:
    for relative in ("api/app.py", "api/runtime.py", "api/schemas.py", "api/session.py"):
        imported = _imports(ROOT / relative)
        assert not {m for m in imported if "runtime_v2" in m or "app_v2" in m
                    or "alert_policy_v2" in m or "gateway_v2" in m}, relative
    assert "api.app" not in _imports(ROOT / "api/app_v2.py")
    assert "app_v2" not in (ROOT / "Makefile").read_text()


def test_v2_app_has_no_import_time_runtime_construction() -> None:
    tree = ast.parse(Path(v2_app_module.__file__).read_text())
    top_level_calls = [n for n in tree.body if isinstance(n, ast.Assign)
                       and isinstance(n.value, ast.Call)]
    for node in top_level_calls:
        text = ast.unparse(node)
        assert "ResearchRuntimeV2" not in text and "create_research_app" not in text
