#!/usr/bin/env python3
"""Validate the T003 canonical contract artifacts and emit machine-readable evidence."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"
FIXTURES = ROOT / "tests/fixtures/contracts"

REQUIRED_IDENTIFIERS = [
    "SPEC_VERSION = 2.2",
    "HARDWARE_DATA_CONTRACT_V1",
    "SAMPLE_SCHEMA_V1",
    "LABEL_SCHEMA_V1",
    "AAMI_SVF_WINDOW_V1",
    "AAMI_SVF_MAP_V1",
    "API_SCHEMA_V1",
]

VALID_FIXTURES = [
    "valid_ecg_only_sample_v1.json",
    "valid_multimodal_sample_v1.json",
]
INVALID_FIXTURES = {
    "invalid_missing_timestamp_v1.json": "timestamp_us",
    "invalid_quality_enum_v1.json": "ecg_quality",
    "invalid_negative_sample_index_v1.json": "sample_index",
}


def load_schema(path: Path) -> dict[str, Any]:
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return schema


def validate_sample_schema() -> dict[str, Any]:
    schema_path = CONTRACTS / "sample_schema_v1.json"
    schema = load_schema(schema_path)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())

    results: list[dict[str, Any]] = []
    for name in VALID_FIXTURES:
        instance = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
        errors = sorted(validator.iter_errors(instance), key=str)
        results.append({"fixture": name, "expected": "VALID", "passed": not errors})

    for name, expected_field in INVALID_FIXTURES.items():
        instance = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
        errors = list(validator.iter_errors(instance))
        matched = any(
            expected_field in str(error.path) or expected_field in error.message
            for error in errors
        )
        results.append(
            {
                "fixture": name,
                "expected": "INVALID",
                "passed": bool(errors) and matched,
                "expected_reason_field": expected_field,
            }
        )
    return {"schema": str(schema_path.relative_to(ROOT)), "results": results}


def validate_api_schema() -> dict[str, Any]:
    schema_path = CONTRACTS / "API_SCHEMA_V1.json"
    schema = load_schema(schema_path)

    def sub_validator(def_name: str) -> Draft202012Validator:
        combined = {
            "$schema": schema["$schema"],
            "$defs": schema["$defs"],
            "$ref": f"#/$defs/{def_name}",
        }
        return Draft202012Validator(combined, format_checker=FormatChecker())

    valid_request = {
        "contract_version": "API_SCHEMA_V1",
        "session_id": "SESSION-FIXTURE-API-001",
        "timestamp_us": 5000000,
        "ecg": {"samples": [0.0] * 2500, "target_hz": 250, "window_seconds": 10},
        "ecg_quality": "VALID",
        "ppg_context": None,
        "model_id": "MODEL_V1",
    }
    invalid_request = dict(valid_request)
    invalid_request["ecg"] = {"samples": [0.0] * 10, "target_hz": 250, "window_seconds": 10}

    valid_response = {
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
    invalid_response = dict(valid_response)
    invalid_response["monitoring_state"] = "DIAGNOSED_ARRHYTHMIA"

    cases = [
        ("valid_infer_window_request", "inferWindowRequest", valid_request, True),
        ("invalid_infer_window_request_ecg_length", "inferWindowRequest", invalid_request, False),
        ("valid_infer_window_response", "inferWindowResponse", valid_response, True),
        (
            "invalid_infer_window_response_monitoring_state",
            "inferWindowResponse",
            invalid_response,
            False,
        ),
    ]
    results = []
    for label, def_name, instance, expect_valid in cases:
        validator = sub_validator(def_name)
        errors = list(validator.iter_errors(instance))
        passed = (not errors) if expect_valid else bool(errors)
        expected_label = "VALID" if expect_valid else "INVALID"
        results.append({"fixture": label, "expected": expected_label, "passed": passed})

    return {"schema": str(schema_path.relative_to(ROOT)), "results": results}


def verify_identifiers() -> dict[str, bool]:
    text = "\n".join(
        (CONTRACTS / name).read_text(encoding="utf-8")
        for name in (
            "HARDWARE_DATA_CONTRACT_V1.md",
            "sample_schema_v1.json",
            "API_SCHEMA_V1.json",
            "LABEL_SCHEMA_V1.md",
        )
    )
    return {identifier: identifier in text for identifier in REQUIRED_IDENTIFIERS}


def count_verification_required() -> tuple[int, list[str]]:
    contract = (CONTRACTS / "HARDWARE_DATA_CONTRACT_V1.md").read_text(encoding="utf-8")
    rows = re.findall(r"\|\s*\d+\s*\|\s*(.+?)\s*\|\s*VERIFICATION_REQUIRED\s*\|", contract)
    return len(rows), rows


def main() -> None:
    sample_result = validate_sample_schema()
    api_result = validate_api_schema()
    identifiers = verify_identifiers()
    unresolved_count, unresolved_items = count_verification_required()

    label_schema = (CONTRACTS / "LABEL_SCHEMA_V1.md").read_text(encoding="utf-8")
    required_label_markers = [
        "AAMI_SVF_WINDOW_V1",
        "AAMI_SVF_MAP_V1",
        "SVF_CONTAINING_WINDOW",
        "N_ONLY_WINDOW",
        "RECHECK_SENSOR",
        "UNMAPPABLE",
        "paced",
    ]
    label_markers_present = {marker: marker in label_schema for marker in required_label_markers}

    all_fixture_results = sample_result["results"] + api_result["results"]
    fixture_pass = all(row["passed"] for row in all_fixture_results)
    identifiers_pass = all(identifiers.values())
    label_pass = all(label_markers_present.values())
    overall_pass = fixture_pass and identifiers_pass and label_pass
    schema_validation_status = "PASS" if overall_pass else "FAIL"

    report = {
        "task_id": "T003",
        "spec_version": "2.2",
        "contract_ids": [
            "HARDWARE_DATA_CONTRACT_V1",
            "SAMPLE_SCHEMA_V1",
            "API_SCHEMA_V1",
            "LABEL_SCHEMA_V1",
        ],
        "schema_validation_status": schema_validation_status,
        "fixture_tests": all_fixture_results,
        "required_identifiers_present": identifiers,
        "label_markers_present": label_markers_present,
        "verification_required_count": unresolved_count,
        "unresolved_hardware_items": unresolved_items,
        "status": schema_validation_status,
    }

    output = ROOT / "reports/t003/contract_validation.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(f"{output.suffix}.tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(output)

    print(
        f"T003 contract validation: {schema_validation_status} "
        f"fixtures={len(all_fixture_results)} verification_required={unresolved_count}"
    )
    if schema_validation_status != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
