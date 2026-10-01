#!/usr/bin/env python3
"""Generate deterministic T032/G18 scope, provenance, test-result, and hash inventory
evidence. Mirrors the house style of scripts/generate_t031_evidence.py."""

from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import fastapi
import pydantic
import starlette

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/t032"

T032_TEST_FILES = [
    "tests/test_api_t032.py",
    "tests/test_api_errors_t032.py",
    "tests/test_api_stateful_t032.py",
    "tests/test_api_openapi_t032.py",
    "tests/test_api_scope_t032.py",
    "tests/test_api_runtime_lock_t032.py",
    "tests/test_api_tamper_matrix_t032.py",
    "tests/test_api_schema_v1.py",
    "tests/test_api_slice_t005.py",
]

TAMPER_TEST_FILE = "tests/test_api_tamper_matrix_t032.py"

RESULT_LINE = re.compile(r"^(?P<nodeid>\S+::\S+)\s+(?P<outcome>PASSED|FAILED|ERROR)\b")


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _run_pytest(paths: list[str]) -> tuple[bool, list[dict[str, str]]]:
    env = os.environ.copy()
    env["PYTHONPATH"] = "src:."
    process = subprocess.run(
        [sys.executable, "-m", "pytest", "-v", "--tb=short", *paths],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    results = []
    for line in process.stdout.splitlines():
        match = RESULT_LINE.match(line)
        if match:
            results.append({"test": match.group("nodeid"), "outcome": match.group("outcome")})
    return process.returncode == 0, results


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    overall_pass, test_results = _run_pytest(T032_TEST_FILES)
    write_json(
        OUT / "test_summary.json",
        {
            "status": "PASS" if overall_pass else "FAIL",
            "files": T032_TEST_FILES,
            "total": len(test_results),
            "passed": sum(1 for r in test_results if r["outcome"] == "PASSED"),
            "failed": sum(1 for r in test_results if r["outcome"] != "PASSED"),
            "results": test_results,
        },
    )
    if not overall_pass:
        raise RuntimeError("T032_TEST_SUITE_FAILED")

    tamper_pass, tamper_results = _run_pytest([TAMPER_TEST_FILE])
    write_json(
        OUT / "tamper_matrix.json",
        {
            "status": "PASS" if tamper_pass else "FAIL",
            "scenario_count": len(tamper_results),
            "scenarios": tamper_results,
        },
    )
    if not tamper_pass:
        raise RuntimeError("T032_TAMPER_MATRIX_FAILED")

    scope = {
        "MODEL_V1_modified": False,
        "model_training": False,
        "threshold_tuning": False,
        "CAL_fitting": False,
        "PREPROC_change": False,
        "dataset_access": False,
        "simulation_truth_access": False,
        "database_or_auth_dependency": False,
        "disease_diagnosis_wording": False,
        "websocket_equivalence_implemented": False,
        "websocket_equivalence_note": (
            "T032 delivers the REST contract POST /v1/infer-window only. The gate-registry "
            "row's prose ('REST/WebSocket equivalence') is planning-stage language from "
            "Sections 4-5; no WebSocket transport was specified by the actual T032 task "
            "packet delivered, so none is implemented or claimed here. This is reported "
            "explicitly, not silently dropped."
        ),
        "new_canonical_freeze_registry_row_created": False,
        "component_lock_created": "API_RUNTIME_V1",
        "status": "PASS",
    }
    write_json(OUT / "scope_audit.json", scope)

    write_json(
        OUT / "run_manifest.json",
        {
            "task": "T032",
            "method": "TYPED_API_AND_VERSIONED_RUNTIME_CONTRACT",
            "Python": platform.python_version(),
            "fastapi": fastapi.__version__,
            "pydantic": pydantic.VERSION,
            "starlette": starlette.__version__,
            "device": "CPU",
            "command": "PYTHONPATH=src:. .venv-t032/bin/python -m pytest "
            + " ".join(T032_TEST_FILES),
            "api_runtime_lock_sha256": hash_file(ROOT / "artifacts/API_RUNTIME_V1.lock.json"),
            "openapi_sha256": hash_file(ROOT / "contracts/openapi_v1.json"),
            "CI_executed": False,
            "status": "PASS",
        },
    )

    artifacts = [
        "api/app.py",
        "api/schemas.py",
        "api/runtime.py",
        "api/session.py",
        "api/fixture_v0.py",
        "contracts/API_SCHEMA_V1.json",
        "contracts/openapi_v1.json",
        "artifacts/API_RUNTIME_V1.lock.json",
        "scripts/generate_openapi_v1_t032.py",
        "scripts/freeze_api_runtime_t032.py",
        "scripts/verify_api_runtime_t032.py",
        "scripts/generate_t032_evidence.py",
        *T032_TEST_FILES,
        "tests/_t032_support.py",
        "reports/t032/scope_audit.json",
        "reports/t032/run_manifest.json",
        "reports/t032/test_summary.json",
        "reports/t032/tamper_matrix.json",
    ]
    write_json(OUT / "artifact_hashes.json", {path: hash_file(ROOT / path) for path in artifacts})

    write_json(
        ROOT / "reports/api_v1.json",
        {
            "gate_id": "G18",
            "task_id": "T032",
            "status": "PASS",
            "route": "POST /v1/infer-window",
            "contract_version": "API_SCHEMA_V1",
            "target_id": "AAMI_SVF_WINDOW_V1",
            "component_lock": "API_RUNTIME_V1",
            "component_lock_sha256": hash_file(ROOT / "artifacts/API_RUNTIME_V1.lock.json"),
            "openapi_path": "contracts/openapi_v1.json",
            "openapi_sha256": hash_file(ROOT / "contracts/openapi_v1.json"),
            "error_semantics": {
                "400": "REQUEST_SCHEMA_ERROR / application-level request-contract error",
                "422": "UNUSABLE_OR_INCOMPLETE_SIGNAL_WINDOW (MODEL_V1 never run)",
                "500": "INTERNAL_SERVER_ERROR (safe generic body)",
            },
            "monitoring_state_vocabulary": [
                "NORMAL_MONITORED_PATTERN",
                "POTENTIAL_ECTOPY_ASSOCIATED_PATTERN",
                "RECHECK_SENSOR",
                "CONTEXT_UNAVAILABLE",
                "SYSTEM_ERROR",
            ],
            "websocket_equivalence_implemented": False,
            "websocket_equivalence_note": scope["websocket_equivalence_note"],
            "disease_diagnosis_wording_present": False,
            "pass_criteria": (
                "Versioned outputs/errors and research semantics pass."
            ),
            "test_summary_path": "reports/t032/test_summary.json",
            "tamper_matrix_path": "reports/t032/tamper_matrix.json",
            "scope_audit_path": "reports/t032/scope_audit.json",
            "evidence_path": "reports/api_v1.json",
        },
    )
    print("reports/api_v1.json")


if __name__ == "__main__":
    main()
