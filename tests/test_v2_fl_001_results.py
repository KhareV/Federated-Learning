"""V2-FL-001 post-result tests: reconstruction of the selected round, evidence integrity,
checkpoint identity, firewall, preserved lineage and registry transition."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import pytest
import torch

from federated.fedavg_runner import choose_best_round
from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_fl_001"


def _j(name: str) -> dict:
    return json.loads((OUT / name).read_text())


def _rows(path: Path) -> list[dict]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def test_fifty_rounds_and_four_hundred_updates_accounted_for() -> None:
    result = _j("fl_iid_model_v2_result.json")
    stability = result["stability"]
    assert stability["rounds_completed"] == 50 and stability["client_updates_received"] == 400
    assert stability["failed_clients"] == 0 and stability["nonfinite_tensor_count"] == 0
    assert stability["aggregation_failures"] == 0
    clients = _rows(OUT / "client_rounds.csv")
    assert len(clients) == 400 and all(r["status"] == "PASS" for r in clients)
    assert {r["local_epoch"] for r in clients} == {"1"}
    rounds = _rows(OUT / "round_log.csv")
    assert [int(r["round"]) for r in rounds] == list(range(51))
    assert all(r["total_examples"] == "9660" for r in rounds[1:])


def test_best_round_reconstructs_from_round_log_with_earliest_tie_rule() -> None:
    result = _j("fl_iid_model_v2_result.json")
    rounds = _rows(OUT / "round_log.csv")
    assert choose_best_round(rounds) == result["best_round"]
    best = next(r for r in rounds if int(r["round"]) == result["best_round"])
    assert float(best["validation_AUPRC"]) == result["best_validation"]["AUPRC"]


def test_initialization_fresh_and_central_checkpoint_not_loaded() -> None:
    result = _j("fl_iid_model_v2_result.json")
    audit = _j("initialization_audit.json")
    assert result["central_checkpoint_loaded_as_initialization"] is False
    assert result["round_0_state_sha256"] == audit["round_0_state_sha256"]
    assert result["round_0_state_sha256"] != result["trained_MODEL_V2_FINAL_state_sha256"]
    assert audit["identical"] is True
    assert _rows(OUT / "round_log.csv")[0]["global_state_sha256"] == audit["round_0_state_sha256"]


def test_best_checkpoint_hash_and_content_are_a_new_artifact() -> None:
    result = _j("fl_iid_model_v2_result.json")
    path = ROOT / result["best_checkpoint"]
    assert hash_file(path) == result["best_checkpoint_sha256"]
    assert hash_file(ROOT / "checkpoints/MODEL_V2_FINAL.pt") != result["best_checkpoint_sha256"]
    payload = torch.load(path, map_location="cpu", weights_only=False)
    assert payload["calibration"] == "NONE" and payload["supersedes_model_v2_final"] is False
    assert payload["round"] == result["best_round"] and len(payload["state_dict"]) == 92


def test_predictions_are_raw_sigmoid_without_calibration() -> None:
    rows = _rows(OUT / "validation_predictions_best_round.csv")
    logits = np.array([float(r["raw_logit"]) for r in rows])
    probs = np.array([float(r["raw_sigmoid_probability"]) for r in rows])
    np.testing.assert_allclose(probs, 1 / (1 + np.exp(-logits)), atol=1e-6)  # float32 sigmoid
    assert len(rows) == 2880
    result = _j("fl_iid_model_v2_result.json")
    assert result["CAL_V2_applied"] is False and result["FL_calibration"] == "NONE"


def test_client_manifest_reused_exactly() -> None:
    result = _j("fl_iid_model_v2_result.json")
    assert result["client_manifest_sha256"] == (
        "80f38fa25c508f9b4e2a4fd49e29c4c8d0034443ec67f7c24bc0954912b6c32a")
    assert _j("client_manifest_audit.json")["manifest_regenerated"] is False


def test_firewall_and_protected_audits_pass() -> None:
    firewall = _j("heldout_firewall_audit.json")
    assert firewall["status"] == "PASS"
    assert set(firewall["partitions_accessed"]) <= {"TRAIN", "VALIDATION"}
    assert _j("protected_artifact_audit.json")["status"] == "PASS"
    assert _j("method_immutability_audit.json")["status"] == "PASS"


@pytest.mark.parametrize(
    "name", ["replay_verification_run_1.json", "replay_verification_run_2.json"])
def test_fresh_process_replays_pass(name: str) -> None:
    data = _j(name)
    assert data["status"] == "PASS" and data["validation_predictions_replayed_identically"]


def test_site_local_diagnostics_are_labeled_train_diagnostics() -> None:
    summary = _j("fl_iid_model_v2_result.json")["site_local_train_summary"]
    assert summary["label"] == "SITE_LOCAL_TRAIN_DIAGNOSTIC"
    assert summary["held_out_client_generalization_claim"] is False


def test_registry_transition_and_future_phases_not_started() -> None:
    def rows(name: str) -> list[dict]:
        return _rows(ROOT / f"manifests/model_v2/{name}_registry_v1.csv")

    tasks = {r["task_id"]: r for r in rows("task")}
    gates = {r["gate_id"]: r for r in rows("gate")}
    comps = {r["component_id"]: r for r in rows("component")}
    outcome = _j("decision.json")["outcome"]
    assert tasks["V2-FL-001"]["status"] == outcome.split("_")[0]  # PASS / FAIL
    assert gates["V2FLG0"]["status"] == tasks["V2-FL-001"]["status"]
    assert tasks["V2-FL-002"]["status"] in {"NOT_STARTED", "PASS"}  # run after V2-FL-001
    assert tasks["V2-FL-003"]["status"] in {"NOT_STARTED", "PASS"}  # run after V2-FL-001
    assert comps["MODEL_V2_FL_PROTOCOL_V1"]["status"].startswith("FROZEN")
    assert comps["FL_INIT_V2"]["status"].startswith("FROZEN")
    assert comps["FL_IID_MODEL_V2_V1"]["status"].startswith("FROZEN")
    assert "FL_STATE_TRANSPORT_V2" not in comps
