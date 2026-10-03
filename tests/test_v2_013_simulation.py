"""V2-013: WEARABLE_SIM separation (ObservedRecord vs SimulationTruth), streaming runtime
correctness against verification-only truth, deterministic stream/replay behavior and the
canonical semantic digest."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from itertools import pairwise
from pathlib import Path

import pytest

import scripts._v2_013_lib as lib
import simulation.truth_v2013 as truth
from simulation import profile_v2013 as prof
from simulation.stream_runtime_v2013 import run_stream
from simulation.types import ObservedRecord

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_FILES = (
    "simulation/stream_runtime_v2013.py", "api/runtime_v2.py", "api/app_v2.py",
    "fusion/alert_policy_v2_binding.py", "deployment/gateway_v2.py",
)
FORBIDDEN_MODULES = ("simulation.truth_v2013", "simulation.profile_v2013")
EXCERPT = prof.LIVE_EXCERPT_PROFILE
KWARGS = {"session_id": "T-SIM", "model_id": "MODEL_V2_FINAL", "replay_id": "T-SIM-REPLAY"}


def _imports(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
            found.update(f"{node.module}.{a.name}" for a in node.names)
    return found


@pytest.fixture(scope="module")
def excerpt_events() -> list[dict]:
    return run_stream(prof.iter_observed_records(EXCERPT), mode="ACCELERATED_REPLAY", **KWARGS)


def test_production_path_never_imports_truth_or_generator_profile() -> None:
    for relative in PRODUCTION_FILES:
        imported = _imports(ROOT / relative)
        assert not {m for m in imported if m.startswith(FORBIDDEN_MODULES)}, relative


def test_runtime_import_closure_excludes_truth_in_fresh_interpreter() -> None:
    code = (
        "import sys, api.runtime_v2, api.app_v2, simulation.stream_runtime_v2013, "
        "fusion.alert_policy_v2_binding;"
        "bad=[m for m in ('simulation.truth_v2013','simulation.profile_v2013') "
        "if m in sys.modules];"
        "print(bad)"
    )
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True,
                            text=True, check=True)
    assert result.stdout.strip() == "[]"


def test_observed_records_carry_no_truth_fields() -> None:
    record = next(iter(prof.iter_observed_records(EXCERPT)))
    assert isinstance(record, ObservedRecord)
    names = {f for f in getattr(record, "__dataclass_fields__", {})} | set(
        getattr(record, "__slots__", ()))
    assert names, "ObservedRecord fields not introspectable"
    for name in names:
        assert "truth" not in name.lower() and "fault" not in name.lower()


def test_behavioral_leakage_poisoned_truth_does_not_change_runtime_output(
        excerpt_events: list[dict], monkeypatch: pytest.MonkeyPatch) -> None:
    def poisoned(*_a: object, **_k: object) -> str:
        raise AssertionError("SimulationTruth consulted by the production path")

    monkeypatch.setattr(truth, "expected_window_quality", poisoned)
    monkeypatch.setattr(truth, "expected_context_mode", poisoned)
    again = run_stream(prof.iter_observed_records(EXCERPT), mode="ACCELERATED_REPLAY", **KWARGS)
    assert again == excerpt_events


def test_stream_quality_and_context_match_truth_only_in_verification(
        excerpt_events: list[dict]) -> None:
    assert excerpt_events
    for event in excerpt_events:
        edge = event["timestamp_us"]
        assert event["ecg_quality"] == truth.expected_window_quality(EXCERPT, edge)
        mode = truth.expected_context_mode(EXCERPT, edge)
        context = event["ppg_context"]
        if mode == "MISSING_PPG":
            assert context is None


def test_stream_windows_have_full_2500_samples_and_right_edge_cadence(
        excerpt_events: list[dict]) -> None:
    edges = [e["timestamp_us"] for e in excerpt_events]
    assert all(len(e["ecg"]["samples"]) == 2500 for e in excerpt_events)
    assert edges[0] == 15_000_000
    assert all(b - a == 5_000_000 for a, b in pairwise(edges))


def test_stream_is_deterministic_and_chunk_size_invariant(
        excerpt_events: list[dict], monkeypatch: pytest.MonkeyPatch) -> None:
    import simulation.stream_runtime_v2013 as sr

    for size in (97, 1000):
        monkeypatch.setattr(sr, "CHUNK_RECORDS", size)
        variant = run_stream(prof.iter_observed_records(EXCERPT), mode="ACCELERATED_REPLAY",
                             **KWARGS)
        assert variant == excerpt_events


def test_live_speed_pacing_does_not_change_events_and_uses_injected_clock(
        excerpt_events: list[dict]) -> None:
    slept: list[float] = []
    live = run_stream(prof.iter_observed_records(EXCERPT), mode="LIVE_SPEED_REPLAY",
                      sleep=slept.append, **KWARGS)
    assert live == excerpt_events
    assert slept, "LIVE_SPEED_REPLAY must pace delivery"


def test_full_profile_bundle_matches_manifest_and_is_complete() -> None:
    bundle_path = ROOT / "frontend/static/replay/WEARABLE_SIM_V2_REPLAY_V1.json"
    manifest = json.loads((ROOT / "tests/fixtures/e2e/WEARABLE_SIM_V2_REPLAY_V1.manifest.json"
                           ).read_text())
    import hashlib

    assert hashlib.sha256(bundle_path.read_bytes()).hexdigest() == manifest["bundle_sha256"]
    events = json.loads(bundle_path.read_text())["events"]
    assert len(events) == manifest["window_count"] == 93
    assert all(len(e["ecg"]["samples"]) == 2500 for e in events)
    assert {e["model_id"] for e in events} == {"MODEL_V2_FINAL"}
    assert {e["ecg_quality"] for e in events} == {"VALID", "DEGRADED", "UNUSABLE"}


def test_flatline_source_fault_limitation_is_disclosed() -> None:
    audit = json.loads((ROOT / "reports/model_v2/v2_013/simulator_maturity_audit.json"
                        ).read_text())
    assert "flatline" in json.dumps(audit).lower()


def _row(seq: int, prob: float = 0.2, latency: float = 1.0) -> dict:
    return {"sequence_index": seq, "window_id": f"w{seq}", "timestamp_us": seq,
            "request_ecg_quality": "VALID", "request_model_id": "MODEL_V2_FINAL",
            "ecg_samples_sha256": "x", "http_status": 200, "error": None,
            "response": {k: None for k in lib.SEMANTIC_RESPONSE_FIELDS}
            | {"monitoring_state": "NORMAL_MONITORED_PATTERN",
               "raw_probability": prob, "latency_ms": latency}}


def test_digest_canonicalizes_number_spelling_and_detects_semantic_change() -> None:
    base = lib.canonical_digest([_row(0, 0.2)])["sha256"]
    int_spelled = _row(0, 0.2)
    int_spelled["timestamp_us"] = 0.0
    assert lib.canonical_digest([int_spelled])["sha256"] == base
    assert lib.canonical_digest([_row(0, 0.2000001)])["sha256"] != base


def test_digest_excludes_only_declared_nondeterministic_fields() -> None:
    assert set(lib.EXCLUDED_FROM_DIGEST) == {
        "latency_ms", "session_id", "wall_clock_time", "process_id"}
    assert "monitoring_state" in lib.SEMANTIC_RESPONSE_FIELDS
    assert "raw_probability" in lib.SEMANTIC_RESPONSE_FIELDS
    assert "latency_ms" not in lib.SEMANTIC_RESPONSE_FIELDS
