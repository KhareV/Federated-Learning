"""T032 golden-path integration tests against the REAL, unmocked production app.

Exercises `api.app.app` (built via `create_app(runtime=ProductionRuntime())`), i.e. genuine
GATEWAY_ARTIFACT_V1 / MODEL_V1 / CAL_V1 / ALERT_POLICY_V1 / ECG_HR_CONTEXT_V2 / PREPROC_V1 --
never a fake. `tests/test_api_stateful_t032.py` and `tests/test_api_errors_t032.py` use the
lighter-weight fake runtime from `tests/_t032_support.py` for HTTP-layer/state-machine
coverage; this file exists specifically to prove the whole chain is wired correctly end to end.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker

from api.app import app as production_app
from api.schemas import ECG_WINDOW_SAMPLE_COUNT

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "contracts/API_SCHEMA_V1.json"

MONITORING_STATES = {
    "NORMAL_MONITORED_PATTERN",
    "POTENTIAL_ECTOPY_ASSOCIATED_PATTERN",
    "RECHECK_SENSOR",
    "CONTEXT_UNAVAILABLE",
    "SYSTEM_ERROR",
}


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(production_app)


def _payload(session_id: str, timestamp_us: int) -> dict:
    return {
        "contract_version": "API_SCHEMA_V1",
        "session_id": session_id,
        "timestamp_us": timestamp_us,
        "ecg": {
            "samples": [0.0] * ECG_WINDOW_SAMPLE_COUNT,
            "target_hz": 250,
            "window_seconds": 10,
        },
        "ecg_quality": "VALID",
        "ppg_context": None,
        "model_id": "MODEL_V1",
    }


def _response_validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    combined = {
        "$schema": schema["$schema"],
        "$defs": schema["$defs"],
        "$ref": "#/$defs/inferWindowResponse",
    }
    return Draft202012Validator(combined, format_checker=FormatChecker())


def test_golden_path_returns_200_with_real_frozen_artifacts(client: TestClient) -> None:
    response = client.post("/v1/infer-window", json=_payload("GOLDEN-1", 1_000_000))
    assert response.status_code == 200
    body = response.json()

    assert body["contract_version"] == "API_SCHEMA_V1"
    assert body["target"] == "AAMI_SVF_WINDOW_V1"
    assert body["model_id"] == "MODEL_V1"
    assert body["calibration_id"] == "CAL_V1"
    assert body["calibration_domain"] == "MIT-BIH-v1.0.0"
    assert body["calibration_patient_count"] == 3
    assert 0.0 <= body["raw_probability"] <= 1.0
    assert 0.0 <= body["source_domain_calibrated_probability"] <= 1.0
    assert 0.0 <= body["threshold"] <= 1.0
    assert body["preprocess_version"] == "PREPROC_V1"
    assert body["alert_policy_id"] == "ALERT_POLICY_V1"
    assert body["monitoring_state"] in MONITORING_STATES
    assert body["latency_ms"] >= 0.0
    assert body["ecg_quality"] == "VALID"
    assert isinstance(body["context"], dict)
    assert body["context"]["ecg_hr_context_id"] == "ECG_HR_CONTEXT_V2"


def test_golden_path_response_matches_api_schema_v1(client: TestClient) -> None:
    validator = _response_validator()
    response = client.post("/v1/infer-window", json=_payload("GOLDEN-2", 2_000_000))
    assert response.status_code == 200
    assert list(validator.iter_errors(response.json())) == []


def test_response_never_contains_diagnosis_wording(client: TestClient) -> None:
    response = client.post("/v1/infer-window", json=_payload("GOLDEN-3", 3_000_000))
    text = json.dumps(response.json()).lower()
    for prohibited in ("diagnos", "disease", "arrhythmia_label", "cardiac_emergency"):
        assert prohibited not in text


def test_context_does_not_alter_calibrated_probability_or_threshold(client: TestClient) -> None:
    """Context invariance (Section 98): raw probability, calibrated probability, and the
    frozen threshold must never change based on PPG/SpO2 context -- only the ECG window and
    MODEL_V1/CAL_V1 may determine them."""
    base = _payload("GOLDEN-INVAR", 4_000_000)
    with_context = _payload("GOLDEN-INVAR", 4_005_000)
    with_context["ppg_context"] = {
        "quality": "VALID",
        "pr_bpm": 72.0,
        "spo2_pct": 97.5,
        "spo2_valid": True,
    }

    r1 = TestClient(production_app).post("/v1/infer-window", json=base)
    r2 = TestClient(production_app).post("/v1/infer-window", json=with_context)

    b1, b2 = r1.json(), r2.json()
    assert b1["raw_probability"] == b2["raw_probability"]
    assert (
        b1["source_domain_calibrated_probability"]
        == b2["source_domain_calibrated_probability"]
    )
    assert b1["threshold"] == b2["threshold"]


def test_t005_fixture_path_still_isolated_and_passing() -> None:
    """Confirms the T005 historical fixture slice (re-exported from api/fixture_v0.py via
    api/app.py) remains untouched by the T032 production rewrite -- see
    tests/test_api_slice_t005.py, which imports directly from api.app."""
    import tests.test_api_slice_t005 as t005

    t005.test_response_is_json_serializable()
    t005.test_response_reports_correct_monitoring_state()
    t005.test_no_fake_calibration_or_model_evidence()
    t005.test_does_not_claim_to_satisfy_production_api_schema()
