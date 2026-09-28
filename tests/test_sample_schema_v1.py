import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "contracts/sample_schema_v1.json"
FIXTURES = ROOT / "tests/fixtures/contracts"


def _validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_schema_is_valid_draft_2020_12() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    Draft202012Validator.check_schema(schema)


def test_ecg_only_fixture_is_valid_with_explicit_null_context() -> None:
    validator = _validator()
    instance = _load("valid_ecg_only_sample_v1.json")
    assert list(validator.iter_errors(instance)) == []
    assert instance["ppg_red_raw"] is None
    assert instance["ppg_ir_raw"] is None
    assert instance["spo2_pct"] is None
    assert instance["spo2_valid"] is False


def test_multimodal_fixture_is_valid() -> None:
    validator = _validator()
    instance = _load("valid_multimodal_sample_v1.json")
    assert list(validator.iter_errors(instance)) == []


def test_missing_required_identity_or_time_field_is_rejected() -> None:
    validator = _validator()
    instance = _load("invalid_missing_timestamp_v1.json")
    errors = list(validator.iter_errors(instance))
    assert errors
    assert any("timestamp_us" in str(error.message) for error in errors)


def test_invalid_quality_enum_is_rejected() -> None:
    validator = _validator()
    instance = _load("invalid_quality_enum_v1.json")
    errors = list(validator.iter_errors(instance))
    assert errors
    assert any("ecg_quality" in list(error.path) or "GOOD" in error.message for error in errors)


def test_negative_sample_index_is_rejected() -> None:
    validator = _validator()
    instance = _load("invalid_negative_sample_index_v1.json")
    errors = list(validator.iter_errors(instance))
    assert errors
    assert any("sample_index" in list(error.path) for error in errors)


def test_negative_timestamp_is_rejected() -> None:
    validator = _validator()
    instance = _load("valid_ecg_only_sample_v1.json")
    instance["timestamp_us"] = -1
    errors = list(validator.iter_errors(instance))
    assert errors


def test_contract_version_is_required_and_locked() -> None:
    validator = _validator()
    instance = _load("valid_ecg_only_sample_v1.json")
    instance["contract_version"] = "SAMPLE_SCHEMA_V2"
    errors = list(validator.iter_errors(instance))
    assert errors

    without_version = dict(instance)
    del without_version["contract_version"]
    errors = list(validator.iter_errors(without_version))
    assert errors


def test_additional_properties_are_rejected() -> None:
    validator = _validator()
    instance = _load("valid_ecg_only_sample_v1.json")
    instance["unexpected_field"] = 1
    errors = list(validator.iter_errors(instance))
    assert errors
