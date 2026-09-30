from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import yaml

from federated.aggregation import ClientUpdate
from federated.fedavg_runner import (
    choose_best_round,
    flower_reference_parity,
    fresh_initial_state,
    stable_convergence,
)
from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]


def test_real_shaped_flower_reference_parity() -> None:
    state = fresh_initial_state(20260927)
    zero = {key: np.zeros_like(value) for key, value in state.items()}
    updates = [ClientUpdate("SITE_00", 2, zero), ClientUpdate("SITE_01", 6, zero)]
    parity = flower_reference_parity(state, updates)
    assert parity["status"] == "PASS"
    assert parity["maximum_absolute_difference"] == 0.0


def test_best_round_uses_earliest_exact_tie() -> None:
    rows = [
        {"round": 0, "validation_AUPRC": 0.9},
        {"round": 1, "validation_AUPRC": 0.7},
        {"round": 2, "validation_AUPRC": 0.8},
        {"round": 3, "validation_AUPRC": 0.8},
    ]
    assert choose_best_round(rows) == 2


def test_stable_convergence_predicate() -> None:
    rounds = [
        {
            "round": index,
            "validation_AUPRC": 0.4 if index == 0 else 0.5,
            "validation_AUROC": 0.6,
            "validation_BCE": 1.0,
            "finite_state": True,
        }
        for index in range(51)
    ]
    clients = [
        {"round": round_number, "status": "PASS", "update_norm": 1.0}
        for round_number in range(1, 51)
        for _ in range(8)
    ]
    assert stable_convergence(rounds, clients)["stable_convergence"] is True
    rounds[1]["validation_AUPRC"] = 0.4
    for row in rounds[2:]:
        row["validation_AUPRC"] = 0.4
    assert stable_convergence(rounds, clients)["stable_convergence"] is False


def test_pre_result_method_lock_and_exact_training_contract() -> None:
    config = yaml.safe_load((ROOT / "configs/fl_iid_v1.yaml").read_text())
    assert config["training"] == {
        "clients": 8,
        "clients_per_round": 8,
        "rounds": 50,
        "local_epochs": 1,
        "batch_size": 64,
        "shuffle": True,
        "drop_last": False,
        "num_workers": 0,
        "device": "cpu",
    }
    assert config["optimizer"]["implementation"] == "AdamW"
    assert config["optimizer"]["learning_rate"] == 0.001
    assert config["optimizer"]["weight_decay"] == 0.0001
    assert config["optimizer"]["scheduler"] == "NONE"
    assert config["loss"]["pos_weight"] == 6103 / 3557
    assert config["loss"]["client_specific_weights"] is False
    assert config["evaluation"]["partition"] == "VALIDATION"
    assert config["evaluation"]["calibration"] == "NONE"
    assert config["access"]["INTERNAL_TEST"] == "FORBIDDEN_IN_T025"
    method = json.loads((ROOT / "artifacts/FL_IID_METHOD_V1.lock.json").read_text())
    assert method["status"] == "FROZEN_ENGINEERING_METHOD"
    assert method["outcome_metrics_included"] is False
    for name, path in method["paths"].items():
        assert hash_file(ROOT / path) == method["hashes"][name], name
    assert method["canonical_F12_status"] == "NOT_FROZEN"
