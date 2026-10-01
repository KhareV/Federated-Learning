#!/usr/bin/env python3
"""Generate pre-candidate T027 evidence and lock the FedProx method."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np
import torch
from sklearn.metrics import average_precision_score
from torch import nn

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from federated.aggregation import aggregate_weighted_deltas  # noqa: E402
from federated.client_manifest import SITE_IDS  # noqa: E402
from federated.fedavg_runner import (  # noqa: E402
    fresh_initial_state,
    normalized_population,
    state_sha,
)
from federated.fedprox_training import proximal_penalty, train_local_fedprox_epoch  # noqa: E402
from federated.local_training import train_local_epoch  # noqa: E402
from federated.model_adapter import fresh_model_v1  # noqa: E402
from federated.non_iid_runner import SHUFFLE_NAMESPACE, load_sites  # noqa: E402
from federated.validation_group_metrics import validation_patient_metrics  # noqa: E402
from nhm.hashing import hash_file  # noqa: E402
from training.train_central import load_population  # noqa: E402


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def mu_zero_unit() -> dict[str, object]:
    torch.manual_seed(20260927)
    base = fresh_model_v1()
    prox = fresh_model_v1()
    prox.load_state_dict(base.state_dict())
    signals = torch.linspace(-1, 1, 5000, dtype=torch.float32).reshape(2, 1, 2500)
    targets = torch.tensor([[0.0], [1.0]])
    criterion = nn.BCEWithLogitsLoss(pos_weight=torch.tensor([6103 / 3557]))
    base_loss = criterion(base(signals), targets)
    snapshot = {name: parameter.detach().clone() for name, parameter in prox.named_parameters()}
    prox_loss = criterion(prox(signals), targets) + 0.0 * proximal_penalty(prox, snapshot)
    base_loss.backward()
    prox_loss.backward()
    differences = [
        float(torch.max(torch.abs(a.grad - b.grad)).item())
        for a, b in zip(base.parameters(), prox.parameters(), strict=True)
    ]
    return {
        "FedAvg_BCE_loss": float(base_loss.item()),
        "FedProx_mu_zero_loss": float(prox_loss.item()),
        "loss_absolute_difference": abs(float(base_loss.item()) - float(prox_loss.item())),
        "maximum_gradient_difference": max(differences),
        "status": "PASS"
        if base_loss.item() == prox_loss.item() and max(differences) == 0
        else "FAIL",
    }


def mu_zero_round() -> dict[str, object]:
    train = load_population("TRAIN")
    inputs = normalized_population(train)
    sites = load_sites(ROOT / "manifests/clients/NONIID_LABEL_V1.csv")
    initial = fresh_initial_state(20260927)
    pos_weight = float(np.sum(train.labels == 0) / np.sum(train.labels == 1))
    fedavg, fedprox = [], []
    for site in SITE_IDS:
        indices = np.flatnonzero(np.isin(train.participant_group_ids, sites[site]))
        common = dict(
            global_state=initial,
            inputs=inputs[indices],
            labels=train.labels[indices],
            site_id=site,
            round_number=1,
            experiment_id=SHUFFLE_NAMESPACE,
            base_seed=20260927,
            batch_size=64,
            learning_rate=0.001,
            weight_decay=0.0001,
            pos_weight=pos_weight,
        )
        fedavg.append(train_local_epoch(**common).update)
        fedprox.append(train_local_fedprox_epoch(**common, mu=0.0).update)
    avg_state, _ = aggregate_weighted_deltas(initial, fedavg)
    prox_state, _ = aggregate_weighted_deltas(initial, fedprox)
    maximum = max(
        float(
            np.max(
                np.abs(
                    np.asarray(avg_state[key], dtype=np.float64)
                    - np.asarray(prox_state[key], dtype=np.float64)
                ),
                initial=0.0,
            )
        )
        for key in avg_state
    )
    with (ROOT / "reports/t026/label_rounds.csv").open(newline="") as handle:
        expected = next(
            row["global_state_sha256"] for row in csv.DictReader(handle) if row["round"] == "1"
        )
    return {
        "expected_T026_LABEL_round1_sha256": expected,
        "FedAvg_replay_sha256": state_sha(avg_state),
        "FedProx_mu_zero_sha256": state_sha(prox_state),
        "maximum_absolute_difference": maximum,
        "status": "PASS"
        if expected == state_sha(avg_state) == state_sha(prox_state) and maximum == 0
        else "FAIL",
    }


def baseline() -> dict[str, object]:
    rows = list(csv.DictReader((ROOT / "reports/t026/label_validation_predictions.csv").open()))
    labels = np.asarray([int(row["label"]) for row in rows])
    probabilities = np.asarray([float(row["raw_sigmoid_probability"]) for row in rows])
    groups = np.asarray([row["participant_group_id"] for row in rows])
    example_ids = [row["example_id"] for row in rows]
    wanted = set(example_ids)
    records = {}
    with (ROOT / "manifests/windows/MITDB_WINDOWS_V1.csv").open(newline="") as handle:
        for row in csv.DictReader(handle):
            if row["example_id"] in wanted:
                records[row["example_id"]] = row["record_id"]
    metrics = validation_patient_metrics(
        labels, probabilities, groups, record_ids=[records[x] for x in example_ids]
    )
    global_auprc = float(average_precision_score(labels, probabilities))
    return {
        "checkpoint": "checkpoints/federated/FL_LABEL_SKEW_V1_best.pt",
        "best_round": 49,
        "global_validation_AUPRC": global_auprc,
        "validation_patient_metrics": metrics,
        "worst_guardrail_threshold": metrics["worst_AUPRC"] - 0.05,
        "source_predictions_sha256": hash_file(
            ROOT / "reports/t026/label_validation_predictions.csv"
        ),
        "status": "PASS",
    }


def main() -> None:
    unit, full, base = mu_zero_unit(), mu_zero_round(), baseline()
    if unit["status"] != "PASS" or full["status"] != "PASS":
        raise RuntimeError("FEDPROX_MU_ZERO_MISMATCH")
    write_json(
        ROOT / "reports/t027/mu_zero_equivalence.json",
        {"unit": unit, "full_round": full, "status": "PASS"},
    )
    write_json(ROOT / "reports/t027/label_fedavg_selection_baseline.json", base)
    write_json(
        ROOT / "reports/t027/freeze_map_reconciliation.json",
        {
            "source_conceptual_FedProx_freeze_exists": True,
            "repository_canonical_numbering_differs": True,
            "canonical_FedProx_Fxx_row_exists": False,
            "FL_config_freeze": {"id": "F12", "version": "FL_CONFIG_V1", "status": "FROZEN"},
            "privacy_freeze": {"id": "F13", "version": "SECAGG_CONFIG_V1", "status": "NOT_FROZEN"},
            "selected_mu_component_lock": "FEDPROX_MU_V1",
            "existing_Fxx_repurposed": False,
        },
    )
    bound = [
        "configs/fedprox_v1.yaml",
        "configs/fedprox_selection_semantics_v1.yaml",
        "artifacts/FL_CONFIG_V1.lock.json",
        "manifests/clients/NONIID_LABEL_V1.csv",
        "configs/fl_init_v1.yaml",
        "federated/fedprox_training.py",
        "federated/fedprox_runner.py",
        "federated/fedprox_selection.py",
        "federated/validation_group_metrics.py",
        "reports/t027/mu_zero_equivalence.json",
        "reports/t027/label_fedavg_selection_baseline.json",
    ]
    lock = {
        "lock_id": "FEDPROX_METHOD_V1",
        "status": "FROZEN_PRE_CANDIDATE_METHOD",
        "candidate_order": [0.001, 0.01, 0.1],
        "tuning_condition": "FL_LABEL_SKEW_V1",
        "guardrail_absolute_AUPRC": 0.05,
        "tie_policy": ["higher_macro", "higher_worst", "higher_global", "smaller_mu"],
        "bound_artifacts": {path: hash_file(ROOT / path) for path in bound},
    }
    write_json(ROOT / "artifacts/FEDPROX_METHOD_V1.lock.json", lock)
    print(
        json.dumps(
            {
                "status": "PASS",
                "mu_zero_round": full["FedProx_mu_zero_sha256"],
                "validation_groups": base["validation_patient_metrics"]["patient_groups"],
            }
        )
    )


if __name__ == "__main__":
    main()
