"""Real deterministic 50-round whole-patient IID FedAvg runner for T025."""

from __future__ import annotations

import copy
import csv
import json
import math
import os
import random
from collections import OrderedDict, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import torch
import yaml
from flwr.app import Array, ArrayRecord, RecordDict
from flwr.common.serde import recorddict_from_proto, recorddict_to_proto

from federated.aggregation import ClientUpdate, aggregate_weighted_deltas
from federated.client_manifest import CLIENT_MANIFEST_ID, SITE_IDS, read_csv
from federated.evaluation import evaluate_model
from federated.local_training import train_local_epoch
from federated.model_adapter import (
    extract_state,
    fresh_model_v1,
    load_adapter_audit_model,
    restore_state,
    serialize_state,
)
from nhm.hashing import hash_bytes, hash_file
from preprocessing.windowing import NORMALIZATION_EPSILON
from training.train_central import WindowPopulation, load_population

EXPERIMENT_ID = "FL_IID_V1"
INITIALIZATION_ID = "FL_INIT_V1"


def set_determinism(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)
    torch.set_num_threads(max(1, min(4, os.cpu_count() or 1)))


def normalized_population(population: WindowPopulation) -> np.ndarray:
    values = np.asarray(population.waveforms, dtype=np.float64)
    means = np.mean(values, axis=1, keepdims=True)
    scales = np.std(values, axis=1, ddof=0, keepdims=True)
    normalized = (values - means) / (scales + NORMALIZATION_EPSILON)
    if not np.isfinite(normalized).all():
        raise RuntimeError("nonfinite normalized FL input")
    return normalized.astype(np.float32)[:, np.newaxis, :]


def fresh_initial_state(seed: int) -> OrderedDict[str, np.ndarray]:
    set_determinism(seed)
    return extract_state(fresh_model_v1())


def state_sha(state: dict[str, np.ndarray]) -> str:
    return hash_bytes(serialize_state(state))


def _flower_transport_updates(updates: list[ClientUpdate]) -> list[ClientUpdate]:
    transported: list[ClientUpdate] = []
    for update in updates:
        arrays = {key: Array(ndarray=value) for key, value in update.delta.items()}
        records = RecordDict({"delta": ArrayRecord(array_dict=arrays)})
        restored = recorddict_from_proto(recorddict_to_proto(records))["delta"]
        delta = {key: value.numpy() for key, value in restored.items()}
        transported.append(
            ClientUpdate(update.client_id, update.num_examples, delta, update.transport_id)
        )
    return transported


def flower_reference_parity(
    global_state: dict[str, np.ndarray], updates: list[ClientUpdate]
) -> dict[str, Any]:
    reference, _ = aggregate_weighted_deltas(global_state, updates)
    flower_path, _ = aggregate_weighted_deltas(global_state, _flower_transport_updates(updates))
    maximum = 0.0
    for key in reference:
        difference = np.max(
            np.abs(
                np.asarray(reference[key], dtype=np.float64)
                - np.asarray(flower_path[key], dtype=np.float64)
            ),
            initial=0.0,
        )
        maximum = max(maximum, float(difference))
    return {
        "real_shaped_reference_aggregate_sha256": state_sha(reference),
        "Flower_server_aggregate_sha256": state_sha(flower_path),
        "maximum_absolute_difference": maximum,
        "status": "PASS" if maximum == 0.0 else "FAIL",
    }


def load_manifest_sites(path: Path) -> dict[str, list[str]]:
    sites: dict[str, list[str]] = defaultdict(list)
    for row in read_csv(path):
        if row["client_manifest_id"] != CLIENT_MANIFEST_ID or row["partition"] != "TRAIN":
            raise ValueError("T025 client manifest identity/partition mismatch")
        sites[row["site_id"]].append(row["participant_group_id"])
    if tuple(sorted(sites)) != SITE_IDS:
        raise ValueError("T025 requires exactly eight canonical sites")
    return {site: sorted(groups) for site, groups in sites.items()}


def choose_best_round(round_rows: list[dict[str, Any]]) -> int:
    eligible = [row for row in round_rows if int(row["round"]) >= 1]
    if not eligible:
        raise ValueError("no post-training rounds")
    selected = max(
        eligible,
        key=lambda row: (float(row["validation_AUPRC"]), -int(row["round"])),
    )
    return int(selected["round"])


def stable_convergence(
    round_rows: list[dict[str, Any]], client_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    post = [row for row in round_rows if int(row["round"]) >= 1]
    round0 = next(row for row in round_rows if int(row["round"]) == 0)
    best = max(post, key=lambda row: float(row["validation_AUPRC"]))
    improvement = float(best["validation_AUPRC"]) - float(round0["validation_AUPRC"])
    client_counts = defaultdict(int)
    for row in client_rows:
        if row["status"] == "PASS":
            client_counts[int(row["round"])] += 1
    finite_metrics = all(
        math.isfinite(float(row[key]))
        for row in round_rows
        for key in ("validation_AUPRC", "validation_AUROC", "validation_BCE")
    )
    passed = (
        len(post) == 50
        and all(client_counts[round_number] == 8 for round_number in range(1, 51))
        and all(row["finite_state"] for row in post)
        and finite_metrics
        and improvement > 1e-6
    )
    return {
        "rounds_expected": 50,
        "rounds_completed": len(post),
        "clients_expected_per_round": 8,
        "client_updates_expected": 400,
        "client_updates_received": sum(client_counts.values()),
        "failed_clients": 400 - sum(client_counts.values()),
        "nonfinite_tensor_count": sum(not bool(row["finite_state"]) for row in post),
        "nonfinite_metric_count": 0 if finite_metrics else 1,
        "aggregation_failures": 0,
        "round_0_validation_AUPRC": float(round0["validation_AUPRC"]),
        "best_validation_AUPRC": float(best["validation_AUPRC"]),
        "improvement_over_round_0": improvement,
        "best_round": choose_best_round(round_rows),
        "final_round_AUPRC": float(post[-1]["validation_AUPRC"]),
        "minimum_update_norm": min(float(row["update_norm"]) for row in client_rows),
        "maximum_update_norm": max(float(row["update_norm"]) for row in client_rows),
        "stable_convergence": passed,
        "reason": "all predeclared criteria passed" if passed else "predeclared criterion failed",
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _checkpoint(
    path: Path,
    *,
    state: dict[str, np.ndarray],
    round_number: int,
    validation_auprc: float,
    config_sha: str,
    manifest_sha: str,
) -> None:
    model = fresh_model_v1()
    restore_state(model, state)
    payload = {
        "checkpoint_id": "FL_IID_V1",
        "model_architecture_id": "MODEL_V1_ARCHITECTURE_V1",
        "initialization_id": INITIALIZATION_ID,
        "round": round_number,
        "validation_AUPRC": validation_auprc,
        "config_sha256": config_sha,
        "client_manifest_sha256": manifest_sha,
        "preproc_id": "PREPROC_V1",
        "transport_id": "FL_STATE_TRANSPORT_V1",
        "aggregation_id": "SAMPLE_COUNT_WEIGHTED_MODEL_DELTA_V1",
        "state_dict": copy.deepcopy(model.state_dict()),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(payload, path)


def run(root: Path) -> dict[str, Any]:
    config_path = root / "configs/fl_iid_v1.yaml"
    manifest_path = root / "manifests/clients/CLIENTS_IID_V1.csv"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    sites = load_manifest_sites(manifest_path)
    set_determinism(int(config["initialization"]["seed"]))
    train = load_population("TRAIN")
    validation = load_population("VALIDATION")
    train_inputs = normalized_population(train)
    validation_inputs = normalized_population(validation)
    pos_weight = float(np.sum(train.labels == 0) / np.sum(train.labels == 1))
    if not math.isclose(pos_weight, float(config["loss"]["pos_weight"]), rel_tol=0, abs_tol=1e-15):
        raise RuntimeError("global TRAIN pos_weight mismatch")
    site_indices = {
        site: np.flatnonzero(np.isin(train.participant_group_ids, groups))
        for site, groups in sites.items()
    }
    global_state = fresh_initial_state(int(config["initialization"]["seed"]))
    initial_sha = state_sha(global_state)
    trained_state_sha = state_sha(extract_state(load_adapter_audit_model(root)))
    if initial_sha == trained_state_sha:
        raise RuntimeError("central MODEL_V1 checkpoint warm start detected")
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
    round_rows: list[dict[str, Any]] = []
    client_rows: list[dict[str, Any]] = []
    states: dict[int, dict[str, np.ndarray]] = {0: copy.deepcopy(global_state)}
    server_payload = len(serialize_state(global_state))
    round_rows.append(
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
    )
    parity: dict[str, Any] | None = None
    for round_number in range(1, int(config["training"]["rounds"]) + 1):
        updates: list[ClientUpdate] = []
        losses: list[tuple[float, int]] = []
        for site in SITE_IDS:
            indices = site_indices[site]
            result = train_local_epoch(
                global_state=global_state,
                inputs=train_inputs[indices],
                labels=train.labels[indices],
                site_id=site,
                round_number=round_number,
                experiment_id=EXPERIMENT_ID,
                base_seed=int(config["initialization"]["seed"]),
                batch_size=int(config["training"]["batch_size"]),
                learning_rate=float(config["optimizer"]["learning_rate"]),
                weight_decay=float(config["optimizer"]["weight_decay"]),
                pos_weight=pos_weight,
            )
            if result.examples_seen != indices.size:
                raise RuntimeError("client sample-count weight mismatch")
            updates.append(result.update)
            losses.append((result.mean_loss, result.examples_seen))
            labels = train.labels[indices]
            client_rows.append(
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
                    "learning_rate": config["optimizer"]["learning_rate"],
                    "weight_decay": config["optimizer"]["weight_decay"],
                    "local_training_loss": result.mean_loss,
                    "update_norm": result.update_norm,
                    "update_bytes": result.update_bytes,
                    "status": "PASS",
                }
            )
        if round_number == 1:
            parity = flower_reference_parity(global_state, updates)
            if parity["status"] != "PASS":
                raise RuntimeError("Flower/reference aggregation mismatch")
        global_state, _ = aggregate_weighted_deltas(global_state, updates)
        finite = all(
            np.isfinite(value).all()
            for value in global_state.values()
            if np.issubdtype(value.dtype, np.floating)
        )
        if not finite:
            raise RuntimeError("nonfinite global state")
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
        total_examples = sum(update.num_examples for update in updates)
        weighted_loss = sum(loss * count for loss, count in losses) / total_examples
        client_bytes = sum(row["update_bytes"] for row in client_rows[-8:])
        current_best = max(
            [float(row["validation_AUPRC"]) for row in round_rows if int(row["round"]) >= 1]
            + [-math.inf]
        )
        round_rows.append(
            {
                "round": round_number,
                "client_count": len(updates),
                "total_examples": total_examples,
                "training_weighted_mean_loss": weighted_loss,
                "validation_windows": validation.labels.size,
                "validation_AUPRC": metrics["AUPRC"],
                "validation_AUROC": metrics["AUROC"],
                "validation_raw_F1_at_0_5": metrics["pooled_F1"],
                "validation_patient_macro_F1_at_0_5": metrics["patient_macro_F1"],
                "validation_BCE": metrics["BCE"],
                "global_state_sha256": state_sha(global_state),
                "bytes_received": client_bytes,
                "bytes_sent": server_payload * 8,
                "finite_state": True,
                "selected_best_so_far": float(metrics["AUPRC"]) > current_best,
            }
        )
    best_round = choose_best_round(round_rows)
    best_row = next(row for row in round_rows if int(row["round"]) == best_round)
    best_state = states[best_round]
    config_sha = hash_file(config_path)
    manifest_sha = hash_file(manifest_path)
    best_checkpoint = root / "checkpoints/federated/FL_IID_V1_best.pt"
    final_checkpoint = root / "checkpoints/federated/FL_IID_V1_round50.pt"
    _checkpoint(
        best_checkpoint,
        state=best_state,
        round_number=best_round,
        validation_auprc=float(best_row["validation_AUPRC"]),
        config_sha=config_sha,
        manifest_sha=manifest_sha,
    )
    _checkpoint(
        final_checkpoint,
        state=states[50],
        round_number=50,
        validation_auprc=float(round_rows[-1]["validation_AUPRC"]),
        config_sha=config_sha,
        manifest_sha=manifest_sha,
    )
    best_model = fresh_model_v1()
    restore_state(best_model, best_state)
    best_metrics, best_logits, best_probabilities = evaluate_model(
        best_model,
        validation_inputs,
        validation.labels,
        validation.participant_group_ids,
        pos_weight=pos_weight,
        partition="VALIDATION",
    )
    predictions = [
        {
            "example_id": example_id,
            "participant_group_id": group,
            "label": int(label),
            "raw_logit": format(float(logit), ".17g"),
            "raw_sigmoid_probability": format(float(probability), ".17g"),
            "prediction_at_0_5": int(probability >= 0.5),
            "round": best_round,
        }
        for example_id, group, label, logit, probability in zip(
            validation.example_ids,
            validation.participant_group_ids,
            validation.labels,
            best_logits,
            best_probabilities,
            strict=True,
        )
    ]
    prediction_path = root / "reports/t025/fl_iid_validation_predictions.csv"
    _write_csv(prediction_path, predictions)
    diagnostics: dict[str, Any] = {}
    for site in SITE_IDS:
        indices = site_indices[site]
        site_metrics, _, _ = evaluate_model(
            best_model,
            train_inputs[indices],
            train.labels[indices],
            train.participant_group_ids[indices],
            pos_weight=pos_weight,
            partition="SITE_LOCAL_TRAIN_DIAGNOSTIC",
        )
        diagnostics[site] = site_metrics
    round_path = root / "reports/t025/fl_iid_rounds.csv"
    client_round_path = root / "reports/t025/fl_iid_client_rounds.csv"
    _write_csv(round_path, round_rows)
    _write_csv(client_round_path, client_rows)
    stability = stable_convergence(round_rows, client_rows)
    _write_json(root / "reports/t025/stability_audit.json", stability)
    if not stability["stable_convergence"]:
        raise RuntimeError("FEDAVG_NO_LEARNING_SIGNAL")
    if parity is None:
        raise RuntimeError("missing aggregation parity evidence")
    _write_json(root / "reports/t025/aggregation_parity.json", parity)
    _write_json(
        root / "reports/t025/initialization_audit.json",
        {
            "initialization_id": INITIALIZATION_ID,
            "source": "FRESH_MODEL_V1_ARCHITECTURE",
            "seed": config["initialization"]["seed"],
            "central_checkpoint_pretraining": False,
            "round_0_state_sha256": initial_sha,
            "trained_MODEL_V1_state_sha256": trained_state_sha,
            "equal": False,
            "deterministic_reconstruction_sha256": state_sha(
                fresh_initial_state(int(config["initialization"]["seed"]))
            ),
            "status": "PASS",
        },
    )
    local_auprcs = [float(diagnostics[site]["AUPRC"]) for site in SITE_IDS]
    communication = {
        "server_to_client_bytes_per_round": server_payload * 8,
        "client_to_server_bytes_per_round": int(
            sum(int(row["update_bytes"]) for row in client_rows[:8])
        ),
        "total_server_to_client_bytes": sum(int(row["bytes_sent"]) for row in round_rows),
        "total_client_to_server_bytes": sum(
            int(row["bytes_received"]) for row in round_rows
        ),
    }
    communication["total_logical_payload_bytes"] = (
        communication["total_server_to_client_bytes"]
        + communication["total_client_to_server_bytes"]
    )
    report = {
        "experiment_id": EXPERIMENT_ID,
        "initialization_id": INITIALIZATION_ID,
        "client_manifest_id": CLIENT_MANIFEST_ID,
        "client_manifest_sha256": manifest_sha,
        "config_sha256": config_sha,
        "Flower_version": "1.39.0",
        "training": config["training"],
        "optimizer": config["optimizer"],
        "aggregation": config["aggregation"],
        "transport": config["transport"],
        "loss": config["loss"],
        "FL_calibration": "NONE",
        "CAL_V1_applied": False,
        "best_round": best_round,
        "round_0_validation": metrics0,
        "best_validation": best_metrics,
        "round_50_validation_AUPRC": round_rows[-1]["validation_AUPRC"],
        "site_local_train_diagnostics": diagnostics,
        "site_local_train_summary": {
            "mean_AUPRC": float(np.mean(local_auprcs)),
            "median_AUPRC": float(np.median(local_auprcs)),
            "minimum_AUPRC": float(np.min(local_auprcs)),
            "label": "SITE_LOCAL_TRAIN_DIAGNOSTIC",
            "held_out_client_generalization_claim": False,
        },
        "communication": {**communication, "network_traffic_measured": False},
        "stability": stability,
        "claim_boundary": {
            "controlled_simulated_sites": True,
            "real_hospital_claim": False,
            "privacy_guarantee": False,
            "held_out_FL_test_performance": False,
        },
        "status": "PASS",
    }
    _write_json(root / "reports/fl_iid.json", report)
    _write_csv(
        root / "reports/fl_iid.csv",
        [
            {
                "experiment_id": EXPERIMENT_ID,
                "best_round": best_round,
                "round_0_AUPRC": metrics0["AUPRC"],
                "best_AUPRC": best_metrics["AUPRC"],
                "best_AUROC": best_metrics["AUROC"],
                "best_F1_at_0_5": best_metrics["pooled_F1"],
                "best_patient_macro_F1_at_0_5": best_metrics["patient_macro_F1"],
                "best_BCE": best_metrics["BCE"],
                "round_50_AUPRC": round_rows[-1]["validation_AUPRC"],
                "stable_convergence": stability["stable_convergence"],
            }
        ],
    )
    return report


if __name__ == "__main__":
    result = run(Path(__file__).resolve().parents[1])
    print(json.dumps({"status": result["status"], "best_round": result["best_round"]}))
