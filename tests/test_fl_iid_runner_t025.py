from __future__ import annotations

import numpy as np

from federated.aggregation import ClientUpdate
from federated.fedavg_runner import (
    choose_best_round,
    flower_reference_parity,
    fresh_initial_state,
    stable_convergence,
)


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

