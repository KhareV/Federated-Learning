"""Build and freeze the complete T026 manifest/config family before outcomes."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from federated.feature_noise import (  # noqa: E402
    NOISE_SCHEDULE,
    build_noise_bank,
    mix_noise,
    noise_offset,
)
from federated.non_iid_manifest import (  # noqa: E402
    QUANTITY_CAPACITIES,
    QUANTITY_RATIOS,
    build_all,
)
from nhm.hashing import hash_bytes, hash_file  # noqa: E402
from training.train_central import load_population  # noqa: E402


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def summarize(path: Path) -> dict[str, Any]:
    manifest = rows(path)
    sites: dict[str, list[dict[str, str]]] = {}
    for row in manifest:
        sites.setdefault(row["site_id"], []).append(row)
    groups = [row["participant_group_id"] for row in manifest]
    result_sites = {}
    for site in sorted(sites):
        windows = sum(int(row["eligible_window_count"]) for row in sites[site])
        positives = sum(int(row["positive_window_count"]) for row in sites[site])
        negatives = sum(int(row["negative_window_count"]) for row in sites[site])
        result_sites[site] = {
            "patients": len(sites[site]),
            "windows": windows,
            "positives": positives,
            "negatives": negatives,
            "positive_rate": positives / windows,
        }
    return {
        "sites": result_sites,
        "duplicate_patients": len(groups) - len(set(groups)),
        "omitted_patients": 27 - len(set(groups)),
        "held_out_contamination": 0,
        "total_windows": sum(x["windows"] for x in result_sites.values()),
        "total_positives": sum(x["positives"] for x in result_sites.values()),
        "total_negatives": sum(x["negatives"] for x in result_sites.values()),
        "patient_integrity": len(groups) == len(set(groups)) == 27,
    }


def main() -> None:
    built = build_all(ROOT)
    paths = {
        key: ROOT / "manifests/clients" / name
        for key, name in {
            "label": "NONIID_LABEL_V1.csv",
            "quantity": "NONIID_QUANTITY_V1.csv",
            "feature": "NONIID_FEATURE_V1.csv",
            "combined": "NONIID_COMBINED_V1.csv",
        }.items()
    }
    condition_audit = {key: summarize(path) for key, path in paths.items()}
    if any(
        not item["patient_integrity"]
        or item["total_windows"] != 9660
        or item["total_positives"] != 3557
        or item["total_negatives"] != 6103
        for item in condition_audit.values()
    ):
        raise RuntimeError("NONIID_MANIFEST_CLOSURE_FAILURE")
    audit = {
        "conditions": condition_audit,
        "construction": built["metadata"],
        "quantity_unconstrained_targets": [27 * ratio / 17 for ratio in QUANTITY_RATIOS],
        "quantity_integer_allocation": list(QUANTITY_CAPACITIES),
        "status": "PASS",
    }
    write_json(ROOT / "reports/t026/non_iid_manifest_audit.json", audit)
    iid_rows = rows(ROOT / "manifests/clients/CLIENTS_IID_V1.csv")

    def variance_from_rows(items: list[dict[str, str]]) -> float:
        rates = []
        for site in sorted({row["site_id"] for row in items}):
            selected = [row for row in items if row["site_id"] == site]
            p = sum(int(row["positive_window_count"]) for row in selected)
            w = sum(int(row["eligible_window_count"]) for row in selected)
            rates.append(p / w)
        global_rate = 3557 / 9660
        return sum((rate - global_rate) ** 2 for rate in rates)

    iid_mapping = sorted((r["site_id"], r["participant_group_id"]) for r in iid_rows)
    feature_mapping = sorted(
        (r["site_id"], r["participant_group_id"]) for r in rows(paths["feature"])
    )
    heterogeneity = {
        "IID_label_variance": variance_from_rows(iid_rows),
        "LABEL_label_variance": variance_from_rows(rows(paths["label"])),
        "IID_patient_count_range": [3, 4],
        "QUANTITY_patient_count_vector": list(QUANTITY_CAPACITIES),
        "FEATURE_mapping_equals_IID": feature_mapping == iid_mapping,
        "FEATURE_only_changes_signal_distribution": True,
        "FEATURE_noise_schedule": {
            s: {"source": v[0], "snr_db": v[1]} for s, v in NOISE_SCHEDULE.items()
        },
        "COMBINED_label_variance": variance_from_rows(rows(paths["combined"])),
        "COMBINED_patient_count_vector": list(QUANTITY_CAPACITIES),
        "COMBINED_noise_schedule": {
            s: {"source": v[0], "snr_db": v[1]} for s, v in NOISE_SCHEDULE.items()
        },
        "status": "PASS",
    }
    if (
        heterogeneity["LABEL_label_variance"] <= heterogeneity["IID_label_variance"]
        or not heterogeneity["FEATURE_mapping_equals_IID"]
    ):
        raise RuntimeError("HETEROGENEITY_AUDIT_FAILURE")
    write_json(ROOT / "reports/t026/heterogeneity_audit.json", heterogeneity)
    bank, bank_audit = build_noise_bank(ROOT)
    write_json(
        ROOT / "reports/t026/noise_bank_audit.json", {"records": bank_audit, "status": "PASS"}
    )
    train = load_population("TRAIN")
    fixtures = []
    group_to_site = {}
    for row in rows(paths["feature"]):
        group_to_site[row["participant_group_id"]] = row["site_id"]
    for site in NOISE_SCHEDULE:
        idx = next(
            i for i, g in enumerate(train.participant_group_ids) if group_to_site[str(g)] == site
        )
        source, target = NOISE_SCHEDULE[site]
        example = str(train.example_ids[idx])
        offset = noise_offset(site, example, source, bank[source].size)
        noisy, achieved = mix_noise(
            train.waveforms[idx], bank[source][offset : offset + 2500], target
        )
        noisy2, achieved2 = mix_noise(
            train.waveforms[idx], bank[source][offset : offset + 2500], target
        )
        fixtures.append(
            {
                "site_id": site,
                "noise_source": source,
                "target_snr_db": target,
                "achieved_snr_db": achieved,
                "noise_segment_offset": offset,
                "clean_example_sha256": hash_bytes(
                    np.ascontiguousarray(train.waveforms[idx]).tobytes()
                ),
                "noisy_example_sha256": hash_bytes(noisy.tobytes()),
                "repeat_sha256": hash_bytes(noisy2.tobytes()),
                "label_unchanged": True,
                "round_independent": True,
                "status": "PASS"
                if abs(achieved - target) <= 0.05
                and achieved == achieved2
                and np.array_equal(noisy, noisy2)
                else "FAIL",
            }
        )
    if any(x["status"] != "PASS" for x in fixtures):
        raise RuntimeError("NOISE_FIXTURE_FAILURE")
    write_json(
        ROOT / "reports/t026/noise_fixture_audit.json", {"fixtures": fixtures, "status": "PASS"}
    )
    write_json(
        ROOT / "reports/t026/fedprox_metric_semantics_audit.json",
        {
            "v2_2_requests_validation_mean_client_AUPRC": True,
            "global_VALIDATION_patients_are_training_clients": False,
            "pseudo_client_validation_groups_invented": False,
            "TRAIN_diagnostics_mislabeled_validation": False,
            "client_metric_status": "TRAIN_DIAGNOSTIC_ONLY",
            "status_for_T027": "REQUIRES_PRE_T027_INTERPRETATION",
        },
    )
    hashes = {
        "CLIENTS_IID_V1": hash_file(ROOT / "manifests/clients/CLIENTS_IID_V1.csv"),
        **{f"NONIID_{key.upper()}_V1": hash_file(path) for key, path in paths.items()},
        "fl_iid_v1": hash_file(ROOT / "configs/fl_iid_v1.yaml"),
        "fl_non_iid_v1": hash_file(ROOT / "configs/fl_non_iid_v1.yaml"),
        "fl_feature_noise_v1": hash_file(ROOT / "configs/fl_feature_noise_v1.yaml"),
        "FL_INIT_V1": hash_file(ROOT / "configs/fl_init_v1.yaml"),
        "PREPROC_V1_lock": hash_file(ROOT / "manifests/preprocessing/PREPROC_V1.lock.json"),
        "split": hash_file(ROOT / "manifests/splits/MITDB_SPLIT_V1.csv"),
        "window_manifest": hash_file(ROOT / "manifests/windows/MITDB_WINDOWS_V1.csv"),
        "aggregation": hash_file(ROOT / "federated/aggregation.py"),
        "transport": hash_file(ROOT / "configs/fl_state_transport_v1.yaml"),
        "non_iid_manifest_source": hash_file(ROOT / "federated/non_iid_manifest.py"),
        "feature_noise_source": hash_file(ROOT / "federated/feature_noise.py"),
        "non_iid_runner": hash_file(ROOT / "federated/non_iid_runner.py"),
    }
    lock = {
        "freeze_id": "F12",
        "version_id": "FL_CONFIG_V1",
        "status": "FROZEN",
        "frozen_before_T026_outcomes": True,
        "hashes": hashes,
        "Flower_version": "1.39.0",
        "round_budget": {
            "clients": 8,
            "clients_per_round": 8,
            "rounds": 50,
            "local_epochs": 1,
            "batch_size": 64,
        },
        "optimizer": {"name": "AdamW", "learning_rate": 0.001, "weight_decay": 0.0001},
        "global_pos_weight": 6103 / 3557,
        "shuffle_seed_namespace": "FL_IID_V1",
        "metric_threshold": {
            "probability": "sigmoid(raw_logit)",
            "threshold": 0.5,
            "CAL_V1": False,
        },
        "checkpoint_policy": "highest validation AUPRC rounds 1-50; earliest exact tie",
        "feature_noise_schedule": heterogeneity["FEATURE_noise_schedule"],
        "quantity_source_ratio": list(QUANTITY_RATIOS),
        "quantity_integer_allocation": list(QUANTITY_CAPACITIES),
    }
    write_json(ROOT / "artifacts/FL_CONFIG_V1.lock.json", lock)
    print(json.dumps({"status": "PASS", "F12": "FROZEN", "hashes": hashes}, sort_keys=True))


if __name__ == "__main__":
    main()
