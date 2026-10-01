"""Deterministic matched FedProx runner for T027."""

from __future__ import annotations

import argparse
import copy
import csv
import json
from pathlib import Path
from typing import Any

import numpy as np
import torch

from federated.aggregation import aggregate_weighted_deltas
from federated.client_manifest import SITE_IDS
from federated.evaluation import evaluate_model
from federated.feature_noise import build_noise_bank, transform_population
from federated.fedavg_runner import (
    _write_csv,
    _write_json,
    choose_best_round,
    fresh_initial_state,
    normalized_population,
    set_determinism,
    state_sha,
)
from federated.fedprox_training import train_local_fedprox_epoch
from federated.model_adapter import fresh_model_v1, restore_state, serialize_state
from federated.non_iid_runner import SHUFFLE_NAMESPACE, load_sites
from federated.validation_group_metrics import validation_patient_metrics
from nhm.hashing import hash_file
from training.train_central import load_population

CONDITIONS = {
    "iid": ("FL_IID_FEDPROX_V1", "CLIENTS_IID_V1.csv"),
    "label": ("FL_LABEL_FEDPROX_V1", "NONIID_LABEL_V1.csv"),
    "quantity": ("FL_QUANTITY_FEDPROX_V1", "NONIID_QUANTITY_V1.csv"),
    "feature": ("FL_FEATURE_FEDPROX_V1", "NONIID_FEATURE_V1.csv"),
    "combined": ("FL_COMBINED_FEDPROX_V1", "NONIID_COMBINED_V1.csv"),
}


def _record_ids(root: Path, example_ids: tuple[str, ...]) -> list[str]:
    wanted = set(example_ids)
    mapping: dict[str, str] = {}
    with (root / "manifests/windows/MITDB_WINDOWS_V1.csv").open(newline="") as handle:
        for row in csv.DictReader(handle):
            if row["example_id"] in wanted:
                mapping[row["example_id"]] = row["record_id"]
    if set(mapping) != wanted:
        raise RuntimeError("validation record provenance incomplete")
    return [mapping[example] for example in example_ids]


def _checkpoint(path: Path, state: dict[str, np.ndarray], metadata: dict[str, Any]) -> None:
    model = fresh_model_v1()
    restore_state(model, state)
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save({**metadata, "state_dict": copy.deepcopy(model.state_dict())}, path)


def run_condition(
    root: Path, condition: str, mu: float, *, candidate: bool = False
) -> dict[str, Any]:
    if condition not in CONDITIONS or (candidate and condition != "label"):
        raise ValueError("invalid FedProx condition/candidate scope")
    experiment_id, manifest_name = CONDITIONS[condition]
    manifest_path = root / "manifests/clients" / manifest_name
    sites = load_sites(manifest_path)
    seed = 20260927
    set_determinism(seed)
    train, validation = load_population("TRAIN"), load_population("VALIDATION")
    clean_train = normalized_population(train)
    validation_inputs = normalized_population(validation)
    group_to_site = {group: site for site, groups in sites.items() for group in groups}
    site_indices = {
        site: np.flatnonzero(np.isin(train.participant_group_ids, groups))
        for site, groups in sites.items()
    }
    train_inputs = clean_train
    if condition in {"feature", "combined"}:
        bank, _ = build_noise_bank(root)
        site_for_example = {
            str(example): group_to_site[str(group)]
            for example, group in zip(train.example_ids, train.participant_group_ids, strict=True)
        }
        train_inputs, _ = transform_population(
            np.asarray(train.waveforms, dtype=np.float64), train.example_ids, site_for_example, bank
        )
    pos_weight = float(np.sum(train.labels == 0) / np.sum(train.labels == 1))
    global_state = fresh_initial_state(seed)
    round0_sha = state_sha(global_state)
    model = fresh_model_v1()
    restore_state(model, global_state)
    metrics0, _, _ = evaluate_model(
        model,
        validation_inputs,
        validation.labels,
        validation.participant_group_ids,
        pos_weight=pos_weight,
        partition="VALIDATION",
    )
    server_payload = len(serialize_state(global_state))
    rounds: list[dict[str, Any]] = [
        {
            "round": 0,
            "client_count": 0,
            "total_examples": 0,
            "training_weighted_mean_loss": "",
            "validation_windows": validation.labels.size,
            "validation_AUPRC": metrics0["AUPRC"],
            "validation_AUROC": metrics0["AUROC"],
            "validation_raw_F1_at_0_5": metrics0["pooled_F1"],
            "validation_patient_macro_F1_at_0_5": metrics0["patient_macro_F1"],
            "validation_BCE": metrics0["BCE"],
            "global_state_sha256": round0_sha,
            "bytes_received": 0,
            "bytes_sent": 0,
            "finite_state": True,
            "selected_best_so_far": False,
        }
    ]
    clients: list[dict[str, Any]] = []
    states = {0: copy.deepcopy(global_state)}
    for round_number in range(1, 51):
        updates, losses = [], []
        for site in SITE_IDS:
            indices = site_indices[site]
            result = train_local_fedprox_epoch(
                global_state=global_state,
                inputs=train_inputs[indices],
                labels=train.labels[indices],
                site_id=site,
                round_number=round_number,
                experiment_id=SHUFFLE_NAMESPACE,
                base_seed=seed,
                batch_size=64,
                learning_rate=0.001,
                weight_decay=0.0001,
                pos_weight=pos_weight,
                mu=mu,
            )
            updates.append(result.update)
            losses.append((result.mean_loss, result.examples_seen))
            site_labels = train.labels[indices]
            clients.append(
                {
                    "round": round_number,
                    "site_id": site,
                    "num_examples": result.examples_seen,
                    "positive_examples": int(np.sum(site_labels == 1)),
                    "negative_examples": int(np.sum(site_labels == 0)),
                    "shuffle_seed": result.shuffle_seed,
                    "batch_count": result.batch_count,
                    "local_epoch": 1,
                    "optimizer": "AdamW",
                    "learning_rate": 0.001,
                    "weight_decay": 0.0001,
                    "mu": mu,
                    "local_training_loss": result.mean_loss,
                    "update_norm": result.update_norm,
                    "update_bytes": result.update_bytes,
                    "status": "PASS",
                }
            )
        global_state, _ = aggregate_weighted_deltas(global_state, updates)
        if not all(np.isfinite(value).all() for value in global_state.values()):
            raise RuntimeError("nonfinite FedProx state")
        states[round_number] = copy.deepcopy(global_state)
        model = fresh_model_v1()
        restore_state(model, global_state)
        metrics, _, _ = evaluate_model(
            model,
            validation_inputs,
            validation.labels,
            validation.participant_group_ids,
            pos_weight=pos_weight,
            partition="VALIDATION",
        )
        prior = max(
            [float(row["validation_AUPRC"]) for row in rounds if row["round"] >= 1] + [-1.0]
        )
        total = sum(update.num_examples for update in updates)
        rounds.append(
            {
                "round": round_number,
                "client_count": 8,
                "total_examples": total,
                "training_weighted_mean_loss": sum(loss * count for loss, count in losses) / total,
                "validation_windows": validation.labels.size,
                "validation_AUPRC": metrics["AUPRC"],
                "validation_AUROC": metrics["AUROC"],
                "validation_raw_F1_at_0_5": metrics["pooled_F1"],
                "validation_patient_macro_F1_at_0_5": metrics["patient_macro_F1"],
                "validation_BCE": metrics["BCE"],
                "global_state_sha256": state_sha(global_state),
                "bytes_received": sum(row["update_bytes"] for row in clients[-8:]),
                "bytes_sent": server_payload * 8,
                "finite_state": True,
                "selected_best_so_far": float(metrics["AUPRC"]) > prior,
            }
        )
    best_round = choose_best_round(rounds)
    best_state = states[best_round]
    best_model = fresh_model_v1()
    restore_state(best_model, best_state)
    best_metrics, logits, probabilities = evaluate_model(
        best_model,
        validation_inputs,
        validation.labels,
        validation.participant_group_ids,
        pos_weight=pos_weight,
        partition="VALIDATION",
    )
    group_metrics = validation_patient_metrics(
        validation.labels,
        probabilities,
        validation.participant_group_ids,
        record_ids=_record_ids(root, validation.example_ids),
    )
    predictions = [
        {
            "example_id": str(example),
            "participant_group_id": str(group),
            "label": int(label),
            "raw_logit": format(float(logit), ".17g"),
            "raw_sigmoid_probability": format(float(probability), ".17g"),
            "prediction_at_0_5": int(probability >= 0.5),
            "round": best_round,
        }
        for example, group, label, logit, probability in zip(
            validation.example_ids,
            validation.participant_group_ids,
            validation.labels,
            logits,
            probabilities,
            strict=True,
        )
    ]
    diagnostics, defined = {}, []
    for site in SITE_IDS:
        indices = site_indices[site]
        site_metrics, _, _ = evaluate_model(
            best_model,
            clean_train[indices],
            train.labels[indices],
            train.participant_group_ids[indices],
            pos_weight=pos_weight,
            partition="SITE_LOCAL_TRAIN_DIAGNOSTIC",
        )
        if len(np.unique(train.labels[indices])) < 2:
            site_metrics["AUPRC"] = None
        else:
            defined.append(float(site_metrics["AUPRC"]))
        diagnostics[site] = {**site_metrics, "label": "SITE_LOCAL_CLEAN_TRAIN_DIAGNOSTIC"}
    local_summary = {
        "defined_AUPRC_sites": len(defined),
        "undefined_AUPRC_sites": 8 - len(defined),
        "mean_AUPRC": float(np.mean(defined)) if defined else None,
        "median_AUPRC": float(np.median(defined)) if defined else None,
        "minimum_AUPRC": float(np.min(defined)) if defined else None,
        "label": "SITE_LOCAL_CLEAN_TRAIN_DIAGNOSTIC",
        "held_out_client_generalization_claim": False,
    }
    token = str(mu).replace(".", "p")
    if candidate:
        out_dir = root / "reports/t027/candidates"
        prefix = f"mu_{token}"
        checkpoint_path = (
            root / f"checkpoints/federated/fedprox_candidates/LABEL_mu_{token}_best.pt"
        )
    else:
        out_dir = root / "reports/t027/comparisons"
        prefix = condition
        checkpoint_path = root / f"checkpoints/federated/{experiment_id}_best.pt"
    _write_csv(out_dir / f"{prefix}_rounds.csv", rounds)
    _write_csv(out_dir / f"{prefix}_client_rounds.csv", clients)
    _write_csv(out_dir / f"{prefix}_validation_predictions.csv", predictions)
    _write_json(out_dir / f"{prefix}_validation_patient_metrics.json", group_metrics)
    metadata = {
        "checkpoint_id": experiment_id,
        "algorithm": "FedProx",
        "mu": mu,
        "round": best_round,
        "validation_AUPRC": best_metrics["AUPRC"],
        "manifest_sha256": hash_file(manifest_path),
        "F12_lock_sha256": hash_file(root / "artifacts/FL_CONFIG_V1.lock.json"),
        "initialization_id": "FL_INIT_V1",
        "transport_id": "FL_STATE_TRANSPORT_V1",
        "aggregation_id": "SAMPLE_COUNT_WEIGHTED_MODEL_DELTA_V1",
    }
    _checkpoint(checkpoint_path, best_state, metadata)
    report = {
        "condition": condition,
        "experiment_id": experiment_id,
        "mu": mu,
        "manifest_sha256": hash_file(manifest_path),
        "round_0_state_sha256": round0_sha,
        "round_0_validation": metrics0,
        "best_round": best_round,
        "best_validation": best_metrics,
        "round_50_AUPRC": rounds[-1]["validation_AUPRC"],
        "validation_patient_metrics": group_metrics,
        "site_local_clean_train_diagnostics": diagnostics,
        "site_local_clean_train_summary": local_summary,
        "logical_payload_bytes": sum(
            int(row["bytes_sent"]) + int(row["bytes_received"]) for row in rounds
        ),
        "client_updates": len(clients),
        "finite": True,
        "checkpoint": str(checkpoint_path.relative_to(root)),
        "status": "PASS",
    }
    _write_json(out_dir / f"{prefix}_result.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("condition", choices=CONDITIONS)
    parser.add_argument("--mu", type=float, required=True)
    parser.add_argument("--candidate", action="store_true")
    args = parser.parse_args()
    result = run_condition(
        Path(__file__).resolve().parents[1], args.condition, args.mu, candidate=args.candidate
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "condition": args.condition,
                "mu": args.mu,
                "best_round": result["best_round"],
            }
        )
    )
