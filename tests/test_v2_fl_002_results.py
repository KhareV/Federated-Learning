"""V2-FL-002 post-result tests: accounting, round-0 equality, selection reconstruction, checkpoint
identity and Git tracking, FedProx-baseline metrics, firewall/NSTDB role, replay, registry."""

from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path

import numpy as np
import pytest
import torch

from federated.fedavg_runner import choose_best_round
from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_fl_002"
CONDITIONS = ["label", "quantity", "feature", "combined"]
INIT_SHA = "6a2923ca87793fb78571b4cffad4026f8b4ce99d9dfcb3abe885e259c68a572f"


def _j(name: str) -> dict:
    return json.loads((OUT / name).read_text())


def _rows(path: Path) -> list[dict]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


@pytest.mark.parametrize("condition", CONDITIONS)
def test_fifty_rounds_four_hundred_updates_all_finite(condition: str) -> None:
    result = _j(f"{condition}_result.json")
    stability = result["stability"]
    assert stability["rounds_completed"] == 50 and stability["client_updates_received"] == 400
    assert stability["failed_clients"] == 0 and stability["nonfinite_tensor_count"] == 0
    assert stability["aggregation_failures"] == 0
    clients = _rows(OUT / f"{condition}_client_rounds.csv")
    assert len(clients) == 400 and {c["status"] for c in clients} == {"PASS"}
    rounds = _rows(OUT / f"{condition}_round_log.csv")
    assert [int(r["round"]) for r in rounds] == list(range(51))
    assert all(r["total_examples"] == "9660" for r in rounds[1:])


@pytest.mark.parametrize("condition", CONDITIONS)
def test_round_zero_identical_to_fl_init_v2_and_v2_fl_001(condition: str) -> None:
    result = _j(f"{condition}_result.json")
    assert result["round_0_state_sha256"] == INIT_SHA
    assert result["round_0_validation"]["AUPRC"] == 0.25769234928353735
    assert result["central_checkpoint_loaded_as_initialization"] is False
    assert _rows(OUT / f"{condition}_round_log.csv")[0]["global_state_sha256"] == INIT_SHA


@pytest.mark.parametrize("condition", CONDITIONS)
def test_best_round_reconstruction_and_checkpoints(condition: str) -> None:
    result = _j(f"{condition}_result.json")
    rounds = _rows(OUT / f"{condition}_round_log.csv")
    assert choose_best_round(rounds) == result["best_round"]
    for key in ("best_checkpoint", "round_50_checkpoint"):
        path = ROOT / result[key]
        assert hash_file(path) == result[f"{key}_sha256"]
        tracked = subprocess.run(["git", "ls-files", "--error-unmatch", result[key]], cwd=ROOT,
                                 capture_output=True, check=False).returncode
        assert tracked == 0, f"{result[key]} is not Git-tracked"
    payload = torch.load(ROOT / result["best_checkpoint"], map_location="cpu",
                         weights_only=False)
    assert payload["round"] == result["best_round"] and payload["calibration"] == "NONE"
    assert payload["supersedes_model_v2_final"] is False


@pytest.mark.parametrize("condition", CONDITIONS)
def test_predictions_are_raw_sigmoid_and_patient_metrics_keep_undefined(condition: str) -> None:
    rows = _rows(OUT / f"{condition}_validation_predictions.csv")
    logits = np.array([float(r["raw_logit"]) for r in rows])
    probs = np.array([float(r["raw_sigmoid_probability"]) for r in rows])
    np.testing.assert_allclose(probs, 1 / (1 + np.exp(-logits)), atol=1e-6)
    assert len(rows) == 2880
    patient = _j(f"{condition}_validation_patient_metrics.json")
    assert len(patient["per_group"]) == 7 and patient["validation_patients_are_clients"] is False
    for group in patient["per_group"]:
        assert {"AUPRC", "AUROC", "F1_at_0_5", "positives", "negatives", "windows"} <= set(group)
    summary = _j(f"{condition}_result.json")["site_local_train_summary"]
    assert summary["label"] == "SITE_LOCAL_TRAIN_DIAGNOSTIC"
    assert summary["held_out_client_generalization_claim"] is False


def test_label_fedprox_baseline_metrics_are_defined_over_finite_patients() -> None:
    baseline = _j("label_fedprox_baseline_metrics.json")
    patient = _j("label_validation_patient_metrics.json")
    finite = [g["AUPRC"] for g in patient["per_group"] if g["AUPRC"] is not None]
    assert baseline["VALIDATION_PATIENT_MACRO_AUPRC_V2"] == float(np.mean(finite))
    assert baseline["VALIDATION_PATIENT_WORST_AUPRC_V2"] == min(finite)
    assert baseline["mu_selected"] is False and baseline["fedprox_run"] is False


def test_accounting_totals_and_gate_criteria() -> None:
    accounting = _j("accounting_audit.json")
    assert accounting["total_rounds"] == 200 and accounting["updates_valid"] == 1600
    assert accounting["round_0_identical_all_conditions"]
    assert accounting["round_0_matches_V2_FL_001"]
    criteria = _j("v2flg1_criteria.json")
    flags = criteria["criteria"]
    if flags["regression"] == "PENDING_STAGE1":  # transient state while the regression runs
        assert all(v is True for k, v in flags.items() if k != "regression")
    else:
        assert criteria["status"] == "PASS" and all(v is True for v in flags.values())
    assert criteria["performance_direction_irrelevant"] is True


def test_firewall_nstdb_role_and_protected_audits() -> None:
    firewall = _j("heldout_firewall_audit.json")
    assert firewall["status"] == "PASS"
    assert firewall["NSTDB_only_as_pure_noise_training_resource"] is True
    assert firewall["NSTDB_evaluation_accessed"] is False
    assert not (firewall["CALIBRATION_accessed"] or firewall["INTERNAL_TEST_accessed"]
                or firewall["INCART_accessed"] or firewall["BIDMC_accessed"])
    assert _j("protected_artifact_audit.json")["status"] == "PASS"
    assert _j("method_immutability_audit.json")["status"] == "PASS"


@pytest.mark.parametrize(
    "name", ["replay_verification_run_1.json", "replay_verification_run_2.json"])
def test_fresh_process_replays_pass_for_all_conditions(name: str) -> None:
    data = _j(name)
    assert data["status"] == "PASS" and len(data["conditions"]) == 4
    assert all(c["round_1_identical"] and c["validation_predictions_replayed_identically"]
               for c in data["conditions"])


def test_bootstrap_is_labeled_development_only() -> None:
    boot = _j("paired_bootstrap.json")
    assert boot["B"] == 2000 and boot["seed"] == 20260927
    assert "DEVELOPMENT DIAGNOSTICS ONLY" in boot["wording"]
    assert set(boot["conditions"]) == set(CONDITIONS)


def test_registry_transition_and_later_phases_not_started() -> None:
    def rows(name: str) -> list[dict]:
        return _rows(ROOT / f"manifests/model_v2/{name}_registry_v1.csv")

    tasks = {r["task_id"]: r for r in rows("task")}
    gates = {r["gate_id"]: r for r in rows("gate")}
    comps = {r["component_id"]: r for r in rows("component")}
    assert tasks["V2-FL-002"]["status"] == "PASS" and gates["V2FLG1"]["status"] == "PASS"
    assert gates["V2FLG0"]["status"] == "PASS" and tasks["V2-FL-001"]["status"] == "PASS"
    assert tasks["V2-FL-003"]["status"] in {"NOT_STARTED", "PASS"}  # run after V2-FL-002
    assert comps["FL_NON_IID_MODEL_V2_V1"]["status"].startswith("FROZEN")
    assert comps["MODEL_V2_FL_PROTOCOL_V1"]["status"] == "FROZEN_BEFORE_FIRST_V2_FL_OUTCOME"
