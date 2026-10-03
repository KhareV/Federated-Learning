"""V2-013 post-result tests: canonical evidence PASS, frozen locks verify and detect tamper,
deterministic replay facts, registry transition, preserved predecessors and V2-014 untouched."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

import scripts.verify_api_runtime_v2 as verifier
from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_013"
REQUIRED_PASS = (
    "api_runtime_equivalence", "api_schema_compatibility", "alert_policy_binding_audit",
    "state_sequence_audit", "v1_default_regression", "runtime_isolation_audit",
    "truth_isolation_audit", "normalization_branch_audit", "replay_semantic_digest",
    "replay_mode_invariance", "frontend_e2e_evidence", "runtime_binding_manifest",
    "frontend_compatibility", "runtime_architecture", "protected_artifact_audit",
)


def _load(name: str) -> dict:
    return json.loads((OUT / f"{name}.json").read_text(encoding="utf-8"))


def _rows(name: str) -> list[dict]:
    with (ROOT / f"manifests/model_v2/{name}_registry_v1.csv").open(newline="") as handle:
        return list(csv.DictReader(handle))


@pytest.mark.parametrize("name", REQUIRED_PASS)
def test_evidence_status_pass(name: str) -> None:
    assert _load(name)["status"] == "PASS"


def test_locks_verify() -> None:
    """API_RUNTIME_V2 was superseded by API_RUNTIME_V2_1 (C-V2-013): the streaming adapter gained an
    empty-chunk guard. The V2 lock file is preserved byte-identical, its live verifier reports
    drift ONLY on that one file, and the successor verifies."""
    successor = json.loads((ROOT / "artifacts/API_RUNTIME_V2_1.lock.json").read_text())
    assert hash_file(ROOT / "artifacts/API_RUNTIME_V2.lock.json") == successor["predecessor_sha256"]
    assert successor["changed_bound_files"] == ["simulation/stream_runtime_v2013.py"]
    with pytest.raises(RuntimeError, match="API_RUNTIME_V2_TAMPER:simulation/stream_runtime_v2013"):
        verifier.verify()
    from scripts.verify_api_runtime_v2_1 import verify as verify_v2_1

    assert verify_v2_1()["status"] == "PASS"
    assert verifier.verify_alert_binding()["status"] == "PASS"


@pytest.mark.parametrize("target", ["api/runtime_v2.py", "artifacts/CAL_V2.json",
                                    "frontend/static/replay/WEARABLE_SIM_V2_REPLAY_V1.json"])
def test_runtime_lock_detects_tamper(target: str, tmp_path: Path) -> None:
    lock = json.loads((ROOT / "artifacts/API_RUNTIME_V2.lock.json").read_text())
    lock["bound_artifacts"][target] = "0" * 64
    shadow = tmp_path / "lock.json"
    shadow.write_text(json.dumps(lock))
    with pytest.raises(RuntimeError, match="TAMPER"):
        verifier._check_bound(json.loads(shadow.read_text()), "API_RUNTIME_V2")


def test_replay_is_deterministic_and_modes_agree() -> None:
    digest = _load("replay_semantic_digest")
    assert digest["all_four_identical"] is True
    assert digest["run_1_equals_run_2"] is True
    assert digest["frontend_path_equals_direct_http"] is True
    assert digest["window_count"] == 93
    assert len(set(digest["fresh_api_process_ids"])) == 2
    assert _load("replay_mode_invariance")["semantic_outputs_identical"] is True
    first = (OUT / "replay_run_1.jsonl").read_bytes()
    assert first == (OUT / "replay_run_2.jsonl").read_bytes()


def test_frontend_e2e_carried_real_waveform_and_identities() -> None:
    e2e = _load("frontend_e2e_evidence")
    assert e2e["waveform"]["samples_per_window"] == 2500
    assert e2e["waveform"]["empty_waveform_shortcut"] is False
    assert e2e["waveform"]["polyline_points_rendered"] == 2500
    assert all(r["monitoring_route_http_status"] == 200 for r in e2e["runs"])
    tiles = e2e["identities_rendered"]
    assert "MODEL_V2_FINAL" in tiles["model_id"] and "CAL_V2" in tiles["calibration_id"]


def test_no_new_fits_or_protected_access_claimed() -> None:
    lock = json.loads((ROOT / "artifacts/API_RUNTIME_V2.lock.json").read_text())
    assert lock["neural_fits_in_this_phase"] == 0
    assert lock["protected_partitions_accessed"] == []
    assert lock["operational_default"] == "MODEL_V1"
    assert lock["public_runtime_model_selector"] is False


def test_registry_transition_and_future_phases_untouched() -> None:
    components = {r["component_id"]: r for r in _rows("component")}
    tasks = {r["task_id"]: r for r in _rows("task")}
    gates = {r["gate_id"]: r for r in _rows("gate")}
    assert components["API_RUNTIME_V2"]["status"] == "FROZEN_RESEARCH_RUNTIME"
    assert tasks["V2-013"]["status"] == "PASS" and gates["V2G12"]["status"] == "PASS"
    assert tasks["V2-014"]["status"] == "NOT_STARTED" and gates["V2G13"]["status"] == "NOT_STARTED"
    for frozen in ("GATEWAY_ARTIFACT_V2", "EXPLAINABILITY_V2"):
        assert components[frozen]["status"].startswith("FROZEN")


def test_predecessor_locks_preserved_byte_identical() -> None:
    for successor, predecessor in (("DASHBOARD_UI_V1_4", "DASHBOARD_UI_V1_3"),
                                   ("E2E_REPLAY_SOFTWARE_V1_3", "E2E_REPLAY_SOFTWARE_V1_2")):
        lock = json.loads((ROOT / f"artifacts/{successor}.lock.json").read_text())
        assert hash_file(ROOT / f"artifacts/{predecessor}.lock.json") == lock["predecessor_sha256"]


def test_protected_artifacts_unchanged_since_entry() -> None:
    baseline = json.loads((OUT / "protected_baseline.json").read_text())["artifacts"]
    for relative, expected in baseline.items():
        assert hash_file(ROOT / relative) == expected, relative
