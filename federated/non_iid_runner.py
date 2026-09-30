"""Matched deterministic FedAvg runner for the four frozen T026 conditions."""

from __future__ import annotations

import argparse
import copy
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import torch
import yaml

from federated.aggregation import aggregate_weighted_deltas
from federated.client_manifest import SITE_IDS
from federated.evaluation import evaluate_model
from federated.feature_noise import build_noise_bank, transform_population
from federated.fedavg_runner import (
    _write_csv,
    _write_json,
    choose_best_round,
    flower_reference_parity,
    fresh_initial_state,
    normalized_population,
    set_determinism,
    state_sha,
)
from federated.local_training import train_local_epoch
from federated.model_adapter import fresh_model_v1, restore_state, serialize_state
from nhm.hashing import hash_file
from training.train_central import load_population

CONDITIONS = {
    "label": ("FL_LABEL_SKEW_V1", "NONIID_LABEL_V1.csv"),
    "quantity": ("FL_QUANTITY_SKEW_V1", "NONIID_QUANTITY_V1.csv"),
    "feature": ("FL_FEATURE_NOISE_V1", "NONIID_FEATURE_V1.csv"),
    "combined": ("FL_COMBINED_SKEW_V1", "NONIID_COMBINED_V1.csv"),
}
SHUFFLE_NAMESPACE = "FL_IID_V1"


def load_sites(path: Path) -> dict[str, list[str]]:
    sites: dict[str, list[str]] = defaultdict(list)
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["partition"] != "TRAIN":
                raise ValueError("non-TRAIN client row")
            sites[row["site_id"]].append(row["participant_group_id"])
    if tuple(sorted(sites)) != SITE_IDS:
        raise ValueError("all eight sites required")
    groups = [group for site in SITE_IDS for group in sites[site]]
    if len(groups) != len(set(groups)) or len(groups) != 27:
        raise ValueError("patient closure failure")
    return {site: sorted(sites[site]) for site in SITE_IDS}


def checkpoint(
    path: Path,
    state: dict[str, np.ndarray],
    *,
    experiment_id: str,
    round_number: int,
    auprc: float,
    config_sha: str,
    manifest_sha: str,
) -> None:
    model = fresh_model_v1()
    restore_state(model, state)
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "checkpoint_id": experiment_id,
            "model_architecture_id": "MODEL_V1_ARCHITECTURE_V1",
            "initialization_id": "FL_INIT_V1",
            "FL_config_id": "FL_CONFIG_V1",
            "round": round_number,
            "validation_AUPRC": auprc,
            "config_sha256": config_sha,
            "client_manifest_sha256": manifest_sha,
            "transport_id": "FL_STATE_TRANSPORT_V1",
            "aggregation_id": "SAMPLE_COUNT_WEIGHTED_MODEL_DELTA_V1",
            "state_dict": copy.deepcopy(model.state_dict()),
        },
        path,
    )


def run_condition(root: Path, condition: str) -> dict[str, Any]:
    experiment_id, manifest_name = CONDITIONS[condition]
    config_path = root / "configs/fl_non_iid_v1.yaml"
    config = yaml.safe_load(config_path.read_text())
    manifest_path = root / "manifests/clients" / manifest_name
    sites = load_sites(manifest_path)
    seed = int(config["initialization"]["seed"])
    set_determinism(seed)
    train, validation = load_population("TRAIN"), load_population("VALIDATION")
    clean_train_inputs = normalized_population(train)
    validation_inputs = normalized_population(validation)
    group_to_site = {group: site for site, groups in sites.items() for group in groups}
    site_indices = {
        site: np.flatnonzero(np.isin(train.participant_group_ids, groups))
        for site, groups in sites.items()
    }
    train_inputs = clean_train_inputs
    noise_fixtures: list[dict[str, Any]] = []
    if condition in {"feature", "combined"}:
        bank, _ = build_noise_bank(root)
        site_for_example = {
            str(example): group_to_site[str(group)]
            for example, group in zip(train.example_ids, train.participant_group_ids, strict=True)
        }
        train_inputs, noise_fixtures = transform_population(
            np.asarray(train.waveforms, dtype=np.float64), train.example_ids, site_for_example, bank
        )
    pos_weight = float(np.sum(train.labels == 0) / np.sum(train.labels == 1))
    global_state = fresh_initial_state(seed)
    initial_sha = state_sha(global_state)
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
            "global_state_sha256": initial_sha,
            "bytes_received": 0,
            "bytes_sent": 0,
            "finite_state": True,
            "selected_best_so_far": False,
        }
    ]
    clients: list[dict[str, Any]] = []
    states = {0: copy.deepcopy(global_state)}
    parity: dict[str, Any] | None = None
    for round_number in range(1, 51):
        updates, losses = [], []
        for site in SITE_IDS:
            indices = site_indices[site]
            result = train_local_epoch(
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
            )
            if result.examples_seen != indices.size:
                raise RuntimeError("sample count mismatch")
            updates.append(result.update)
            losses.append((result.mean_loss, result.examples_seen))
            labels = train.labels[indices]
            clients.append(
                {
                    "round": round_number,
                    "site_id": site,
                    "patient_count": len(sites[site]),
                    "num_examples": result.examples_seen,
                    "positive_examples": int(np.sum(labels == 1)),
                    "negative_examples": int(np.sum(labels == 0)),
                    "shuffle_seed": result.shuffle_seed,
                    "batch_count": result.batch_count,
                    "local_epoch": 1,
                    "optimizer": "AdamW",
                    "learning_rate": 0.001,
                    "weight_decay": 0.0001,
                    "local_training_loss": result.mean_loss,
                    "update_norm": result.update_norm,
                    "update_bytes": result.update_bytes,
                    "status": "PASS",
                }
            )
        if round_number == 1:
            parity = flower_reference_parity(global_state, updates)
            if parity["status"] != "PASS":
                raise RuntimeError("aggregation parity")
        global_state, _ = aggregate_weighted_deltas(global_state, updates)
        if not all(np.isfinite(value).all() for value in global_state.values()):
            raise RuntimeError("nonfinite state")
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
        total = sum(update.num_examples for update in updates)
        weighted_loss = sum(loss * count for loss, count in losses) / total
        prior = max(
            [float(row["validation_AUPRC"]) for row in rounds if int(row["round"]) >= 1]
            + [-math.inf]
        )
        rounds.append(
            {
                "round": round_number,
                "client_count": 8,
                "total_examples": total,
                "training_weighted_mean_loss": weighted_loss,
                "validation_windows": validation.labels.size,
                "validation_AUPRC": metrics["AUPRC"],
                "validation_AUROC": metrics["AUROC"],
                "validation_raw_F1_at_0_5": metrics["pooled_F1"],
                "validation_patient_macro_F1_at_0_5": metrics["patient_macro_F1"],
                "validation_BCE": metrics["BCE"],
                "global_state_sha256": state_sha(global_state),
            "bytes_received": sum(int(row["update_bytes"]) for row in clients[-8:]),
                "bytes_sent": server_payload * 8,
                "finite_state": True,
                "selected_best_so_far": float(metrics["AUPRC"]) > prior,
            }
        )
    best_round = choose_best_round(rounds)
    best_row = next(row for row in rounds if int(row["round"]) == best_round)
    best_state = states[best_round]
    config_sha, manifest_sha = hash_file(config_path), hash_file(manifest_path)
    base = experiment_id
    checkpoint(
        root / f"checkpoints/federated/{base}_best.pt",
        best_state,
        experiment_id=experiment_id,
        round_number=best_round,
        auprc=float(best_row["validation_AUPRC"]),
        config_sha=config_sha,
        manifest_sha=manifest_sha,
    )
    checkpoint(
        root / f"checkpoints/federated/{base}_round50.pt",
        states[50],
        experiment_id=experiment_id,
        round_number=50,
        auprc=float(rounds[-1]["validation_AUPRC"]),
        config_sha=config_sha,
        manifest_sha=manifest_sha,
    )
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
    prefix = {
        "label": "label",
        "quantity": "quantity",
        "feature": "feature",
        "combined": "combined",
    }[condition]
    _write_csv(root / f"reports/t026/{prefix}_rounds.csv", rounds)
    _write_csv(root / f"reports/t026/{prefix}_client_rounds.csv", clients)
    _write_csv(root / f"reports/t026/{prefix}_validation_predictions.csv", predictions)
    diagnostics: dict[str, Any] = {}
    defined = []
    for site in SITE_IDS:
        indices = site_indices[site]
        labels = train.labels[indices]
        site_metrics, _, _ = evaluate_model(
            best_model,
            clean_train_inputs[indices],
            labels,
            train.participant_group_ids[indices],
            pos_weight=pos_weight,
            partition="SITE_LOCAL_TRAIN_DIAGNOSTIC",
        )
        if len(np.unique(labels)) < 2:
            site_metrics["AUPRC"] = None
        else:
            defined.append(float(site_metrics["AUPRC"]))
        diagnostics[site] = {**site_metrics, "label": "SITE_LOCAL_CLEAN_TRAIN_DIAGNOSTIC"}
    summary = {
        "defined_AUPRC_sites": len(defined),
        "undefined_AUPRC_sites": 8 - len(defined),
        "mean_AUPRC": float(np.mean(defined)) if defined else None,
        "median_AUPRC": float(np.median(defined)) if defined else None,
        "minimum_AUPRC": float(np.min(defined)) if defined else None,
        "label": "SITE_LOCAL_CLEAN_TRAIN_DIAGNOSTIC",
        "held_out_client_generalization_claim": False,
    }
    total_sent = sum(int(row["bytes_sent"]) for row in rounds)
    total_received = sum(int(row["bytes_received"]) for row in rounds)
    report = {
        "condition": condition,
        "experiment_id": experiment_id,
        "manifest_sha256": manifest_sha,
        "config_sha256": config_sha,
        "round_0_state_sha256": initial_sha,
        "round_0_validation": metrics0,
        "best_round": best_round,
        "best_validation": best_metrics,
        "round_50_AUPRC": rounds[-1]["validation_AUPRC"],
        "client_updates": len(clients),
        "finite": True,
        "aggregation_parity": parity,
        "site_local_clean_train_diagnostics": diagnostics,
        "site_local_clean_train_summary": summary,
        "logical_payload_bytes": total_sent + total_received,
        "noise_fixtures": noise_fixtures,
        "shuffle_seed_namespace": SHUFFLE_NAMESPACE,
        "status": "PASS",
    }
    _write_json(root / f"reports/t026/{prefix}_result.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("condition", choices=CONDITIONS)
    args = parser.parse_args()
    result = run_condition(Path(__file__).resolve().parents[1], args.condition)
    print(
        json.dumps(
            {
                "status": result["status"],
                "condition": args.condition,
                "best_round": result["best_round"],
            }
        )
    )
