"""T034 SimulationTruth isolation (Section 31/32).

WEARABLE_SIM_REPLAY_V1 originates from engineering simulation; this suite proves
SimulationTruth/get_truth()/expected_monitoring_state/latent_hr/latent_spo2 never enter the
request body, the production API runtime, the gateway, or the dashboard -- statically (source
import checks) and dynamically (building the actual replay requests and asserting no truth
field name appears in them).
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.run_replay import _sim_requests

ROOT = Path(__file__).resolve().parents[1]

TRUTH_ONLY_FIELDS = (
    "true_activity",
    "latent_hr",
    "latent_spo2",
    "scheduled_fault",
    "actual_fault_active",
    "true_signal_quality",
    "expected_monitoring_state",
    "segment_kind",
    "segment_name",
)


def test_build_wearable_sim_replay_fixture_never_imports_get_truth() -> None:
    import ast

    tree = ast.parse(
        (ROOT / "scripts/build_wearable_sim_replay_t034.py").read_text(encoding="utf-8")
    )
    imported_names = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert "get_truth" not in imported_names
    assert "SimulationTruth" not in imported_names


def test_run_replay_never_imports_get_truth_or_simulation_truth() -> None:
    text = (ROOT / "scripts/run_replay.py").read_text(encoding="utf-8")
    assert "get_truth" not in text
    assert "SimulationTruth" not in text
    assert "simulation.wearable" not in text
    assert "simulation.types" not in text


def test_replay_ts_adapter_never_references_simulation_truth() -> None:
    text = (ROOT / "frontend/src/lib/dashboard/replay.ts").read_text(encoding="utf-8")
    for forbidden in TRUTH_ONLY_FIELDS:
        assert forbidden not in text
    assert "SimulationTruth" not in text


def test_actual_sim_replay_requests_contain_no_truth_field() -> None:
    requests_ = _sim_requests("T034-ISOLATION-CHECK")
    serialized = json.dumps(requests_)
    for forbidden in TRUTH_ONLY_FIELDS:
        assert forbidden not in serialized, forbidden


def test_actual_sim_replay_requests_match_the_real_api_schema_fields_only() -> None:
    """Every top-level request field is one API_SCHEMA_V1 actually defines (plus the
    internal-only `_window_id` key, stripped before sending)."""
    allowed = {
        "contract_version",
        "session_id",
        "timestamp_us",
        "ecg",
        "ecg_quality",
        "ppg_context",
        "model_id",
        "_window_id",
    }
    for payload in _sim_requests("T034-SCHEMA-FIELD-CHECK"):
        assert set(payload.keys()) <= allowed


def test_wearable_sim_fixture_manifest_declares_no_truth_usage() -> None:
    manifest = json.loads(
        (ROOT / "tests/fixtures/e2e/WEARABLE_SIM_REPLAY_V1.manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["simulation_truth_used"] is False
    assert manifest["labels_included"] is False
    assert manifest["claim_boundary"].startswith("SIMULATION_ENGINEERING_ONLY")
