import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "contracts/API_SCHEMA_V1.json"


def _schema() -> dict:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return schema


def _sub_validator(def_name: str) -> Draft202012Validator:
    schema = _schema()
    combined = {
        "$schema": schema["$schema"],
        "$defs": schema["$defs"],
        "$ref": f"#/$defs/{def_name}",
    }
    return Draft202012Validator(combined, format_checker=FormatChecker())


def _valid_request() -> dict:
    return {
        "contract_version": "API_SCHEMA_V1",
        "session_id": "SESSION-FIXTURE-API-001",
        "timestamp_us": 5000000,
        "ecg": {"samples": [0.0] * 2500, "target_hz": 250, "window_seconds": 10},
        "ecg_quality": "VALID",
        "ppg_context": {"quality": "VALID", "pr_bpm": 70.0, "spo2_pct": 98.0, "spo2_valid": True},
        "model_id": "MODEL_V1",
    }


def _valid_response() -> dict:
    return {
        "contract_version": "API_SCHEMA_V1",
        "timestamp_us": 5000000,
        "model_id": None,
        "target": "AAMI_SVF_WINDOW_V1",
        "raw_probability": None,
        "source_domain_calibrated_probability": None,
        "calibration_domain": None,
        "calibration_patient_count": None,
        "calibration_id": None,
        "threshold": None,
        "ecg_quality": "VALID",
        "monitoring_state": "CONTEXT_UNAVAILABLE",
        "context": None,
        "latency_ms": None,
        "preprocess_version": None,
        "alert_policy_id": None,
    }


def test_request_and_response_schemas_are_valid_json_schema() -> None:
    schema = _schema()
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert {"inferWindowRequest", "inferWindowResponse", "errorResponse", "monitoringState"} <= set(
        schema["$defs"]
    )


def test_valid_request_passes() -> None:
    validator = _sub_validator("inferWindowRequest")
    assert list(validator.iter_errors(_valid_request())) == []


def test_request_requires_exact_2500_sample_ecg_window() -> None:
    validator = _sub_validator("inferWindowRequest")
    instance = _valid_request()
    instance["ecg"]["samples"] = [0.0] * 10
    assert list(validator.iter_errors(instance)) != []


def test_valid_response_passes() -> None:
    validator = _sub_validator("inferWindowResponse")
    assert list(validator.iter_errors(_valid_response())) == []


def test_response_requires_version_and_provenance_fields() -> None:
    validator = _sub_validator("inferWindowResponse")
    for field in (
        "contract_version",
        "target",
        "calibration_domain",
        "calibration_patient_count",
        "calibration_id",
        "preprocess_version",
        "alert_policy_id",
    ):
        instance = _valid_response()
        del instance[field]
        assert list(validator.iter_errors(instance)) != [], field


def test_target_is_locked_to_aami_svf_window_v1() -> None:
    validator = _sub_validator("inferWindowResponse")
    instance = _valid_response()
    instance["target"] = "ARRHYTHMIA_DIAGNOSIS_V1"
    assert list(validator.iter_errors(instance)) != []


def test_monitoring_state_enum_is_exact() -> None:
    validator = _sub_validator("inferWindowResponse")
    expected = {
        "NORMAL_MONITORED_PATTERN",
        "POTENTIAL_ECTOPY_ASSOCIATED_PATTERN",
        "RECHECK_SENSOR",
        "CONTEXT_UNAVAILABLE",
        "SYSTEM_ERROR",
    }
    schema = _schema()
    assert set(schema["$defs"]["monitoringState"]["enum"]) == expected

    instance = _valid_response()
    instance["monitoring_state"] = "DIAGNOSED_ARRHYTHMIA"
    assert list(validator.iter_errors(instance)) != []


def test_error_response_locks_status_codes() -> None:
    validator = _sub_validator("errorResponse")
    for code in (400, 422, 500):
        instance = {
            "contract_version": "API_SCHEMA_V1",
            "status_code": code,
            "error_type": "example",
            "message": "example",
        }
        assert list(validator.iter_errors(instance)) == []

    instance = {
        "contract_version": "API_SCHEMA_V1",
        "status_code": 200,
        "error_type": "example",
        "message": "example",
    }
    assert list(validator.iter_errors(instance)) != []


def test_no_disease_diagnosis_output_is_present() -> None:
    text = SCHEMA_PATH.read_text(encoding="utf-8")
    assert "No API field or endpoint may return a disease diagnosis." in text
    prohibited = ("diagnosis_label", "disease_probability", "arrhythmia_diagnosis")
    for field in prohibited:
        assert field not in text
