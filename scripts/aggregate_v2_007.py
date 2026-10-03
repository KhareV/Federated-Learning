#!/usr/bin/env python3
"""V2-007 Sections 33-37: prediction closure, V1 reconstruction check, point metrics, patient
diagnostics, and TRAIN->VALIDATION gap. Reads only already-frozen prediction CSVs -- no model
inference, no waveform access.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict

import numpy as np

import scripts._v2_007_lib as lib
import scripts._v2_007_stats as stats

OUT_DIR = lib.ROOT / "reports/model_v2/v2_007"

EXPECTED_V1_AUPRC = {
    20260927: 0.5328607838787021,
    20260928: 0.4794350072114173,
    20260929: 0.4825433837968652,
}
EXPECTED_V1_MEAN = 0.49827972496232814
TOLERANCE = 1e-9


def _read(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def prediction_closure_audit(v2_rows: list[dict], v1_rows: list[dict]) -> dict:
    by_config = defaultdict(list)
    for row in v2_rows:
        by_config[row["configuration_id"]].append(row)

    config_closures = {}
    label_by_example_overall: dict[str, str] = {}
    group_by_example_overall: dict[str, str] = {}
    violations = []
    for config_id, rows in by_config.items():
        example_ids = [r["example_id"] for r in rows]
        groups = {r["participant_group_id"] for r in rows}
        positives = sum(1 for r in rows if r["label"] == "1")
        negatives = sum(1 for r in rows if r["label"] == "0")
        duplicates = len(example_ids) - len(set(example_ids))
        config_closures[config_id] = {
            "windows": len(rows), "groups": len(groups), "positive": positives,
            "negative": negatives, "duplicates": duplicates,
        }
        if len(rows) != 2880 or len(groups) != 7 or positives != 676 or negatives != 2204:
            violations.append(config_id)
        for r in rows:
            prior_label = label_by_example_overall.get(r["example_id"])
            if prior_label is not None and prior_label != r["label"]:
                violations.append(f"label_mismatch:{r['example_id']}")
            label_by_example_overall[r["example_id"]] = r["label"]
            prior_group = group_by_example_overall.get(r["example_id"])
            if prior_group is not None and prior_group != r["participant_group_id"]:
                violations.append(f"group_mismatch:{r['example_id']}")
            group_by_example_overall[r["example_id"]] = r["participant_group_id"]

    v1_by_seed = defaultdict(list)
    for row in v1_rows:
        v1_by_seed[row["seed"]].append(row)
    v1_closures = {}
    for seed, rows in v1_by_seed.items():
        example_ids = [r["example_id"] for r in rows]
        groups = {r["participant_group_id"] for r in rows}
        positives = sum(1 for r in rows if r["label"] == "1")
        negatives = sum(1 for r in rows if r["label"] == "0")
        duplicates = len(example_ids) - len(set(example_ids))
        v1_closures[seed] = {
            "windows": len(rows), "groups": len(groups), "positive": positives,
            "negative": negatives, "duplicates": duplicates,
        }
        if len(rows) != 2880 or len(groups) != 7 or positives != 676 or negatives != 2204:
            violations.append(f"v1_seed_{seed}")

    data = {
        "v2_config_closures": config_closures,
        "v1_seed_closures": v1_closures,
        "total_v2_rows": len(v2_rows),
        "total_v1_rows": len(v1_rows),
        "expected_v2_rows": 2 * 3 * 2880,
        "expected_v1_rows": 3 * 2880,
        "violations": violations,
        "status": "PASS" if (
            not violations and len(v2_rows) == 17280 and len(v1_rows) == 8640
        ) else "FAIL",
    }
    (OUT_DIR / "prediction_closure_audit.json").write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return data


def v1_reconstruction_check(v1_rows: list[dict]) -> dict:
    by_seed = defaultdict(list)
    for row in v1_rows:
        by_seed[int(row["seed"])].append(row)
    per_seed = {}
    for seed, rows in by_seed.items():
        labels = np.array([int(r["label"]) for r in rows])
        probs = np.array([float(r["raw_probability"]) for r in rows])
        auprc, auroc = stats.pooled_metrics(labels, probs)
        expected = EXPECTED_V1_AUPRC[seed]
        per_seed[str(seed)] = {
            "reconstructed_auprc": auprc, "reconstructed_auroc": auroc,
            "expected_auprc": expected, "match": abs(auprc - expected) < TOLERANCE,
        }
    mean_auprc = float(np.mean([v["reconstructed_auprc"] for v in per_seed.values()]))
    mean_match = abs(mean_auprc - EXPECTED_V1_MEAN) < TOLERANCE
    all_match = all(v["match"] for v in per_seed.values()) and mean_match
    data = {
        "per_seed": per_seed,
        "reconstructed_three_seed_mean_auprc": mean_auprc,
        "expected_three_seed_mean_auprc": EXPECTED_V1_MEAN,
        "mean_match": mean_match,
        "all_historical_values_reproduced": all_match,
        "classification": "RECONSTRUCTION_VERIFIED" if all_match else (
            "V1_REFERENCE_RECONSTRUCTION_MISMATCH"
        ),
        "status": "PASS" if all_match else "FAIL_V1_REFERENCE_RECONSTRUCTION",
    }
    (OUT_DIR / "v1_reference_reconstruction_audit.json").write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return data


def per_seed_validation_metrics(v2_rows: list[dict]) -> list[dict]:
    by_config = defaultdict(list)
    for row in v2_rows:
        by_config[row["configuration_id"]].append(row)
    out = []
    for config_id, rows in by_config.items():
        labels = np.array([int(r["label"]) for r in rows])
        probs = np.array([float(r["raw_probability"]) for r in rows])
        auprc, auroc = stats.pooled_metrics(labels, probs)
        out.append(
            {
                "configuration_id": config_id,
                "architecture_id": rows[0]["architecture_id"],
                "schedule_id": rows[0]["schedule_id"],
                "seed": rows[0]["seed"],
                "official_validation_auprc": auprc,
                "official_validation_auroc": auroc,
                "windows": len(rows),
            }
        )
    out.sort(key=lambda r: r["configuration_id"])
    with (OUT_DIR / "per_seed_validation_metrics.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, lineterminator="\n", fieldnames=list(out[0].keys()))
        writer.writeheader()
        writer.writerows(out)
    return out


def finalist_validation_summary(per_seed: list[dict]) -> list[dict]:
    by_arch = defaultdict(dict)
    for row in per_seed:
        by_arch[row["architecture_id"]][int(row["seed"])] = row

    rows = []
    for finalist in lib.FINALISTS:
        arch = finalist["architecture_id"]
        seed_rows = by_arch[arch]
        auprc_values = {seed: seed_rows[seed]["official_validation_auprc"] for seed in lib.SEEDS}
        auroc_values = {seed: seed_rows[seed]["official_validation_auroc"] for seed in lib.SEEDS}
        auprc_stats = stats.three_seed_stats(auprc_values)
        auroc_stats = stats.three_seed_stats(auroc_values)
        rows.append(
            {
                "finalist": finalist["finalist"],
                "architecture_id": arch,
                "schedule_id": finalist["schedule_id"],
                "mean_auprc": auprc_stats["mean"],
                "sd_auprc": auprc_stats["sd"],
                "min_auprc": auprc_stats["min"],
                "mean_auroc": auroc_stats["mean"],
                "sd_auroc": auroc_stats["sd"],
                "min_auroc": auroc_stats["min"],
                "parameter_count": lib.EXPECTED_PARAMETER_COUNTS[arch],
                "seed_20260927_auprc": auprc_values[20260927],
                "seed_20260928_auprc": auprc_values[20260928],
                "seed_20260929_auprc": auprc_values[20260929],
            }
        )
    with (OUT_DIR / "finalist_validation_summary.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, lineterminator="\n", fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return rows


def patient_diagnostics(v2_rows: list[dict], v1_rows: list[dict]) -> None:
    combined = []
    for r in v2_rows:
        combined.append(
            {"model_key": r["configuration_id"], "group": r["participant_group_id"],
             "label": int(r["label"]), "prob": float(r["raw_probability"])}
        )
    for r in v1_rows:
        combined.append(
            {"model_key": f"MODEL_V1_S{r['seed']}", "group": r["participant_group_id"],
             "label": int(r["label"]), "prob": float(r["raw_probability"])}
        )
    by_key_group = defaultdict(list)
    for row in combined:
        by_key_group[(row["model_key"], row["group"])].append(row)

    out = []
    for (model_key, group), rows in sorted(by_key_group.items()):
        labels = np.array([r["label"] for r in rows])
        probs = np.array([r["prob"] for r in rows])
        pos_mask = labels == 1
        neg_mask = labels == 0
        out.append(
            {
                "model_key": model_key,
                "participant_group_id": group,
                "window_count": len(rows),
                "positive_count": int(pos_mask.sum()),
                "negative_count": int(neg_mask.sum()),
                "prevalence": float(pos_mask.sum() / len(rows)),
                "mean_probability_overall": float(np.mean(probs)),
                "mean_probability_positive": (
                    float(np.mean(probs[pos_mask])) if pos_mask.any() else None
                ),
                "mean_probability_negative": (
                    float(np.mean(probs[neg_mask])) if neg_mask.any() else None
                ),
            }
        )
    with (OUT_DIR / "patient_diagnostics.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, lineterminator="\n", fieldnames=list(out[0].keys()))
        writer.writeheader()
        writer.writerows(out)


def train_validation_gap(per_seed: list[dict]) -> None:
    fit_rows = _read(OUT_DIR / "fit_summary.csv")
    source_train_by_exp = {r["experiment_id"]: r for r in fit_rows}
    out = []
    for row in per_seed:
        exp_id = row["configuration_id"]
        source = source_train_by_exp[exp_id]
        source_auprc = float(source["source_train_auprc"])
        validation_auprc = row["official_validation_auprc"]
        out.append(
            {
                "configuration_id": exp_id,
                "architecture_id": row["architecture_id"],
                "seed": row["seed"],
                "source_train_auprc": source_auprc,
                "official_validation_auprc": validation_auprc,
                "gap": source_auprc - validation_auprc,
            }
        )
    with (OUT_DIR / "train_validation_gap.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, lineterminator="\n", fieldnames=list(out[0].keys()))
        writer.writeheader()
        writer.writerows(out)


def main() -> None:
    v2_rows = _read(OUT_DIR / "official_validation_predictions.csv")
    v1_rows = _read(OUT_DIR / "v1_reference_validation_predictions.csv")

    closure = prediction_closure_audit(v2_rows, v1_rows)
    if closure["status"] != "PASS":
        raise RuntimeError("prediction closure FAILED -- stopping before any decision")

    reconstruction = v1_reconstruction_check(v1_rows)
    if reconstruction["status"] != "PASS":
        print("V1_REFERENCE_RECONSTRUCTION_MISMATCH -- stopping, not repairing")
        return

    per_seed = per_seed_validation_metrics(v2_rows)
    finalist_validation_summary(per_seed)
    patient_diagnostics(v2_rows, v1_rows)
    train_validation_gap(per_seed)
    print("V2-007 aggregation complete.")


if __name__ == "__main__":
    main()
