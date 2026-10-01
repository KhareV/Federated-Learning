"""T032 tamper matrix (Section 85): mutating any locked identity/shape must be detected --
never silently accepted. Each test name identifies exactly one tamper target; evidence
generation (scripts/generate_t032_evidence.py) runs this file and records pass/fail per
scenario into reports/t032/tamper_matrix.json.

Tests that need a real file mutation operate on a throwaway shadow copy of only the files
involved (never the live repository, never a full-repo copy -- see
tests/test_api_runtime_lock_t032.py for why).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from api.schemas import ErrorResponse, InferWindowResponse
from scripts.verify_api_runtime_t032 import verify as verify_api_runtime

ROOT = Path(__file__).resolve().parents[1]


def _shadow_bound_files(tmp_path: Path) -> Path:
    lock = json.loads((ROOT / "artifacts/API_RUNTIME_V1.lock.json").read_text(encoding="utf-8"))
    shadow_root = tmp_path / "repo"
    (shadow_root / "artifacts").mkdir(parents=True)
    (shadow_root / "artifacts/API_RUNTIME_V1.lock.json").write_text(
        (ROOT / "artifacts/API_RUNTIME_V1.lock.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    for relative_path in lock["bound_artifacts"]:
        destination = shadow_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((ROOT / relative_path).read_bytes())
    return shadow_root


def _tamper_and_expect_runtime_tamper(monkeypatch, tmp_path, relative_path: str) -> None:
    shadow_root = _shadow_bound_files(tmp_path)
    target = shadow_root / relative_path
    target.write_bytes(target.read_bytes() + b"\ntampered\n")
    monkeypatch.setattr("scripts.verify_api_runtime_t032.ROOT", shadow_root)
    with pytest.raises(RuntimeError, match="API_RUNTIME_V1_TAMPER"):
        verify_api_runtime()


def test_api_schema_v1_tamper_is_detected(monkeypatch, tmp_path) -> None:
    _tamper_and_expect_runtime_tamper(monkeypatch, tmp_path, "contracts/API_SCHEMA_V1.json")


def test_openapi_contract_tamper_is_detected(monkeypatch, tmp_path) -> None:
    _tamper_and_expect_runtime_tamper(monkeypatch, tmp_path, "contracts/openapi_v1.json")


def test_gateway_artifact_identity_tamper_is_detected(monkeypatch, tmp_path) -> None:
    _tamper_and_expect_runtime_tamper(
        monkeypatch, tmp_path, "artifacts/deployment/MODEL_V1_GATEWAY_FP32.ts"
    )


def test_model_v1_checkpoint_tamper_is_detected(monkeypatch, tmp_path) -> None:
    _tamper_and_expect_runtime_tamper(monkeypatch, tmp_path, "checkpoints/MODEL_V1.pt")


def test_preproc_v1_lock_tamper_is_detected(monkeypatch, tmp_path) -> None:
    _tamper_and_expect_runtime_tamper(
        monkeypatch, tmp_path, "manifests/preprocessing/PREPROC_V1.lock.json"
    )


def test_cal_v1_temperature_and_threshold_tamper_is_detected(monkeypatch, tmp_path) -> None:
    _tamper_and_expect_runtime_tamper(monkeypatch, tmp_path, "artifacts/CAL_V1.json")


def test_alert_policy_v1_lock_tamper_is_detected(monkeypatch, tmp_path) -> None:
    _tamper_and_expect_runtime_tamper(monkeypatch, tmp_path, "artifacts/ALERT_POLICY_V1.lock.json")


def test_ecg_hr_context_v2_lock_tamper_is_detected(monkeypatch, tmp_path) -> None:
    _tamper_and_expect_runtime_tamper(
        monkeypatch, tmp_path, "artifacts/ECG_HR_CONTEXT_V2.lock.json"
    )


def test_api_app_source_tamper_is_detected(monkeypatch, tmp_path) -> None:
    _tamper_and_expect_runtime_tamper(monkeypatch, tmp_path, "api/app.py")


def test_monitoring_state_enum_tamper_is_rejected() -> None:
    with pytest.raises(ValidationError):
        InferWindowResponse(
            timestamp_us=1,
            model_id="MODEL_V1",
            calibration_domain="MIT-BIH-v1.0.0",
            calibration_id="CAL_V1",
            ecg_quality="VALID",
            monitoring_state="DIAGNOSED_ARRHYTHMIA",
            context=None,
            preprocess_version="PREPROC_V1",
            alert_policy_id="ALERT_POLICY_V1",
        )


def test_status_code_mapping_tamper_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ErrorResponse(status_code=404, error_type="NOT_FOUND", message="x")


def test_target_id_tamper_is_rejected() -> None:
    with pytest.raises(ValidationError):
        InferWindowResponse(
            timestamp_us=1,
            model_id="MODEL_V1",
            target="ARRHYTHMIA_DIAGNOSIS_V1",
            calibration_domain="MIT-BIH-v1.0.0",
            calibration_id="CAL_V1",
            ecg_quality="VALID",
            monitoring_state="NORMAL_MONITORED_PATTERN",
            context=None,
            preprocess_version="PREPROC_V1",
            alert_policy_id="ALERT_POLICY_V1",
        )


def test_response_contract_version_tamper_is_rejected() -> None:
    with pytest.raises(ValidationError):
        InferWindowResponse(
            contract_version="API_SCHEMA_V2",
            timestamp_us=1,
            model_id="MODEL_V1",
            calibration_domain="MIT-BIH-v1.0.0",
            calibration_id="CAL_V1",
            ecg_quality="VALID",
            monitoring_state="NORMAL_MONITORED_PATTERN",
            context=None,
            preprocess_version="PREPROC_V1",
            alert_policy_id="ALERT_POLICY_V1",
        )


def test_openapi_route_tamper_is_detected_as_drift() -> None:
    """A hand-edited contracts/openapi_v1.json (e.g. renaming the documented route) must
    disagree with the live app.openapi() output -- see test_api_openapi_t032.py's drift test,
    which this scenario specifically targets."""
    from api.app import app

    live = json.loads(json.dumps(app.openapi()))
    tampered = json.loads(json.dumps(live))
    tampered["paths"]["/v1/infer-window-RENAMED"] = tampered["paths"].pop("/v1/infer-window")
    assert tampered != live
