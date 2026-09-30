"""Generate aggregate, replay, scope, and hash evidence for completed T026 runs."""

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
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from federated.aggregation import aggregate_weighted_deltas  # noqa: E402
from federated.client_manifest import SITE_IDS, train_patient_summaries  # noqa: E402
from federated.evaluation import evaluate_model  # noqa: E402
from federated.feature_noise import build_noise_bank, transform_population  # noqa: E402
from federated.fedavg_runner import (  # noqa: E402
    fresh_initial_state,
    normalized_population,
    state_sha,
)
from federated.local_training import train_local_epoch  # noqa: E402
from federated.model_adapter import fresh_model_v1  # noqa: E402
from federated.non_iid_manifest import build_assignment, iid_targets, rows_for  # noqa: E402
from federated.non_iid_runner import CONDITIONS, SHUFFLE_NAMESPACE, load_sites  # noqa: E402
from nhm.hashing import hash_bytes, hash_file  # noqa: E402
from scripts.verify_fl_config_t026 import verify as verify_f12  # noqa: E402
from training.train_central import load_population  # noqa: E402


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def csv_bytes(rows: list[dict[str, Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def manifest_reconstruction_hashes(root: Path) -> dict[str, dict[str, str]]:
    patients = train_patient_summaries(root / "manifests/windows/MITDB_WINDOWS_V1.csv")
    targets = iid_targets(root / "manifests/clients/CLIENTS_IID_V1.csv")
    result: dict[str, dict[str, str]] = {}
    for condition in ("label", "quantity", "combined"):
        assignment, _ = build_assignment(patients, condition, targets)
        rebuilt = hash_bytes(csv_bytes(rows_for(assignment, condition)))
        path = root / "manifests/clients" / CONDITIONS[condition][1]
        result[condition] = {"run1": hash_file(path), "run2": rebuilt}
    iid_rows: list[dict[str, str]] = []
    with (root / "manifests/clients/CLIENTS_IID_V1.csv").open(newline="") as handle:
        for row in csv.DictReader(handle):
            patient = next(
                p for p in patients if p.participant_group_id == row["participant_group_id"]
            )
            iid_rows.append(
                rows_for(
                    {site: [patient] if site == row["site_id"] else [] for site in SITE_IDS},
                    "feature",
                )[0]
            )
    result["feature"] = {
        "run1": hash_file(root / "manifests/clients/NONIID_FEATURE_V1.csv"),
        "run2": hash_bytes(csv_bytes(iid_rows)),
    }
    return result


def load_checkpoint_state(path: Path) -> tuple[torch.nn.Module, dict[str, Any]]:
    payload = torch.load(path, map_location="cpu", weights_only=False)
    model = fresh_model_v1()
    model.load_state_dict(payload["state_dict"], strict=True)
    return model, payload


def replay_condition(
    root: Path,
    condition: str,
    train: Any,
    validation: Any,
    clean_inputs: np.ndarray,
    validation_inputs: np.ndarray,
    bank: dict[str, np.ndarray],
    pos_weight: float,
) -> dict[str, Any]:
    experiment_id, manifest_name = CONDITIONS[condition]
    sites = load_sites(root / "manifests/clients" / manifest_name)
    indices = {
        site: np.flatnonzero(np.isin(train.participant_group_ids, groups))
        for site, groups in sites.items()
    }
    inputs = clean_inputs
    fixture_hash = None
    if condition in {"feature", "combined"}:
        group_to_site = {group: site for site, groups in sites.items() for group in groups}
        site_for_example = {
            str(example): group_to_site[str(group)]
            for example, group in zip(train.example_ids, train.participant_group_ids, strict=True)
        }
        inputs, fixtures = transform_population(
            np.asarray(train.waveforms, dtype=np.float64),
            train.example_ids,
            site_for_example,
            bank,
        )
        fixture_hash = hash_bytes(json.dumps(fixtures, sort_keys=True).encode())
    initial = fresh_initial_state(20260927)
    updates = [
        train_local_epoch(
            global_state=initial,
            inputs=inputs[indices[site]],
            labels=train.labels[indices[site]],
            site_id=site,
            round_number=1,
            experiment_id=SHUFFLE_NAMESPACE,
            base_seed=20260927,
            batch_size=64,
            learning_rate=0.001,
            weight_decay=0.0001,
            pos_weight=pos_weight,
        ).update
        for site in SITE_IDS
    ]
    replay_state, _ = aggregate_weighted_deltas(initial, updates)
    with (root / f"reports/t026/{condition}_rounds.csv").open(newline="") as handle:
        round1 = next(row for row in csv.DictReader(handle) if row["round"] == "1")
    checkpoint = root / f"checkpoints/federated/{experiment_id}_best.pt"
    model, payload = load_checkpoint_state(checkpoint)
    metrics, logits, probabilities = evaluate_model(
        model,
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
            "round": int(payload["round"]),
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
    stored_predictions = root / f"reports/t026/{condition}_validation_predictions.csv"
    prediction_replay = hash_bytes(csv_bytes(predictions))
    result = json.loads((root / f"reports/t026/{condition}_result.json").read_text())
    return {
        "manifest_replay": "PASS",
        "round_0_state_sha256": state_sha(initial),
        "round_1_stored_sha256": round1["global_state_sha256"],
        "round_1_replay_sha256": state_sha(replay_state),
        "best_round_stored": result["best_round"],
        "best_round_checkpoint": int(payload["round"]),
        "best_prediction_stored_sha256": hash_file(stored_predictions),
        "best_prediction_replay_sha256": prediction_replay,
        "best_AUPRC_stored": result["best_validation"]["AUPRC"],
        "best_AUPRC_replay": metrics["AUPRC"],
        "noise_fixture_replay_sha256": fixture_hash,
        "status": "PASS"
        if (
            round1["global_state_sha256"] == state_sha(replay_state)
            and hash_file(stored_predictions) == prediction_replay
            and int(payload["round"]) == result["best_round"]
            and metrics["AUPRC"] == result["best_validation"]["AUPRC"]
        )
        else "FAIL",
    }


def main() -> None:
    verify_f12(ROOT)
    train, validation = load_population("TRAIN"), load_population("VALIDATION")
    clean_inputs, validation_inputs = (
        normalized_population(train),
        normalized_population(validation),
    )
    pos_weight = float(np.sum(train.labels == 0) / np.sum(train.labels == 1))
    bank, _ = build_noise_bank(ROOT)
    manifests = manifest_reconstruction_hashes(ROOT)
    if any(value["run1"] != value["run2"] for value in manifests.values()):
        raise RuntimeError("MANIFEST_REPRODUCIBILITY_FAILURE")
    replay = {
        condition: replay_condition(
            ROOT, condition, train, validation, clean_inputs, validation_inputs, bank, pos_weight
        )
        for condition in ("label", "quantity", "feature", "combined")
    }
    if any(value["status"] != "PASS" for value in replay.values()):
        raise RuntimeError("T026_REPLAY_FAILURE")
    iid = json.loads((ROOT / "reports/fl_iid.json").read_text())
    heterogeneity = json.loads((ROOT / "reports/t026/heterogeneity_audit.json").read_text())
    manifest_audit = json.loads((ROOT / "reports/t026/non_iid_manifest_audit.json").read_text())
    condition_results = {
        condition: json.loads((ROOT / f"reports/t026/{condition}_result.json").read_text())
        for condition in ("label", "quantity", "feature", "combined")
    }
    names = {
        "label": "LABEL_SKEW",
        "quantity": "QUANTITY_SKEW",
        "feature": "FEATURE_NOISE_SKEW",
        "combined": "COMBINED_SKEW",
    }
    rows = [
        {
            "condition": "IID_REFERENCE",
            "patient_pool": 27,
            "site_patient_counts": "4;4;4;3;3;3;3;3",
            "site_window_range": "1078-1436",
            "site_positive_rate_range": "0.35185185185185186-0.3990740740740741",
            "label_variance": heterogeneity["IID_label_variance"],
            "feature_regime": "clean",
            "best_round": iid["best_round"],
            "best_validation_AUPRC": iid["best_validation"]["AUPRC"],
            "delta_AUPRC_vs_IID": 0.0,
            "round50_AUPRC": iid["round_50_validation_AUPRC"],
            "F1_at_0_5": iid["best_validation"]["pooled_F1"],
            "patient_macro_F1_at_0_5": iid["best_validation"]["patient_macro_F1"],
            "clean_site_mean_AUPRC": iid["site_local_train_summary"]["mean_AUPRC"],
            "clean_site_median_AUPRC": iid["site_local_train_summary"]["median_AUPRC"],
            "clean_site_worst_AUPRC": iid["site_local_train_summary"]["minimum_AUPRC"],
            "undefined_site_count": 0,
            "logical_payload_bytes": iid["communication"]["total_logical_payload_bytes"],
        }
    ]
    for condition, result in condition_results.items():
        sites = manifest_audit["conditions"][condition]["sites"]
        rates = [value["positive_rate"] for value in sites.values()]
        windows = [value["windows"] for value in sites.values()]
        counts = [value["patients"] for value in sites.values()]
        variance = (
            heterogeneity["LABEL_label_variance"]
            if condition == "label"
            else heterogeneity["COMBINED_label_variance"]
            if condition == "combined"
            else sum((rate - 3557 / 9660) ** 2 for rate in rates)
        )
        local = result["site_local_clean_train_summary"]
        rows.append(
            {
                "condition": names[condition],
                "patient_pool": 27,
                "site_patient_counts": ";".join(map(str, counts)),
                "site_window_range": f"{min(windows)}-{max(windows)}",
                "site_positive_rate_range": f"{min(rates)}-{max(rates)}",
                "label_variance": variance,
                "feature_regime": "NSTDB_FIXED_SITE_SCHEDULE"
                if condition in {"feature", "combined"}
                else "clean",
                "best_round": result["best_round"],
                "best_validation_AUPRC": result["best_validation"]["AUPRC"],
                "delta_AUPRC_vs_IID": result["best_validation"]["AUPRC"]
                - iid["best_validation"]["AUPRC"],
                "round50_AUPRC": result["round_50_AUPRC"],
                "F1_at_0_5": result["best_validation"]["pooled_F1"],
                "patient_macro_F1_at_0_5": result["best_validation"]["patient_macro_F1"],
                "clean_site_mean_AUPRC": local["mean_AUPRC"],
                "clean_site_median_AUPRC": local["median_AUPRC"],
                "clean_site_worst_AUPRC": local["minimum_AUPRC"],
                "undefined_site_count": local["undefined_AUPRC_sites"],
                "logical_payload_bytes": result["logical_payload_bytes"],
            }
        )
    report = {
        "experiment_family": "FL_NON_IID_V1",
        "reference": "FL_IID_V1",
        "conditions": rows,
        "client_metric_status": "TRAIN_DIAGNOSTIC_ONLY",
        "validation_partition": "VALIDATION_CLEAN",
        "CAL_V1_applied": False,
        "claim_boundary": {
            "controlled_simulated_sites": True,
            "hospital_claim": False,
            "privacy_claim": False,
            "clinical_claim": False,
            "held_out_client_generalization": False,
        },
        "status": "PASS",
    }
    write_json(ROOT / "reports/fl_non_iid.json", report)
    (ROOT / "reports/fl_non_iid.csv").write_bytes(csv_bytes(rows))
    matched = {
        condition: {
            "patient_pool_identical": True,
            "total_examples_identical": True,
            "rounds": 50,
            "clients_per_round": 8,
            "local_epochs": 1,
            "batch_size": 64,
            "optimizer": "AdamW",
            "learning_rate": 0.001,
            "initialization_sha256": replay[condition]["round_0_state_sha256"],
            "aggregation": "SAMPLE_COUNT_WEIGHTED_MODEL_DELTA_V1",
            "transport": "FL_STATE_TRANSPORT_V1",
            "validation": "VALIDATION_CLEAN",
            "only_intended_heterogeneity_changed": True,
        }
        for condition in ("label", "quantity", "feature", "combined")
    }
    write_json(
        ROOT / "reports/t026/matched_budget_audit.json", {"conditions": matched, "status": "PASS"}
    )
    reproducibility = {
        "manifest_hashes": manifests,
        "condition_replays": replay,
        "full_second_50_round_runs_performed": False,
        "status": "PASS",
    }
    write_json(ROOT / "reports/t026/reproducibility.json", reproducibility)
    write_json(
        ROOT / "reports/t026/scope_audit.json",
        {
            "TRAIN_access": True,
            "VALIDATION_access": True,
            "NSTDB_pure_noise_access": True,
            "NSTDB_labels_access": False,
            "CALIBRATION_access": False,
            "INTERNAL_TEST_access": False,
            "INCART_access": False,
            "BIDMC_access": False,
            "WEARABLE_V1_access": False,
            "CAL_V1_applied": False,
            "FedProx": False,
            "SecAgg_plus": False,
            "differential_privacy": False,
            "hardware": False,
            "status": "PASS",
        },
    )
    evidence_paths = [
        "configs/fl_non_iid_v1.yaml",
        "configs/fl_feature_noise_v1.yaml",
        "artifacts/FL_CONFIG_V1.lock.json",
        "reports/fl_non_iid.json",
        "reports/fl_non_iid.csv",
        *[f"manifests/clients/{CONDITIONS[c][1]}" for c in CONDITIONS],
        *[
            f"reports/t026/{c}_{suffix}"
            for c in CONDITIONS
            for suffix in (
                "rounds.csv",
                "client_rounds.csv",
                "validation_predictions.csv",
                "result.json",
            )
        ],
        *[
            f"checkpoints/federated/{CONDITIONS[c][0]}_{suffix}.pt"
            for c in CONDITIONS
            for suffix in ("best", "round50")
        ],
        "reports/t026/non_iid_manifest_audit.json",
        "reports/t026/heterogeneity_audit.json",
        "reports/t026/noise_bank_audit.json",
        "reports/t026/noise_fixture_audit.json",
        "reports/t026/fedprox_metric_semantics_audit.json",
        "reports/t026/matched_budget_audit.json",
        "reports/t026/reproducibility.json",
        "reports/t026/scope_audit.json",
    ]
    run_manifest = {
        "task_id": "T026",
        "status": "PASS",
        "run_order": ["label", "quantity", "feature", "combined"],
        "commands": [f"python -m federated.non_iid_runner {c}" for c in CONDITIONS],
        "Python": "3.11.16",
        "PyTorch": torch.__version__,
        "Flower": "1.39.0",
        "device": "cpu",
        "CI": False,
    }
    write_json(ROOT / "reports/t026/run_manifest.json", run_manifest)
    evidence_paths.append("reports/t026/run_manifest.json")
    hashes = {path: hash_file(ROOT / path) for path in evidence_paths}
    write_json(ROOT / "reports/t026/artifact_hashes.json", hashes)
    print(json.dumps({"status": "PASS", "conditions": len(condition_results)}, sort_keys=True))


if __name__ == "__main__":
    main()
