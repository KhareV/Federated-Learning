#!/usr/bin/env python3
"""V2-007 Section 38: patient-cluster bootstrap distributions per finalist x seed, and the
three-seed-mean replicate distribution, from the frozen MODEL_V2_VALIDATION_BOOTSTRAP_DRAWS_V1
matrix and the frozen official-VALIDATION predictions. No model inference, no waveform access.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict

import numpy as np

import scripts._v2_007_lib as lib
import scripts._v2_007_stats as stats

OUT_DIR = lib.ROOT / "reports/model_v2/v2_007"


def _read(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_draws() -> tuple[np.ndarray, list[str]]:
    manifest = json.loads(
        (OUT_DIR / "validation_bootstrap_draws_manifest.json").read_text(encoding="utf-8")
    )
    draws = np.load(OUT_DIR / "validation_bootstrap_draws.npz")["draws"]
    return draws, manifest["sorted_patient_index_mapping"]


def labels_probs_by_group(rows: list[dict]) -> tuple[dict, dict]:
    labels_by_group: dict[str, list[int]] = defaultdict(list)
    probs_by_group: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        labels_by_group[r["participant_group_id"]].append(int(r["label"]))
        probs_by_group[r["participant_group_id"]].append(float(r["raw_probability"]))
    return (
        {g: np.array(v) for g, v in labels_by_group.items()},
        {g: np.array(v) for g, v in probs_by_group.items()},
    )


def main() -> None:
    draws, group_order = load_draws()
    v2_rows = _read(OUT_DIR / "official_validation_predictions.csv")
    v1_rows = _read(OUT_DIR / "v1_reference_validation_predictions.csv")

    v2_by_config = defaultdict(list)
    for r in v2_rows:
        v2_by_config[r["configuration_id"]].append(r)
    v1_by_seed = defaultdict(list)
    for r in v1_rows:
        v1_by_seed[int(r["seed"])].append(r)

    seed_metric_rows = []
    config_distributions: dict[str, np.ndarray] = {}
    for config_id, rows in v2_by_config.items():
        labels_by_group, probs_by_group = labels_probs_by_group(rows)
        dist = stats.bootstrap_auprc_distribution(
            draws, group_order, labels_by_group, probs_by_group
        )
        config_distributions[config_id] = dist
        seed_metric_rows.append(
            {
                "configuration_id": config_id,
                "architecture_id": rows[0]["architecture_id"],
                "seed": rows[0]["seed"],
                "valid_replicates": int(np.sum(~np.isnan(dist))),
                "invalid_replicates": int(np.sum(np.isnan(dist))),
                "bootstrap_mean_auprc": float(np.nanmean(dist)),
            }
        )

    v1_distributions: dict[int, np.ndarray] = {}
    for seed, rows in v1_by_seed.items():
        labels_by_group, probs_by_group = labels_probs_by_group(rows)
        dist = stats.bootstrap_auprc_distribution(
            draws, group_order, labels_by_group, probs_by_group
        )
        v1_distributions[seed] = dist
        seed_metric_rows.append(
            {
                "configuration_id": f"MODEL_V1_S{seed}",
                "architecture_id": "MODEL_V1",
                "seed": seed,
                "valid_replicates": int(np.sum(~np.isnan(dist))),
                "invalid_replicates": int(np.sum(np.isnan(dist))),
                "bootstrap_mean_auprc": float(np.nanmean(dist)),
            }
        )

    seed_metric_rows.sort(key=lambda r: r["configuration_id"])
    seed_fields = list(seed_metric_rows[0].keys())
    with (OUT_DIR / "bootstrap_seed_metrics.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, lineterminator="\n", fieldnames=seed_fields)
        writer.writeheader()
        writer.writerows(seed_metric_rows)

    by_arch_seed_dist: dict[str, dict[int, np.ndarray]] = defaultdict(dict)
    for config_id, dist in config_distributions.items():
        rows = v2_by_config[config_id]
        arch = rows[0]["architecture_id"]
        seed = int(rows[0]["seed"])
        by_arch_seed_dist[arch][seed] = dist

    finalist_rep_mean: dict[str, np.ndarray] = {}
    three_seed_rows = []
    for arch, seed_dists in by_arch_seed_dist.items():
        rep_mean = stats.three_seed_mean_replicate_distribution(seed_dists)
        finalist_rep_mean[arch] = rep_mean
        three_seed_rows.append(
            {
                "architecture_id": arch,
                "valid_replicates": int(np.sum(~np.isnan(rep_mean))),
                "invalid_replicates": int(np.sum(np.isnan(rep_mean))),
                "bootstrap_mean_auprc": float(np.nanmean(rep_mean)),
            }
        )
    v1_rep_mean = stats.three_seed_mean_replicate_distribution(v1_distributions)
    three_seed_rows.append(
        {
            "architecture_id": "MODEL_V1",
            "valid_replicates": int(np.sum(~np.isnan(v1_rep_mean))),
            "invalid_replicates": int(np.sum(np.isnan(v1_rep_mean))),
            "bootstrap_mean_auprc": float(np.nanmean(v1_rep_mean)),
        }
    )
    three_seed_fields = list(three_seed_rows[0].keys())
    with (OUT_DIR / "bootstrap_three_seed_metrics.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, lineterminator="\n", fieldnames=three_seed_fields)
        writer.writeheader()
        writer.writerows(three_seed_rows)

    np.savez(
        OUT_DIR / "finalist_rep_mean_distributions.npz",
        A=finalist_rep_mean["MODEL_V2_TCN_MEAN"],
        B=finalist_rep_mean["MODEL_V2_TCN_MEANMAX"],
        V1=v1_rep_mean,
        **{f"V1_S{seed}": dist for seed, dist in v1_distributions.items()},
        **{
            f"{arch}_S{seed}": dist
            for arch, seed_dists in by_arch_seed_dist.items()
            for seed, dist in seed_dists.items()
        },
    )

    summary = {
        "B": 2000,
        "bootstrap_id": "MODEL_V2_VALIDATION_BOOTSTRAP_DRAWS_V1",
        "finalist_a_rep_mean_valid": int(np.sum(~np.isnan(finalist_rep_mean["MODEL_V2_TCN_MEAN"]))),
        "finalist_b_rep_mean_valid": int(
            np.sum(~np.isnan(finalist_rep_mean["MODEL_V2_TCN_MEANMAX"]))
        ),
        "v1_rep_mean_valid": int(np.sum(~np.isnan(v1_rep_mean))),
        "status": "PASS",
    }
    (OUT_DIR / "bootstrap_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
