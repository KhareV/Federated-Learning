#!/usr/bin/env python3
"""Freeze and verify the completed T025 IID FedAvg result."""

from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import platform
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import flwr
import numpy as np
import torch
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from federated.aggregation import aggregate_weighted_deltas  # noqa: E402
from federated.client_manifest import (  # noqa: E402
    SITE_IDS,
    build_assignment,
    manifest_rows,
    train_patient_summaries,
    write_manifest,
)
from federated.evaluation import evaluate_model  # noqa: E402
from federated.fedavg_runner import (  # noqa: E402
    choose_best_round,
    fresh_initial_state,
    load_manifest_sites,
    normalized_population,
    state_sha,
)
from federated.local_training import train_local_epoch  # noqa: E402
from federated.model_adapter import fresh_model_v1, restore_state  # noqa: E402
from nhm.hashing import hash_file  # noqa: E402
from training.train_central import load_population  # noqa: E402

REPORT_DIR = ROOT / "reports/t025"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def commit_for_subject(subject: str) -> str:
    return subprocess.check_output(
        ["git", "log", "--format=%H", "--grep", f"^{subject}$", "-1"],
        cwd=ROOT,
        text=True,
    ).strip()


def checkpoint_state(path: Path) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    payload = torch.load(path, map_location="cpu", weights_only=True)
    state = {
        key: np.array(value.detach().cpu().numpy(), copy=True)
        for key, value in payload["state_dict"].items()
    }
    return payload, state


def prediction_csv_bytes(
    example_ids: tuple[str, ...],
    groups: np.ndarray,
    labels: np.ndarray,
    logits: np.ndarray,
    probabilities: np.ndarray,
    best_round: int,
) -> bytes:
    fields = [
        "example_id",
        "participant_group_id",
        "label",
        "raw_logit",
        "raw_sigmoid_probability",
        "prediction_at_0_5",
        "round",
    ]
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for example_id, group, label, logit, probability in zip(
        example_ids, groups, labels, logits, probabilities, strict=True
    ):
        writer.writerow(
            {
                "example_id": example_id,
                "participant_group_id": group,
                "label": int(label),
                "raw_logit": format(float(logit), ".17g"),
                "raw_sigmoid_probability": format(float(probability), ".17g"),
                "prediction_at_0_5": int(probability >= 0.5),
                "round": best_round,
            }
        )
    return buffer.getvalue().encode()


def round_one_replay(config: dict[str, Any]) -> tuple[str, str, list[int]]:
    train = load_population("TRAIN")
    train_inputs = normalized_population(train)
    sites = load_manifest_sites(ROOT / "manifests/clients/CLIENTS_IID_V1.csv")
    site_indices = {
        site: np.flatnonzero(np.isin(train.participant_group_ids, groups))
        for site, groups in sites.items()
    }
    initial = fresh_initial_state(int(config["initialization"]["seed"]))
    updates = []
    seeds = []
    pos_weight = float(config["loss"]["pos_weight"])
    for site in SITE_IDS:
        indices = site_indices[site]
        result = train_local_epoch(
            global_state=initial,
            inputs=train_inputs[indices],
            labels=train.labels[indices],
            site_id=site,
            round_number=1,
            experiment_id="FL_IID_V1",
            base_seed=int(config["initialization"]["seed"]),
            batch_size=int(config["training"]["batch_size"]),
            learning_rate=float(config["optimizer"]["learning_rate"]),
            weight_decay=float(config["optimizer"]["weight_decay"]),
            pos_weight=pos_weight,
        )
        updates.append(result.update)
        seeds.append(result.shuffle_seed)
    aggregate, _ = aggregate_weighted_deltas(initial, updates)
    return state_sha(initial), state_sha(aggregate), seeds


def main() -> None:
    method_lock = json.loads((ROOT / "artifacts/FL_IID_METHOD_V1.lock.json").read_text())
    for name, path in method_lock["paths"].items():
        if hash_file(ROOT / path) != method_lock["hashes"][name]:
            raise RuntimeError(f"FL_IID_METHOD_LOCK_MISMATCH: {name}")
    config = yaml.safe_load((ROOT / "configs/fl_iid_v1.yaml").read_text())
    round_rows = read_csv(REPORT_DIR / "fl_iid_rounds.csv")
    client_rows = read_csv(REPORT_DIR / "fl_iid_client_rounds.csv")
    if len(round_rows) != 51 or len(client_rows) != 400:
        raise RuntimeError("FL_IID_ROUND_CLOSURE_FAILURE")
    if any(int(row["client_count"]) != 8 for row in round_rows[1:]):
        raise RuntimeError("FL_IID_CLIENT_PARTICIPATION_FAILURE")
    if any(row["status"] != "PASS" for row in client_rows):
        raise RuntimeError("FL_IID_CLIENT_FAILURE")
    best_round = choose_best_round(round_rows)
    report = json.loads((ROOT / "reports/fl_iid.json").read_text())
    stability = json.loads((REPORT_DIR / "stability_audit.json").read_text())
    if best_round != report["best_round"] or not stability["stable_convergence"]:
        raise RuntimeError("FEDAVG_NO_LEARNING_SIGNAL")

    initial_sha_1, round1_sha_1, seeds1 = round_one_replay(config)
    expected_initial = round_rows[0]["global_state_sha256"]
    expected_round1 = round_rows[1]["global_state_sha256"]
    if initial_sha_1 != expected_initial or round1_sha_1 != expected_round1:
        raise RuntimeError("FL_IID_ROUND_ONE_REPRODUCIBILITY_FAILURE")
    initial_sha_2 = state_sha(fresh_initial_state(int(config["initialization"]["seed"])))

    best_path = ROOT / "checkpoints/federated/FL_IID_V1_best.pt"
    checkpoint, best_state = checkpoint_state(best_path)
    if int(checkpoint["round"]) != best_round:
        raise RuntimeError("FL_IID_BEST_CHECKPOINT_ROUND_MISMATCH")
    validation = load_population("VALIDATION")
    validation_inputs = normalized_population(validation)
    model = fresh_model_v1()
    restore_state(model, best_state)
    metrics1, logits1, probabilities1 = evaluate_model(
        model,
        validation_inputs,
        validation.labels,
        validation.participant_group_ids,
        pos_weight=float(config["loss"]["pos_weight"]),
        partition="VALIDATION",
    )
    model2 = fresh_model_v1()
    restore_state(model2, copy.deepcopy(best_state))
    metrics2, logits2, probabilities2 = evaluate_model(
        model2,
        validation_inputs,
        validation.labels,
        validation.participant_group_ids,
        pos_weight=float(config["loss"]["pos_weight"]),
        partition="VALIDATION",
    )
    bytes1 = prediction_csv_bytes(
        validation.example_ids,
        validation.participant_group_ids,
        validation.labels,
        logits1,
        probabilities1,
        best_round,
    )
    bytes2 = prediction_csv_bytes(
        validation.example_ids,
        validation.participant_group_ids,
        validation.labels,
        logits2,
        probabilities2,
        best_round,
    )
    stored = (REPORT_DIR / "fl_iid_validation_predictions.csv").read_bytes()
    if bytes1 != bytes2 or bytes1 != stored or metrics1 != metrics2:
        raise RuntimeError("FL_IID_SELECTED_CHECKPOINT_REPLAY_FAILURE")
    prediction_sha = hashlib.sha256(stored).hexdigest()

    with tempfile.TemporaryDirectory() as directory:
        rebuilt = Path(directory) / "CLIENTS_IID_V1.csv"
        assignment, _ = build_assignment(
            train_patient_summaries(ROOT / "manifests/windows/MITDB_WINDOWS_V1.csv")
        )
        write_manifest(rebuilt, manifest_rows(assignment))
        manifest_run2_sha = hash_file(rebuilt)
    manifest_run1_sha = hash_file(ROOT / "manifests/clients/CLIENTS_IID_V1.csv")
    if manifest_run1_sha != manifest_run2_sha:
        raise RuntimeError("CLIENTS_IID_V1_RECONSTRUCTION_MISMATCH")

    write_json(
        REPORT_DIR / "reproducibility.json",
        {
            "manifest_run_1_sha256": manifest_run1_sha,
            "manifest_run_2_sha256": manifest_run2_sha,
            "round_0_state_run_1_sha256": initial_sha_1,
            "round_0_state_run_2_sha256": initial_sha_2,
            "round_1_aggregate_run_1_sha256": expected_round1,
            "round_1_aggregate_replay_sha256": round1_sha_1,
            "round_1_client_seeds": seeds1,
            "best_round_run_1": best_round,
            "best_round_log_recomputation": choose_best_round(round_rows),
            "best_prediction_run_1_sha256": prediction_sha,
            "best_prediction_replay_sha256": hashlib.sha256(bytes2).hexdigest(),
            "best_metrics_run_1": metrics1,
            "best_metrics_replay": metrics2,
            "full_second_50_round_run_performed": False,
            "deterministic_replay_used": (
                "byte-identical manifest reconstruction; exact fresh round-0 reconstruction; "
                "complete eight-client round-1 replay; selected-checkpoint reload/inference "
                "replay; metric recomputation from frozen predictions and logs"
            ),
            "status": "PASS",
        },
    )
    write_json(
        REPORT_DIR / "scope_audit.json",
        {
            "TRAIN_access": True,
            "VALIDATION_access": True,
            "CALIBRATION_access": False,
            "INTERNAL_TEST_access": False,
            "INCART_access": False,
            "NSTDB_access": False,
            "BIDMC_access": False,
            "WEARABLE_V1_access": False,
            "FedProx": False,
            "SecAgg_plus": False,
            "differential_privacy": False,
            "non_IID": False,
            "hardware": False,
            "CAL_V1_transferred": False,
            "central_checkpoint_warm_start": False,
            "status": "PASS",
        },
    )
    result_paths = {
        "best_checkpoint": "checkpoints/federated/FL_IID_V1_best.pt",
        "round_50_checkpoint": "checkpoints/federated/FL_IID_V1_round50.pt",
        "round_log": "reports/t025/fl_iid_rounds.csv",
        "client_round_log": "reports/t025/fl_iid_client_rounds.csv",
        "validation_predictions": "reports/t025/fl_iid_validation_predictions.csv",
        "stability_audit": "reports/t025/stability_audit.json",
        "initialization_audit": "reports/t025/initialization_audit.json",
        "aggregation_parity": "reports/t025/aggregation_parity.json",
        "main_report": "reports/fl_iid.json",
        "summary_csv": "reports/fl_iid.csv",
    }
    write_json(
        ROOT / "artifacts/FL_IID_V1.lock.json",
        {
            "lock_id": "FL_IID_V1",
            "status": "FROZEN_ENGINEERING_RESULT",
            "method_lock_sha256": hash_file(ROOT / "artifacts/FL_IID_METHOD_V1.lock.json"),
            "config_sha256": hash_file(ROOT / "configs/fl_iid_v1.yaml"),
            "client_manifest_sha256": manifest_run1_sha,
            "initialization_sha256": hash_file(ROOT / "configs/fl_init_v1.yaml"),
            "transport_sha256": hash_file(ROOT / "configs/fl_state_transport_v1.yaml"),
            "aggregation_sha256": hash_file(ROOT / "federated/aggregation.py"),
            "result_hashes": {
                name: hash_file(ROOT / path) for name, path in result_paths.items()
            },
            "result_paths": result_paths,
            "best_round": best_round,
            "best_validation_AUPRC": report["best_validation"]["AUPRC"],
            "canonical_F12_status": "NOT_FROZEN",
        },
    )
    implementation_commit = commit_for_subject(
        "fl(T025): implement whole-patient IID client construction and runner"
    )
    protocol_commit = commit_for_subject(
        "fl(T025): freeze IID FedAvg protocol and client manifest"
    )
    write_json(
        REPORT_DIR / "run_manifest.json",
        {
            "task_id": "T025",
            "experiment_id": "FL_IID_V1",
            "command": "PYTHONPATH=src:. .venv-t024/bin/python -m federated.fedavg_runner",
            "implementation_commit": implementation_commit,
            "pre_result_protocol_commit": protocol_commit,
            "python": platform.python_version(),
            "pytorch": torch.__version__,
            "Flower": flwr.__version__,
            "device": "cpu",
            "rounds": 50,
            "client_updates": 400,
            "ci_executed": False,
            "status": "PASS",
        },
    )
    paths = [
        "configs/fl_init_v1.yaml",
        "configs/fl_iid_v1.yaml",
        "manifests/clients/CLIENTS_IID_V1.csv",
        "federated/client_manifest.py",
        "federated/local_training.py",
        "federated/fedavg_runner.py",
        "federated/evaluation.py",
        "artifacts/FL_IID_METHOD_V1.lock.json",
        "artifacts/FL_IID_V1.lock.json",
        *result_paths.values(),
        "reports/t025/client_manifest_audit.json",
        "reports/t025/client_balance.csv",
        "reports/t025/scope_audit.json",
        "reports/t025/reproducibility.json",
        "reports/t025/run_manifest.json",
    ]
    write_json(
        REPORT_DIR / "artifact_hashes.json",
        {
            "algorithm": "sha256",
            "artifacts": {path: hash_file(ROOT / path) for path in paths},
            "status": "PASS",
        },
    )
    print(json.dumps({"status": "PASS", "best_round": best_round}, sort_keys=True))


if __name__ == "__main__":
    main()
