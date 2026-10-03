#!/usr/bin/env python3
"""V2-010 Sections 20-29: from frozen prediction tables ONLY (no further waveform access),
compute INTERNAL_TEST/INCART point metrics + paired patient-cluster bootstrap (reusing the
frozen F10/F11 draw matrices verbatim), the NSTDB six-SNR V1/V2 curves, and the two
predeclared zero-margin runtime-acceptance guards plus the final MODEL_V2_RUNTIME_ACCEPTED
decision. Must run strictly after all three guarded V2-only inference sessions have reached
COMPLETED. Every statistical rule is imported unchanged from scripts._v2_010_stats (frozen at
METHOD_COMMIT, before any dataset was opened).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np

import scripts._v2_010_lib as lib
from evaluation.bootstrap import bootstrap_replicates, percentile_summary
from evaluation.metrics import METRIC_NAMES, pooled_binary_metrics
from evaluation.noise import SNR_LEVELS, summarize_prediction_rows
from nhm.hashing import hash_file
from nhm.model_v2_second_look_guard import read_guard_state
from scripts._v2_010_stats import (
    incart_auroc_runtime_guard_pass,
    nstdb_no_collapse_pass,
    paired_bootstrap_delta,
    paired_bootstrap_summary,
    runtime_acceptance_decision,
)

ROOT = lib.ROOT
OUT = ROOT / "reports/model_v2/v2_010"


def _write_json(name: str, data: dict) -> None:
    (OUT / name).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row[key] for key in fields})


def _require_completed(dataset: str) -> None:
    state = read_guard_state(ROOT, dataset)
    if state is None or state.get("state") != "COMPLETED":
        raise lib.V2SecondLookError(
            f"CANNOT_COMPUTE_COMPARISON_BEFORE_GUARD_COMPLETED:{dataset}"
        )


# ---------------------------------------------------------------------------
# INTERNAL_TEST (descriptive only -- never a hard gate)
# ---------------------------------------------------------------------------


def compute_internal_comparison() -> dict[str, Any]:
    _require_completed("INTERNAL_TEST")
    with (OUT / "internal_v2_predictions.csv").open(newline="", encoding="utf-8") as handle:
        v2_rows = list(csv.DictReader(handle))
    patients = np.asarray([row["participant_group_id"] for row in v2_rows], dtype=str)
    labels = np.asarray([int(row["label"]) for row in v2_rows], dtype=np.int64)
    probabilities = np.asarray(
        [float(row["source_domain_calibrated_probability"]) for row in v2_rows]
    )
    predictions = np.asarray(
        [int(row["thresholded_prediction"]) for row in v2_rows], dtype=np.int64
    )
    v2_point = pooled_binary_metrics(labels, probabilities, predictions, patients)

    draws = np.load(ROOT / "reports/t018/bootstrap_draws.npz", allow_pickle=False)[
        "draws_int64"
    ]
    _, v2_replicate_rows = bootstrap_replicates(
        patients, labels, probabilities, predictions, replicates=2000, seed=20260927, draws=draws
    )
    v2_summary = percentile_summary(v2_point, v2_replicate_rows)

    with (ROOT / "reports/t018/bootstrap_replicates.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        v1_replicate_rows = list(csv.DictReader(handle))

    deltas_by_metric = {}
    for name in METRIC_NAMES:
        deltas = paired_bootstrap_delta(v1_replicate_rows, v2_replicate_rows, name)
        v1_point = float(json.loads((ROOT / "reports/internal_test.json").read_text())[
            "point_metrics"
        ][name])
        point_delta = float(v2_point[name]) - v1_point
        deltas_by_metric[name] = {
            "v1_point": v1_point,
            "v2_point": float(v2_point[name]),
            **paired_bootstrap_summary(point_delta, deltas),
        }

    _write_csv(
        OUT / "internal_bootstrap_replicates.csv",
        v2_replicate_rows,
        ["replicate_index", "sampled_patient_slots", "unique_patient_count", *METRIC_NAMES],
    )
    _write_json(
        "internal_bootstrap_summary.json",
        {"method": "PATIENT_CLUSTER_PERCENTILE_95_V1", "metrics": v2_summary},
    )

    comparison = {
        "dataset": "INTERNAL_TEST",
        "role": "DESCRIPTIVE_ONLY_NOT_A_HARD_GATE",
        "v2_point_metrics": {name: v2_point[name] for name in METRIC_NAMES},
        "paired_bootstrap_deltas": deltas_by_metric,
        "prediction_table_sha256": hash_file(OUT / "internal_v2_predictions.csv"),
    }
    _write_json("internal_comparison.json", comparison)
    return comparison


# ---------------------------------------------------------------------------
# INCART (hard gate: INCART_AUROC_RUNTIME_GUARD_PASS)
# ---------------------------------------------------------------------------


def compute_incart_comparison() -> dict[str, Any]:
    _require_completed("INCART")
    with (OUT / "incart_v2_predictions.csv").open(newline="", encoding="utf-8") as handle:
        v2_rows = list(csv.DictReader(handle))
    patients = np.asarray([row["participant_group_id"] for row in v2_rows], dtype=str)
    labels = np.asarray([int(row["label"]) for row in v2_rows], dtype=np.int64)
    probabilities = np.asarray(
        [float(row["source_domain_calibrated_probability"]) for row in v2_rows]
    )
    predictions = np.asarray(
        [int(row["thresholded_prediction"]) for row in v2_rows], dtype=np.int64
    )
    v2_point = pooled_binary_metrics(labels, probabilities, predictions, patients)

    draws = np.load(ROOT / "reports/t020/bootstrap_draws.npz", allow_pickle=False)[
        "draws_int64"
    ]
    _, v2_replicate_rows = bootstrap_replicates(
        patients, labels, probabilities, predictions, replicates=2000, seed=20260927, draws=draws
    )
    v2_summary = percentile_summary(v2_point, v2_replicate_rows)

    with (ROOT / "reports/t020/bootstrap_replicates.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        v1_replicate_rows = list(csv.DictReader(handle))
    with (ROOT / "reports/external_incart_metrics.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        v1_metric_rows = {row["metric"]: row for row in csv.DictReader(handle)}

    deltas_by_metric = {}
    for name in METRIC_NAMES:
        deltas = paired_bootstrap_delta(v1_replicate_rows, v2_replicate_rows, name)
        v1_point = float(v1_metric_rows[name]["point_estimate"])
        point_delta = float(v2_point[name]) - v1_point
        deltas_by_metric[name] = {
            "v1_point": v1_point,
            "v2_point": float(v2_point[name]),
            **paired_bootstrap_summary(point_delta, deltas),
        }

    auroc_ci_lower_95 = deltas_by_metric["AUROC"]["ci_lower_95"]
    guard_pass = incart_auroc_runtime_guard_pass(auroc_ci_lower_95)

    _write_csv(
        OUT / "incart_bootstrap_replicates.csv",
        v2_replicate_rows,
        ["replicate_index", "sampled_patient_slots", "unique_patient_count", *METRIC_NAMES],
    )
    _write_json(
        "incart_bootstrap_summary.json",
        {"method": "PATIENT_CLUSTER_PERCENTILE_95_V1", "metrics": v2_summary},
    )

    comparison = {
        "dataset": "INCART",
        "role": "HARD_GATE",
        "v2_point_metrics": {name: v2_point[name] for name in METRIC_NAMES},
        "paired_bootstrap_deltas": deltas_by_metric,
        "INCART_AUROC_RUNTIME_GUARD_PASS": guard_pass,
        "auroc_delta_ci_lower_95": auroc_ci_lower_95,
        "prediction_table_sha256": hash_file(OUT / "incart_v2_predictions.csv"),
    }
    _write_json("incart_comparison.json", comparison)
    return comparison


# ---------------------------------------------------------------------------
# NSTDB (hard gate: NSTDB_NO_COLLAPSE_PASS)
# ---------------------------------------------------------------------------


def _coerce_nstdb_v1_rows(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    return [
        {
            **row,
            "snr_db": int(row["snr_db"]),
            "label": int(row["label"]),
            "thresholded_prediction": int(row["thresholded_prediction"]),
            "transferred_source_domain_probability": float(
                row["transferred_source_domain_probability"]
            ),
        }
        for row in rows
    ]


def _coerce_nstdb_v2_rows(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    return [
        {
            **row,
            "snr_db": int(row["snr_db"]),
            "label": int(row["label"]),
            "thresholded_prediction": int(row["thresholded_prediction"]),
            "transferred_source_domain_probability": float(
                row["transferred_source_domain_probability"]
            ),
        }
        for row in rows
    ]


def compute_nstdb_comparison() -> dict[str, Any]:
    _require_completed("NSTDB")
    with (OUT / "nstdb_v2_predictions.csv").open(newline="", encoding="utf-8") as handle:
        v2_rows = _coerce_nstdb_v2_rows(list(csv.DictReader(handle)))
    with (ROOT / "reports/t019/nstdb_predictions.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        v1_rows = _coerce_nstdb_v1_rows(list(csv.DictReader(handle)))

    v1_pooled, v1_by_record = summarize_prediction_rows(v1_rows)
    v2_pooled, v2_by_record = summarize_prediction_rows(v2_rows)

    v1_by_snr = {row["snr_db"]: row for row in v1_pooled}
    v2_by_snr = {row["snr_db"]: row for row in v2_pooled}
    comparison_rows = []
    delta_auprc_by_snr: dict[int, float] = {}
    for snr in SNR_LEVELS:
        delta_auprc = float(v2_by_snr[snr]["AUPRC"]) - float(v1_by_snr[snr]["AUPRC"])
        delta_auprc_by_snr[snr] = delta_auprc
        comparison_rows.append(
            {
                "snr_db": snr,
                "v1_AUPRC": v1_by_snr[snr]["AUPRC"],
                "v2_AUPRC": v2_by_snr[snr]["AUPRC"],
                "delta_AUPRC_V2_minus_V1": delta_auprc,
                "v1_AUROC": v1_by_snr[snr]["AUROC"],
                "v2_AUROC": v2_by_snr[snr]["AUROC"],
                "v1_pooled_F1": v1_by_snr[snr]["pooled_F1"],
                "v2_pooled_F1": v2_by_snr[snr]["pooled_F1"],
                "v1_precision": v1_by_snr[snr]["precision"],
                "v2_precision": v2_by_snr[snr]["precision"],
                "v1_sensitivity": v1_by_snr[snr]["sensitivity"],
                "v2_sensitivity": v2_by_snr[snr]["sensitivity"],
                "v1_specificity": v1_by_snr[snr]["specificity"],
                "v2_specificity": v2_by_snr[snr]["specificity"],
                "v1_delta_AUPRC_vs_24dB": v1_by_snr[snr]["delta_AUPRC_vs_24dB"],
                "v2_delta_AUPRC_vs_24dB": v2_by_snr[snr]["delta_AUPRC_vs_24dB"],
            }
        )

    guard_pass = nstdb_no_collapse_pass(delta_auprc_by_snr)

    _write_csv(
        OUT / "nstdb_comparison.csv",
        comparison_rows,
        [
            "snr_db", "v1_AUPRC", "v2_AUPRC", "delta_AUPRC_V2_minus_V1", "v1_AUROC", "v2_AUROC",
            "v1_pooled_F1", "v2_pooled_F1", "v1_precision", "v2_precision", "v1_sensitivity",
            "v2_sensitivity", "v1_specificity", "v2_specificity", "v1_delta_AUPRC_vs_24dB",
            "v2_delta_AUPRC_vs_24dB",
        ],
    )

    by_record_rows = []
    v1_record_index = {(row["base_record_id"], row["snr_db"]): row for row in v1_by_record}
    v2_record_index = {(row["base_record_id"], row["snr_db"]): row for row in v2_by_record}
    for key in sorted(v1_record_index):
        v1_row, v2_row = v1_record_index[key], v2_record_index[key]
        by_record_rows.append(
            {
                "base_record_id": key[0],
                "snr_db": key[1],
                "v1_AUPRC": v1_row["AUPRC"],
                "v2_AUPRC": v2_row["AUPRC"],
                "delta_AUPRC_V2_minus_V1": float(v2_row["AUPRC"]) - float(v1_row["AUPRC"]),
                "v1_AUROC": v1_row["AUROC"],
                "v2_AUROC": v2_row["AUROC"],
            }
        )
    _write_csv(
        OUT / "nstdb_by_record.csv",
        by_record_rows,
        ["base_record_id", "snr_db", "v1_AUPRC", "v2_AUPRC", "delta_AUPRC_V2_minus_V1",
         "v1_AUROC", "v2_AUROC"],
    )

    return {
        "dataset": "NSTDB",
        "role": "HARD_GATE",
        "delta_auprc_by_snr": delta_auprc_by_snr,
        "NSTDB_NO_COLLAPSE_PASS": guard_pass,
        "prediction_table_sha256": hash_file(OUT / "nstdb_v2_predictions.csv"),
    }


# ---------------------------------------------------------------------------
# Final runtime-acceptance decision
# ---------------------------------------------------------------------------


def compute_runtime_acceptance_decision(
    incart_comparison: dict[str, Any], nstdb_comparison: dict[str, Any]
) -> dict[str, Any]:
    method_integrity_pass = all(
        read_guard_state(ROOT, dataset) is not None
        and read_guard_state(ROOT, dataset)["state"] == "COMPLETED"
        for dataset in ("INTERNAL_TEST", "INCART", "NSTDB")
    )
    decision = runtime_acceptance_decision(
        method_integrity_pass=method_integrity_pass,
        incart_guard_pass=incart_comparison["INCART_AUROC_RUNTIME_GUARD_PASS"],
        nstdb_guard_pass=nstdb_comparison["NSTDB_NO_COLLAPSE_PASS"],
    )
    result = {
        "MODEL_V2_RUNTIME_ACCEPTED": decision,
        "method_integrity_pass": method_integrity_pass,
        "INCART_AUROC_RUNTIME_GUARD_PASS": incart_comparison["INCART_AUROC_RUNTIME_GUARD_PASS"],
        "NSTDB_NO_COLLAPSE_PASS": nstdb_comparison["NSTDB_NO_COLLAPSE_PASS"],
        "internal_test_participates_in_decision": False,
        "operational_lineage": "MODEL_V1",
        "subjective_override_applied": False,
    }
    _write_json("runtime_acceptance_decision.json", result)
    return result


def main() -> None:
    internal_comparison = compute_internal_comparison()
    incart_comparison = compute_incart_comparison()
    nstdb_comparison = compute_nstdb_comparison()
    _write_json("incart_comparison.json", incart_comparison)
    _write_json("nstdb_comparison_summary.json", nstdb_comparison)
    decision = compute_runtime_acceptance_decision(incart_comparison, nstdb_comparison)
    print(json.dumps({
        "internal_role": internal_comparison["role"],
        "incart_guard": incart_comparison["INCART_AUROC_RUNTIME_GUARD_PASS"],
        "nstdb_guard": nstdb_comparison["NSTDB_NO_COLLAPSE_PASS"],
        "decision": decision["MODEL_V2_RUNTIME_ACCEPTED"],
    }, indent=2))


if __name__ == "__main__":
    main()
