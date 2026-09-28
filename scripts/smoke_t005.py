#!/usr/bin/env python3
"""End-to-end T005 vertical-slice smoke runner.

fixture -> MOCK_INFERENCE_V0 -> FIXTURE_STATE_POLICY_V0 -> API-facing result -> evidence.
No network, no hardware, no MongoDB, no public-dataset download, no model training.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from api.app import FIXTURE_API_RESPONSE_VERSION, process_observed_record
from deployment.mock_inference import MOCK_INFERENCE_MODEL_ID
from fusion.state_machine import FIXTURE_STATE_POLICY_ID
from simulation.fixtures import (
    MANIFEST_FIXTURE_PATH,
    OBSERVED_FIXTURE_PATH,
    TRUTH_FIXTURE_PATH,
    render_fixture_files,
)

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports/t005"

# Production-path modules that must never import the simulation truth channel. Their source
# is scanned via AST (not just tested behaviorally) so a future accidental import is caught
# even before any test that exercises behavior would notice. AST scanning (rather than a
# plain substring search) avoids false positives from these modules' own docstrings, which
# legitimately describe this exact boundary rule in prose.
PRODUCTION_MODULES = (
    ROOT / "deployment/mock_inference.py",
    ROOT / "fusion/state_machine.py",
    ROOT / "api/app.py",
)
_FORBIDDEN_MODULES = {"simulation.wearable", "simulation.fixtures"}
_FORBIDDEN_NAMES = {"SimulationTruth", "get_truth"}


def _references_truth_channel(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name in _FORBIDDEN_MODULES for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module in _FORBIDDEN_MODULES:
                return True
            if module == "simulation" and any(
                alias.name in {"wearable", "fixtures"} for alias in node.names
            ):
                return True
            if any(alias.name in _FORBIDDEN_NAMES for alias in node.names):
                return True
        elif isinstance(node, ast.Name | ast.Attribute):
            name = node.id if isinstance(node, ast.Name) else node.attr
            if name in _FORBIDDEN_NAMES:
                return True
    return False


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").strip().splitlines()]


def run_pipeline(observed_dicts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        process_observed_record(SimpleNamespace(**record)).to_dict() for record in observed_dicts
    ]


def verify_fixture_matches_checked_in() -> None:
    observed_lines, truth_lines, manifest = render_fixture_files()
    checked_in_observed = (
        (ROOT / OBSERVED_FIXTURE_PATH).read_text(encoding="utf-8").strip().splitlines()
    )
    checked_in_truth = (ROOT / TRUTH_FIXTURE_PATH).read_text(encoding="utf-8").strip().splitlines()
    checked_in_manifest = json.loads((ROOT / MANIFEST_FIXTURE_PATH).read_text(encoding="utf-8"))
    if observed_lines != checked_in_observed:
        raise RuntimeError("T005 fixture drift: session_v1.jsonl does not match regeneration")
    if truth_lines != checked_in_truth:
        raise RuntimeError(
            "T005 fixture drift: session_v1_truth.jsonl does not match regeneration"
        )
    if manifest != checked_in_manifest:
        raise RuntimeError(
            "T005 fixture drift: session_v1_manifest.json does not match regeneration"
        )


def verify_no_truth_channel_imports() -> str:
    for path in PRODUCTION_MODULES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if _references_truth_channel(tree):
            return "FAIL"
    return "PASS"


def verify_determinism(observed_dicts: list[dict[str, Any]]) -> str:
    run_a = run_pipeline(observed_dicts)
    run_b = run_pipeline(observed_dicts)
    return "PASS" if run_a == run_b else "FAIL"


def main() -> None:
    verify_fixture_matches_checked_in()

    observed_dicts = load_jsonl(ROOT / OBSERVED_FIXTURE_PATH)
    truth_dicts = load_jsonl(ROOT / TRUTH_FIXTURE_PATH)
    manifest = json.loads((ROOT / MANIFEST_FIXTURE_PATH).read_text(encoding="utf-8"))

    results = run_pipeline(observed_dicts)
    state_sequence = [result["monitoring_state"] for result in results]
    expected_sequence = [truth["expected_monitoring_state"] for truth in truth_dicts]
    if state_sequence != expected_sequence:
        raise RuntimeError("T005 smoke: state sequence does not match scenario expectation")

    determinism_status = verify_determinism(observed_dicts)
    truth_leakage_status = verify_no_truth_channel_imports()
    overall_status = (
        "PASS" if determinism_status == "PASS" and truth_leakage_status == "PASS" else "FAIL"
    )

    report = {
        "task_id": "T005",
        "simulation_id": manifest["dataset_id"],
        "profile": manifest["profile"],
        "seed": manifest["simulation_seed"],
        "participant_count": 1,
        "session_count": 1,
        "observed_record_count": len(observed_dicts),
        "mock_inference_id": MOCK_INFERENCE_MODEL_ID,
        "fixture_state_policy_id": FIXTURE_STATE_POLICY_ID,
        "fixture_api_response_version": FIXTURE_API_RESPONSE_VERSION,
        "state_sequence": state_sequence,
        "truth_leakage_test_status": truth_leakage_status,
        "determinism_status": determinism_status,
        "overall_status": overall_status,
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    output = REPORT_DIR / "smoke_report.json"
    temporary = output.with_suffix(f"{output.suffix}.tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(output)

    print(f"T005 smoke: {overall_status} records={len(observed_dicts)} states={state_sequence}")
    if overall_status != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
