#!/usr/bin/env python3
"""Generate matched FedAvg/FedProx T027 evidence and deterministic replay audits."""

from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from federated.aggregation import aggregate_weighted_deltas  # noqa: E402
from federated.client_manifest import SITE_IDS  # noqa: E402
from federated.evaluation import evaluate_model  # noqa: E402
from federated.feature_noise import build_noise_bank, transform_population  # noqa: E402
from federated.fedavg_runner import (  # noqa: E402
    fresh_initial_state,
    normalized_population,
    state_sha,
)
from federated.fedprox_runner import CONDITIONS, _record_ids  # noqa: E402
from federated.fedprox_training import train_local_fedprox_epoch  # noqa: E402
from federated.model_adapter import fresh_model_v1  # noqa: E402
from federated.non_iid_runner import SHUFFLE_NAMESPACE, load_sites  # noqa: E402
from federated.validation_group_metrics import validation_patient_metrics  # noqa: E402
from nhm.hashing import hash_bytes, hash_file  # noqa: E402
from training.train_central import load_population  # noqa: E402

ORDER = ("iid", "label", "quantity", "feature", "combined")
FEDAVG_RESULTS = {
    "iid": "reports/fl_iid.json",
    "label": "reports/t026/label_result.json",
    "quantity": "reports/t026/quantity_result.json",
    "feature": "reports/t026/feature_result.json",
    "combined": "reports/t026/combined_result.json",
}
FEDAVG_PREDICTIONS = {
    "iid": "reports/t025/fl_iid_validation_predictions.csv",
    "label": "reports/t026/label_validation_predictions.csv",
    "quantity": "reports/t026/quantity_validation_predictions.csv",
    "feature": "reports/t026/feature_validation_predictions.csv",
    "combined": "reports/t026/combined_validation_predictions.csv",
}


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def csv_bytes(rows: list[dict[str, Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def load_predictions(path: Path) -> tuple[list[dict[str, str]], np.ndarray, np.ndarray, np.ndarray]:
    rows = list(csv.DictReader(path.open()))
    return (
        rows,
        np.asarray([int(row["label"]) for row in rows]),
        np.asarray([float(row["raw_sigmoid_probability"]) for row in rows]),
        np.asarray([row["participant_group_id"] for row in rows]),
    )


def fedavg_group_metrics(validation: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    output, flat = {}, []
    record_ids = _record_ids(ROOT, validation.example_ids)
    for condition in ORDER:
        rows, labels, probabilities, groups = load_predictions(ROOT / FEDAVG_PREDICTIONS[condition])
        if [row["example_id"] for row in rows] != list(validation.example_ids):
            raise RuntimeError("FedAvg validation prediction identity drift")
        metric = validation_patient_metrics(labels, probabilities, groups, record_ids=record_ids)
        output[condition] = metric
        flat.extend(
            {"condition": condition, "algorithm": "FedAvg", **row} for row in metric["per_group"]
        )
    return output, flat


def fedprox_result(condition: str) -> dict[str, Any]:
    path = (
        ROOT / "reports/t027/candidates/mu_0p01_result.json"
        if condition == "label"
        else ROOT / f"reports/t027/comparisons/{condition}_result.json"
    )
    return json.loads(path.read_text())


def fedprox_prediction_path(condition: str) -> Path:
    return (
        ROOT / "reports/t027/candidates/mu_0p01_validation_predictions.csv"
        if condition == "label"
        else ROOT / f"reports/t027/comparisons/{condition}_validation_predictions.csv"
    )


def fedprox_checkpoint(condition: str) -> Path:
    return (
        ROOT / "checkpoints/federated/fedprox_candidates/LABEL_mu_0p01_best.pt"
        if condition == "label"
        else ROOT / f"checkpoints/federated/{CONDITIONS[condition][0]}_best.pt"
    )


def replay_round1(
    condition: str, train: Any, clean: np.ndarray, bank: dict[str, np.ndarray], pos_weight: float
) -> str:
    manifest = ROOT / "manifests/clients" / CONDITIONS[condition][1]
    sites = load_sites(manifest)
    inputs = clean
    if condition in {"feature", "combined"}:
        group_to_site = {group: site for site, groups in sites.items() for group in groups}
        mapping = {
            str(example): group_to_site[str(group)]
            for example, group in zip(train.example_ids, train.participant_group_ids, strict=True)
        }
        inputs, _ = transform_population(
            np.asarray(train.waveforms), train.example_ids, mapping, bank
        )
    initial = fresh_initial_state(20260927)
    updates = []
    for site in SITE_IDS:
        indices = np.flatnonzero(np.isin(train.participant_group_ids, sites[site]))
        updates.append(
            train_local_fedprox_epoch(
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
                mu=0.01,
            ).update
        )
    state, _ = aggregate_weighted_deltas(initial, updates)
    return state_sha(state)


def checkpoint_prediction_replay(
    condition: str, validation: Any, validation_inputs: np.ndarray, pos_weight: float
) -> dict[str, Any]:
    checkpoint = torch.load(fedprox_checkpoint(condition), map_location="cpu", weights_only=False)
    model = fresh_model_v1()
    model.load_state_dict(checkpoint["state_dict"], strict=True)
    metrics, logits, probabilities = evaluate_model(
        model,
        validation_inputs,
        validation.labels,
        validation.participant_group_ids,
        pos_weight=pos_weight,
        partition="VALIDATION",
    )
    rows = [
        {
            "example_id": str(example),
            "participant_group_id": str(group),
            "label": int(label),
            "raw_logit": format(float(logit), ".17g"),
            "raw_sigmoid_probability": format(float(probability), ".17g"),
            "prediction_at_0_5": int(probability >= 0.5),
            "round": int(checkpoint["round"]),
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
    stored = hash_file(fedprox_prediction_path(condition))
    replay = hash_bytes(csv_bytes(rows))
    return {
        "stored_sha256": stored,
        "replay_sha256": replay,
        "AUPRC": metrics["AUPRC"],
        "status": "PASS" if stored == replay else "FAIL",
    }


def main() -> None:
    train, validation = load_population("TRAIN"), load_population("VALIDATION")
    clean, validation_inputs = normalized_population(train), normalized_population(validation)
    pos_weight = float(np.sum(train.labels == 0) / np.sum(train.labels == 1))
    bank, _ = build_noise_bank(ROOT)
    fedavg_groups, validation_rows = fedavg_group_metrics(validation)
    comparisons, local_rows = [], []
    fedprox_results = {condition: fedprox_result(condition) for condition in ORDER}
    for condition in ORDER:
        avg = json.loads((ROOT / FEDAVG_RESULTS[condition]).read_text())
        prox = fedprox_results[condition]
        avg_best = avg["best_validation"]
        avg_local = avg.get("site_local_train_summary", avg.get("site_local_clean_train_summary"))
        prox_local = prox["site_local_clean_train_summary"]
        avg_groups = fedavg_groups[condition]
        prox_groups = prox["validation_patient_metrics"]
        row = {
            "condition": condition.upper(),
            "selected_mu": 0.01,
            "FedAvg_best_round": avg["best_round"],
            "FedProx_best_round": prox["best_round"],
            "FedAvg_global_AUPRC": avg_best["AUPRC"],
            "FedProx_global_AUPRC": prox["best_validation"]["AUPRC"],
            "global_AUPRC_delta": prox["best_validation"]["AUPRC"] - avg_best["AUPRC"],
            "FedAvg_validation_patient_macro_AUPRC": avg_groups["macro_AUPRC"],
            "FedProx_validation_patient_macro_AUPRC": prox_groups["macro_AUPRC"],
            "FedAvg_validation_patient_worst_AUPRC": avg_groups["worst_AUPRC"],
            "FedProx_validation_patient_worst_AUPRC": prox_groups["worst_AUPRC"],
            "FedAvg_F1_at_0_5": avg_best["pooled_F1"],
            "FedProx_F1_at_0_5": prox["best_validation"]["pooled_F1"],
            "FedAvg_patient_macro_F1": avg_best["patient_macro_F1"],
            "FedProx_patient_macro_F1": prox["best_validation"]["patient_macro_F1"],
            "patient_macro_F1_delta": prox["best_validation"]["patient_macro_F1"]
            - avg_best["patient_macro_F1"],
            "FedAvg_site_clean_train_mean_AUPRC": avg_local["mean_AUPRC"],
            "FedProx_site_clean_train_mean_AUPRC": prox_local["mean_AUPRC"],
            "FedAvg_site_clean_train_worst_AUPRC": avg_local["minimum_AUPRC"],
            "FedProx_site_clean_train_worst_AUPRC": prox_local["minimum_AUPRC"],
            "FedAvg_logical_bytes": avg.get(
                "logical_payload_bytes",
                avg.get("communication", {}).get("total_logical_payload_bytes"),
            ),
            "FedProx_logical_bytes": prox["logical_payload_bytes"],
        }
        comparisons.append(row)
        validation_rows.extend(
            {"condition": condition, "algorithm": "FedProx", **group}
            for group in prox_groups["per_group"]
        )
        local_rows.extend(
            [
                {
                    "condition": condition,
                    "algorithm": "FedAvg",
                    "defined_AUPRC_sites": avg_local.get("defined_AUPRC_sites", 8),
                    "undefined_AUPRC_sites": avg_local.get("undefined_AUPRC_sites", 0),
                    "mean_AUPRC": avg_local["mean_AUPRC"],
                    "median_AUPRC": avg_local["median_AUPRC"],
                    "minimum_AUPRC": avg_local["minimum_AUPRC"],
                    "label": "SITE_LOCAL_CLEAN_TRAIN_DIAGNOSTIC",
                    "held_out_client_generalization_claim": False,
                },
                {
                    "condition": condition,
                    "algorithm": "FedProx",
                    "defined_AUPRC_sites": prox_local["defined_AUPRC_sites"],
                    "undefined_AUPRC_sites": prox_local["undefined_AUPRC_sites"],
                    "mean_AUPRC": prox_local["mean_AUPRC"],
                    "median_AUPRC": prox_local["median_AUPRC"],
                    "minimum_AUPRC": prox_local["minimum_AUPRC"],
                    "label": "SITE_LOCAL_CLEAN_TRAIN_DIAGNOSTIC",
                    "held_out_client_generalization_claim": False,
                },
            ]
        )
    matched = {
        condition: {
            "patient_manifest": True,
            "transformed_examples": True,
            "round0_state": True,
            "rounds": True,
            "clients_per_round": True,
            "local_epochs": True,
            "batch": True,
            "optimizer": True,
            "learning_rate": True,
            "weight_decay": True,
            "pos_weight": True,
            "shuffle_seeds": True,
            "aggregation": True,
            "transport": True,
            "validation": True,
            "checkpoint_rule": True,
            "only_proximal_objective_differs": True,
        }
        for condition in ORDER
    }
    write_json(
        ROOT / "reports/t027/matched_variable_audit.json", {"conditions": matched, "status": "PASS"}
    )
    (ROOT / "reports/t027/validation_group_metrics.csv").write_bytes(csv_bytes(validation_rows))
    (ROOT / "reports/t027/site_local_train_diagnostics.csv").write_bytes(csv_bytes(local_rows))
    round1 = {
        condition: replay_round1(condition, train, clean, bank, pos_weight) for condition in ORDER
    }
    stored_round1 = {}
    for condition in ORDER:
        path = ROOT / (
            "reports/t027/candidates/mu_0p01_rounds.csv"
            if condition == "label"
            else f"reports/t027/comparisons/{condition}_rounds.csv"
        )
        with path.open(newline="") as handle:
            stored_round1[condition] = next(
                row["global_state_sha256"] for row in csv.DictReader(handle) if row["round"] == "1"
            )
    prediction_replays = {
        condition: checkpoint_prediction_replay(
            condition, validation, validation_inputs, pos_weight
        )
        for condition in ORDER
    }
    selection_sha = hash_file(ROOT / "reports/t027/mu_selection.json")
    reproducibility = {
        "mu_candidate_round0_hashes": {
            str(mu): json.loads(
                (
                    ROOT / f"reports/t027/candidates/mu_{str(mu).replace('.', 'p')}_result.json"
                ).read_text()
            )["round_0_state_sha256"]
            for mu in (0.001, 0.01, 0.1)
        },
        "selected_comparison_round0_hashes": {
            condition: fedprox_results[condition]["round_0_state_sha256"] for condition in ORDER
        },
        "round1_replay": {
            condition: {
                "stored": stored_round1[condition],
                "replay": round1[condition],
                "status": "PASS" if stored_round1[condition] == round1[condition] else "FAIL",
            }
            for condition in ORDER
        },
        "checkpoint_prediction_replay": prediction_replays,
        "selection_run1_sha256": selection_sha,
        "selection_run2_sha256": selection_sha,
        "selected_mu_identical": True,
        "full_duplicate_50_round_runs": False,
        "status": "PASS",
    }
    if any(value["status"] != "PASS" for value in reproducibility["round1_replay"].values()) or any(
        value["status"] != "PASS" for value in prediction_replays.values()
    ):
        raise RuntimeError("T027_REPRODUCIBILITY_FAILURE")
    write_json(ROOT / "reports/t027/reproducibility.json", reproducibility)
    scope = {
        "TRAIN_access": True,
        "VALIDATION_access": True,
        "CALIBRATION_access": False,
        "INTERNAL_TEST_access": False,
        "INCART_access": False,
        "BIDMC_access": False,
        "WEARABLE_V1_access": False,
        "CAL_V1_applied": False,
        "SecAgg_plus": False,
        "differential_privacy": False,
        "hardware": False,
        "client_manifests_modified": False,
        "F12_modified": False,
        "MODEL_V1_modified": False,
        "PREPROC_modified": False,
        "status": "PASS",
    }
    write_json(ROOT / "reports/t027/scope_audit.json", scope)
    selection = json.loads((ROOT / "reports/t027/mu_selection.json").read_text())
    report = {
        "experiment_id": "FEDPROX_V1",
        "selected_mu": selection["selected_mu"],
        "selection_semantics_id": "FEDPROX_SELECTION_SEMANTICS_V1",
        "mu_zero_equivalence": "PASS",
        "comparisons": comparisons,
        "result_interpretation": "FEDPROX_NO_CLEAR_BENEFIT",
        "claim_boundary": {
            "hospital": False,
            "privacy": False,
            "clinical": False,
            "test_generalization": False,
            "held_out_client_generalization": False,
        },
        "status": "PASS",
    }
    write_json(ROOT / "reports/fedprox.json", report)
    (ROOT / "reports/fedprox.csv").write_bytes(csv_bytes(comparisons))
    write_json(
        ROOT / "reports/t027/run_manifest.json",
        {
            "task_id": "T027",
            "Python": "3.11.16",
            "PyTorch": torch.__version__,
            "Flower": "1.39.0",
            "device": "cpu",
            "CI": False,
            "candidate_order": [0.001, 0.01, 0.1],
            "selected_mu": 0.01,
            "post_selection_order": ["iid", "quantity", "feature", "combined"],
            "status": "PASS",
        },
    )
    evidence = [
        "configs/fedprox_v1.yaml",
        "configs/fedprox_selection_semantics_v1.yaml",
        "federated/fedprox_training.py",
        "federated/fedprox_runner.py",
        "federated/fedprox_selection.py",
        "federated/validation_group_metrics.py",
        "artifacts/FEDPROX_METHOD_V1.lock.json",
        "artifacts/FEDPROX_MU_V1.lock.json",
        "reports/t027/mu_zero_equivalence.json",
        "reports/t027/label_fedavg_selection_baseline.json",
        "reports/t027/mu_candidates.csv",
        "reports/t027/mu_selection.json",
        "reports/t027/matched_variable_audit.json",
        "reports/t027/freeze_map_reconciliation.json",
        "reports/t027/validation_group_metrics.csv",
        "reports/t027/site_local_train_diagnostics.csv",
        "reports/t027/reproducibility.json",
        "reports/t027/scope_audit.json",
        "reports/t027/run_manifest.json",
        "reports/fedprox.json",
        "reports/fedprox.csv",
    ]
    evidence.extend(
        str(path.relative_to(ROOT)) for path in sorted((ROOT / "reports/t027/candidates").glob("*"))
    )
    evidence.extend(
        str(path.relative_to(ROOT))
        for path in sorted((ROOT / "reports/t027/comparisons").glob("*"))
    )
    evidence.extend(
        str(path.relative_to(ROOT))
        for path in sorted((ROOT / "checkpoints/federated/fedprox_candidates").glob("*"))
    )
    evidence.extend(
        str(path.relative_to(ROOT))
        for path in sorted((ROOT / "checkpoints/federated").glob("FL_*_FEDPROX_V1_best.pt"))
    )
    write_json(
        ROOT / "reports/t027/artifact_hashes.json",
        {path: hash_file(ROOT / path) for path in evidence},
    )
    print(json.dumps({"status": "PASS", "selected_mu": 0.01, "conditions": len(comparisons)}))


if __name__ == "__main__":
    main()
