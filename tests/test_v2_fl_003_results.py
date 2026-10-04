"""V2-FL-003 post-result tests: accounting, selection/lock consistency and chronology,
reconstruction, checkpoints (Git-tracked), comparison completeness, firewall, replay, registry."""

from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path

import numpy as np
import pytest
import torch

from federated.fedavg_runner import choose_best_round
from federated.model_v2_fedprox import CANDIDATES, MACRO_ID, WORST_ID, select_mu
from federated.model_v2_fedprox_runner import mu_token, run_key
from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_fl_003"
if not (ROOT / "artifacts/FEDPROX_MU_V2.lock.json").exists():  # pre-selection chronology
    pytest.skip("FEDPROX_MU_V2 not yet frozen", allow_module_level=True)
LOCK = json.loads((ROOT / "artifacts/FEDPROX_MU_V2.lock.json").read_text())
MU = float(LOCK["selected_mu"])
RUNS = [("label", m, "candidate") for m in CANDIDATES] + [
    (c, MU, "transfer") for c in ("iid", "quantity", "feature", "combined")]


def _j(name: str) -> dict:
    return json.loads((OUT / name).read_text())


def _rows(path: Path) -> list[dict]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _result(condition: str, mu: float, role: str) -> dict:
    return json.loads((OUT / run_key(condition, mu, role)[1] / "result.json").read_text())


@pytest.mark.parametrize(("condition", "mu", "role"), RUNS)
def test_fifty_rounds_four_hundred_updates_finite_and_round0(condition, mu, role) -> None:
    result = _result(condition, mu, role)
    stability = result["stability"]
    assert stability["rounds_completed"] == 50 and stability["client_updates_received"] == 400
    assert stability["failed_clients"] == 0 and stability["nonfinite_tensor_count"] == 0
    assert result["round_0_state_sha256"] == (
        "6a2923ca87793fb78571b4cffad4026f8b4ce99d9dfcb3abe885e259c68a572f")
    assert result["round_0_validation"]["AUPRC"] == 0.25769234928353735
    sub = run_key(condition, mu, role)[1]
    rounds = _rows(OUT / sub / "round_log.csv")
    assert choose_best_round(rounds) == result["best_round"]
    assert len(_rows(OUT / sub / "client_rounds.csv")) == 400


@pytest.mark.parametrize(("condition", "mu", "role"), RUNS)
def test_checkpoints_are_present_hashed_and_git_tracked(condition, mu, role) -> None:
    result = _result(condition, mu, role)
    for key in ("best_checkpoint", "round_50_checkpoint"):
        assert hash_file(ROOT / result[key]) == result[f"{key}_sha256"]
        tracked = subprocess.run(["git", "ls-files", "--error-unmatch", result[key]], cwd=ROOT,
                                 capture_output=True, check=False).returncode
        assert tracked == 0, result[key]
    payload = torch.load(ROOT / result["best_checkpoint"], map_location="cpu",
                         weights_only=False)
    assert payload["mu"] == mu and payload["calibration"] == "NONE"
    assert payload["supersedes_model_v2_final"] is False


def test_selection_rule_reproduces_and_matches_the_lock() -> None:
    rows = []
    for mu in CANDIDATES:
        r = _result("label", mu, "candidate")
        s = r["validation_patient_summary"]
        assert s["finite_AUPRC_patients"] == 7
        rows.append({"mu": mu, MACRO_ID: s[MACRO_ID], WORST_ID: s[WORST_ID],
                     "best_global_validation_AUPRC": r["best_validation"]["AUPRC"]})
    baseline = json.loads((ROOT / "reports/model_v2/v2_fl_002/"
                           "label_validation_patient_metrics.json").read_text())[WORST_ID]
    selection = select_mu(rows, baseline)
    assert selection["selected_mu"] == MU == _j("selection/selection.json")["selected_mu"]
    assert LOCK["status"] == "FROZEN_ENGINEERING_METHOD" and LOCK["human_override"] is False
    assert LOCK["selected_before_cross_condition_runs"] is True
    assert LOCK["candidate_set"] == [0.001, 0.01, 0.1] and 0.0 not in LOCK["candidate_set"]
    assert LOCK["supersedes_or_reuses_FEDPROX_MU_V1"] is False
    for mu in CANDIDATES:
        r = _result("label", mu, "candidate")
        assert LOCK["candidate_checkpoint_sha256"][str(mu)]["best_checkpoint_sha256"] == r[
            "best_checkpoint_sha256"]


def test_label_comparison_reuses_the_selected_candidate_without_retraining() -> None:
    alias = _j("selection/label_alias.json")
    assert alias["retrained"] is False and alias["selected_mu"] == MU
    assert not (OUT / "transfer/label").exists()
    assert alias["alias_of"].endswith(f"candidates/mu_{mu_token(MU)}/result.json")


def test_accounting_matches_expected_2800() -> None:
    accounting = _j("accounting_audit.json")
    assert accounting["candidates"]["updates"] == 1200 and accounting["candidates"]["rounds"] == 150
    assert accounting["transfer"]["updates"] == 1600 and accounting["transfer"]["rounds"] == 200
    assert accounting["total_positive_mu_updates"] == 2800
    assert accounting["round_0_all_FL_INIT_V2"] is True
    assert accounting["selected_label_candidate_retrained"] is False


def test_comparison_covers_five_conditions_with_patient_level_detail() -> None:
    comparison = _j("fedavg_vs_fedprox_comparison.json")
    assert set(comparison["conditions"]) == {"iid", "label", "quantity", "feature", "combined"}
    for entry in comparison["conditions"].values():
        for method in ("FedAvg", "FedProx"):
            assert {"best_round", "best_AUPRC", "round_50_AUPRC", "AUROC", "F1_at_0_5",
                    "precision", "sensitivity", "specificity", "BCE", "patient_macro_F1",
                    "validation_patient_mean_AUPRC", "validation_patient_median_AUPRC",
                    "validation_patient_worst_AUPRC", "logical_bytes", "runtime_seconds",
                    "rounds_to_best"} <= set(entry[method])
    patients = _j("patient_level_comparison.json")
    assert patients["validation_patients_are_clients"] is False
    for entry in patients["conditions"].values():
        assert len(entry["FedProx"]) == 7 and len(entry["FedAvg"]) == 7


def test_bootstrap_is_development_only_and_not_a_criterion() -> None:
    boot = _j("paired_bootstrap.json")
    assert boot["B"] == 2000 and boot["seed"] == 20260927
    assert "DEVELOPMENT DIAGNOSTICS ONLY" in boot["wording"]
    criteria = _j("v2flg2_criteria.json")["criteria"]
    assert not any("bootstrap" in k and "significan" in k for k in criteria)


def test_chronology_selection_frozen_before_transfer_runs() -> None:
    chronology = _j("chronology_audit.json")
    assert chronology["status"] == "PASS" and chronology["frozen_before_transfer_runs"] is True
    assert chronology["selection_freeze_commit"] != chronology["method_commit"]
    assert _j("mu0_equivalence.json")["status"] == "PASS"


def test_criteria_firewall_protected_and_replay() -> None:
    criteria = _j("v2flg2_criteria.json")
    flags = criteria["criteria"]
    if flags["regression"] == "PENDING_STAGE1":
        assert all(v is True for k, v in flags.items() if k != "regression")
    else:
        assert criteria["status"] == "PASS" and all(v is True for v in flags.values())
    firewall = _j("heldout_firewall_audit.json")
    assert firewall["status"] == "PASS" and firewall["INTERNAL_TEST_accessed"] is False
    assert not (firewall["CALIBRATION_accessed"] or firewall["INCART_accessed"]
                or firewall["BIDMC_accessed"])
    assert firewall["NSTDB_only_as_pure_noise_training_resource"] is True
    assert _j("protected_artifact_audit.json")["status"] == "PASS"
    assert _j("method_immutability_audit.json")["status"] == "PASS"
    for name in ("replay_verification_run_1.json", "replay_verification_run_2.json"):
        data = _j(name)
        assert data["status"] == "PASS" and len(data["runs"]) == 7
        assert data["selection_matches_lock"] and data["mu0_repeat_in_fresh_process"][
            "exact_match"]


def test_predictions_are_raw_sigmoid() -> None:
    for condition, mu, role in RUNS:
        rows = _rows(OUT / run_key(condition, mu, role)[1] / "validation_predictions.csv")
        logits = np.array([float(r["raw_logit"]) for r in rows])
        probs = np.array([float(r["raw_sigmoid_probability"]) for r in rows])
        np.testing.assert_allclose(probs, 1 / (1 + np.exp(-logits)), atol=1e-6)
        assert len(rows) == 2880


def test_registry_transition_and_later_phases_not_started() -> None:
    def rows(name: str) -> list[dict]:
        return _rows(ROOT / f"manifests/model_v2/{name}_registry_v1.csv")

    tasks = {r["task_id"]: r for r in rows("task")}
    gates = {r["gate_id"]: r for r in rows("gate")}
    comps = {r["component_id"]: r for r in rows("component")}
    assert tasks["V2-FL-003"]["status"] == "PASS" and gates["V2FLG2"]["status"] == "PASS"
    for later in ("V2-FL-EVAL-001", "V2-FL-004", "V2-FL-005", "V2-014"):
        assert tasks[later]["status"] == "NOT_STARTED"
    assert comps["FEDPROX_MU_V2"]["status"] == "FROZEN_ENGINEERING_METHOD"
    assert comps["MODEL_V2_FL_PROTOCOL_V2"]["status"] == "FROZEN_RESEARCH_PROTOCOL_SUCCESSOR"
