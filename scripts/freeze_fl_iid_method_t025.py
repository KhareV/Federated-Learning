#!/usr/bin/env python3
"""Build CLIENTS_IID_V1 and freeze the pre-result T025 method lock."""

from __future__ import annotations

import csv
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

import flwr

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from federated.client_manifest import (  # noqa: E402
    ASSIGNMENT_METHOD_ID,
    CLIENT_MANIFEST_ID,
    SITE_IDS,
    build_assignment,
    coefficient_of_variation,
    manifest_rows,
    read_csv,
    train_patient_summaries,
    write_manifest,
)
from nhm.hashing import hash_file  # noqa: E402


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    window_path = ROOT / "manifests/windows/MITDB_WINDOWS_V1.csv"
    split_path = ROOT / "manifests/splits/MITDB_SPLIT_V1.csv"
    output = ROOT / "manifests/clients/CLIENTS_IID_V1.csv"
    patients = train_patient_summaries(window_path)
    assignment, details = build_assignment(patients)
    rows = manifest_rows(assignment)
    write_manifest(output, rows)
    with tempfile.TemporaryDirectory() as directory:
        rebuilt = Path(directory) / output.name
        second_assignment, second_details = build_assignment(
            train_patient_summaries(window_path)
        )
        write_manifest(rebuilt, manifest_rows(second_assignment))
        if output.read_bytes() != rebuilt.read_bytes() or details != second_details:
            raise RuntimeError("CLIENTS_IID_V1_RECONSTRUCTION_MISMATCH")

    split = read_csv(split_path)
    partition_by_group = {row["participant_group_id"]: row["partition"] for row in split}
    assigned_groups = [row["participant_group_id"] for row in rows]
    train_groups = {
        row["participant_group_id"] for row in split if row["partition"] == "TRAIN"
    }
    duplicates = sorted({group for group in assigned_groups if assigned_groups.count(group) > 1})
    omitted = sorted(train_groups - set(assigned_groups))
    forbidden = {
        partition: sorted(
            group
            for group in assigned_groups
            if partition_by_group.get(group) == partition
        )
        for partition in ("VALIDATION", "CALIBRATION", "INTERNAL_TEST")
    }
    if duplicates or omitted or any(forbidden.values()) or set(assigned_groups) != train_groups:
        raise RuntimeError("CLIENTS_IID_V1_PATIENT_INTEGRITY_FAILURE")
    site_rows: list[dict[str, Any]] = []
    for site in SITE_IDS:
        site_patients = assignment[site]
        windows = sum(patient.windows for patient in site_patients)
        positives = sum(patient.positives for patient in site_patients)
        site_rows.append(
            {
                "site_id": site,
                "patients": len(site_patients),
                "windows": windows,
                "positive": positives,
                "negative": windows - positives,
                "positive_rate": positives / windows,
                "quantity_deviation_from_target": windows / (details["total_windows"] / 8) - 1,
                "label_rate_deviation_from_global": positives / windows
                - details["total_positives"] / details["total_windows"],
            }
        )
    if any(row["positive"] == 0 or row["negative"] == 0 for row in site_rows):
        raise RuntimeError("CLIENTS_IID_V1_SINGLE_CLASS_SITE")
    write_csv(ROOT / "reports/t025/client_balance.csv", site_rows)
    manifest_sha = hash_file(output)
    reconstruction_sha = hashlib.sha256(output.read_bytes()).hexdigest()
    write_json(
        ROOT / "reports/t025/client_manifest_audit.json",
        {
            "client_manifest_id": CLIENT_MANIFEST_ID,
            "assignment_method": ASSIGNMENT_METHOD_ID,
            "sites": len(SITE_IDS),
            "TRAIN_patient_groups": len(train_groups),
            "assigned_patient_groups": len(assigned_groups),
            "omitted_TRAIN_patients": omitted,
            "duplicate_patient_assignments": duplicates,
            "cross_site_patients": duplicates,
            "forbidden_partition_patients": forbidden,
            "total_windows": sum(int(row["eligible_window_count"]) for row in rows),
            "total_positives": sum(int(row["positive_window_count"]) for row in rows),
            "total_negatives": sum(int(row["negative_window_count"]) for row in rows),
            "patient_indivisibility": True,
            "manifest_sha256": manifest_sha,
            "reconstruction_sha256": reconstruction_sha,
            "reconstruction_byte_identical": True,
            "capacities": details["capacities"],
            "initial_assignment_objective": details["initial_objective"],
            "final_assignment_objective": details["final_objective"],
            "swap_count": details["swap_count"],
            "all_sites_both_classes": True,
            "site_rows": site_rows,
            "aggregate_balance": {
                "minimum_patient_count": min(row["patients"] for row in site_rows),
                "maximum_patient_count": max(row["patients"] for row in site_rows),
                "minimum_window_count": min(row["windows"] for row in site_rows),
                "maximum_window_count": max(row["windows"] for row in site_rows),
                "window_count_CV": coefficient_of_variation(
                    [int(row["windows"]) for row in site_rows]
                ),
                "minimum_positive_rate": min(row["positive_rate"] for row in site_rows),
                "maximum_positive_rate": max(row["positive_rate"] for row in site_rows),
                "global_positive_rate": details["total_positives"] / details["total_windows"],
                "target_windows_per_site": details["total_windows"] / 8,
            },
            "status": "PASS",
        },
    )
    paths = {
        "fl_iid_config": "configs/fl_iid_v1.yaml",
        "fl_init_config": "configs/fl_init_v1.yaml",
        "client_manifest": "manifests/clients/CLIENTS_IID_V1.csv",
        "model_architecture": "models/ecg_cnn.py",
        "model_frozen_config": "configs/model_v1_frozen.yaml",
        "preproc_lock": "manifests/preprocessing/PREPROC_V1.lock.json",
        "split": "manifests/splits/MITDB_SPLIT_V1.csv",
        "window_manifest": "manifests/windows/MITDB_WINDOWS_V1.csv",
        "transport_config": "configs/fl_state_transport_v1.yaml",
        "aggregation_source": "federated/aggregation.py",
        "model_adapter": "federated/model_adapter.py",
        "manifest_builder": "federated/client_manifest.py",
        "local_training": "federated/local_training.py",
        "runner": "federated/fedavg_runner.py",
        "evaluation": "federated/evaluation.py",
    }
    write_json(
        ROOT / "artifacts/FL_IID_METHOD_V1.lock.json",
        {
            "lock_id": "FL_IID_METHOD_V1",
            "experiment_id": "FL_IID_V1",
            "status": "FROZEN_ENGINEERING_METHOD",
            "outcome_metrics_included": False,
            "hashes": {name: hash_file(ROOT / path) for name, path in paths.items()},
            "paths": paths,
            "Flower_version": flwr.__version__,
            "initialization": {
                "id": "FL_INIT_V1",
                "source": "FRESH_MODEL_V1_ARCHITECTURE",
                "seed": 20260927,
                "central_checkpoint_pretraining": False,
            },
            "seed_rule": "SHA256(20260927|experiment_id|round|client_id)",
            "metric_threshold": {
                "id": "FL_METRIC_THRESHOLD_V1",
                "probability": "sigmoid(raw_logit)",
                "threshold": 0.5,
                "comparator": ">=",
                "CAL_V1_applied": False,
            },
            "validation_only_access": True,
            "stable_convergence": {
                "rounds": 50,
                "clients_per_round": 8,
                "finite_states_and_metrics": True,
                "post_round_AUPRC_improvement_over_round_0": ">1e-6",
            },
            "canonical_F12_status": "NOT_FROZEN",
        },
    )
    print(json.dumps({"status": "PASS", "manifest_sha256": manifest_sha}, sort_keys=True))


if __name__ == "__main__":
    main()
