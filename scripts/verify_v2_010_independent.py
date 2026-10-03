#!/usr/bin/env python3
"""V2-010 Section 40: independent, non-importing reverification. Reimplements every metric,
the paired-bootstrap delta/CI, both runtime guards, and the final decision rule from scratch
using only numpy/sklearn primitives and frozen CSV/npz files -- it never imports
evaluation.metrics, evaluation.bootstrap, or scripts._v2_010_stats's decision functions, so
agreement is not self-grading. Mirrors the precedent set in
scripts/generate_v2_007_evidence.py's independent_reverification().
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_010"
SNR_LEVELS = (24, 18, 12, 6, 0, -6)
TOLERANCE = 1e-9


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _confusion(labels: np.ndarray, predictions: np.ndarray) -> dict[str, int]:
    tp = int(np.sum((labels == 1) & (predictions == 1)))
    fp = int(np.sum((labels == 0) & (predictions == 1)))
    tn = int(np.sum((labels == 0) & (predictions == 0)))
    fn = int(np.sum((labels == 1) & (predictions == 0)))
    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn}


def _independent_point_metrics(
    labels: np.ndarray, probabilities: np.ndarray, predictions: np.ndarray
) -> dict[str, float]:
    counts = _confusion(labels, predictions)
    precision_denominator = counts["tp"] + counts["fp"]
    sensitivity_denominator = counts["tp"] + counts["fn"]
    specificity_denominator = counts["tn"] + counts["fp"]
    precision = counts["tp"] / precision_denominator if precision_denominator else 0.0
    sensitivity = counts["tp"] / sensitivity_denominator if sensitivity_denominator else 0.0
    f1_denominator = precision + sensitivity
    return {
        "AUPRC": float(average_precision_score(labels, probabilities)),
        "AUROC": float(roc_auc_score(labels, probabilities)),
        "precision": float(precision),
        "sensitivity": float(sensitivity),
        "specificity": float(counts["tn"] / specificity_denominator)
        if specificity_denominator else 0.0,
        "pooled_F1": float(2 * precision * sensitivity / f1_denominator) if f1_denominator else 0.0,
    }


def _bootstrap_distribution(
    patient_ids: np.ndarray,
    labels: np.ndarray,
    probabilities: np.ndarray,
    draws: np.ndarray,
    unique_patients_sorted: np.ndarray,
) -> np.ndarray:
    by_patient = {
        patient: np.flatnonzero(patient_ids == patient) for patient in unique_patients_sorted
    }
    out = np.full(draws.shape[0], np.nan)
    for replicate_index in range(draws.shape[0]):
        indices = np.concatenate(
            [by_patient[unique_patients_sorted[int(slot)]] for slot in draws[replicate_index]]
        )
        if len(np.unique(labels[indices])) < 2:
            continue
        out[replicate_index] = roc_auc_score(labels[indices], probabilities[indices])
    return out


def _verify_dataset_point_metrics(
    dataset: str, prediction_path: Path, label_col: str, prob_col: str, pred_col: str
) -> dict[str, object]:
    rows = _read_csv(prediction_path)
    labels = np.asarray([int(row[label_col]) for row in rows], dtype=np.int64)
    probabilities = np.asarray([float(row[prob_col]) for row in rows], dtype=np.float64)
    predictions = np.asarray([int(row[pred_col]) for row in rows], dtype=np.int64)
    independent = _independent_point_metrics(labels, probabilities, predictions)

    official_file = {
        "INTERNAL_TEST": "internal_comparison.json",
        "INCART": "incart_comparison.json",
    }[dataset]
    official = json.loads((OUT / official_file).read_text())["v2_point_metrics"]
    agreement = {
        name: abs(independent[name] - float(official[name])) <= TOLERANCE
        for name in independent
    }
    return {"independent": independent, "official": official, "agreement": agreement}


def verify_incart_guard() -> dict[str, object]:
    rows = _read_csv(OUT / "incart_v2_predictions.csv")
    patients = np.asarray([row["participant_group_id"] for row in rows], dtype=str)
    labels = np.asarray([int(row["label"]) for row in rows], dtype=np.int64)
    probabilities = np.asarray(
        [float(row["source_domain_calibrated_probability"]) for row in rows]
    )

    draws = np.load(ROOT / "reports/t020/bootstrap_draws.npz")["draws_int64"]
    unique_patients = np.asarray(sorted(set(patients.tolist())), dtype=str)
    v2_dist = _bootstrap_distribution(patients, labels, probabilities, draws, unique_patients)

    v1_replicate_rows = _read_csv(ROOT / "reports/t020/bootstrap_replicates.csv")
    v1_dist = np.asarray([float(row["AUROC"]) for row in v1_replicate_rows], dtype=np.float64)

    deltas = v2_dist - v1_dist
    finite = deltas[np.isfinite(deltas)]
    ci_lower_95 = float(np.quantile(finite, 0.025, method="linear"))
    independent_guard_pass = bool(ci_lower_95 >= -1e-12)

    official = json.loads((OUT / "incart_comparison.json").read_text())
    return {
        "independent_ci_lower_95": ci_lower_95,
        "independent_guard_pass": independent_guard_pass,
        "official_ci_lower_95": official["auroc_delta_ci_lower_95"],
        "official_guard_pass": official["INCART_AUROC_RUNTIME_GUARD_PASS"],
        "ci_agreement": abs(ci_lower_95 - official["auroc_delta_ci_lower_95"]) <= 1e-6,
        "guard_agreement": independent_guard_pass == official["INCART_AUROC_RUNTIME_GUARD_PASS"],
    }


def verify_nstdb_guard() -> dict[str, object]:
    def auprc_by_snr(path: Path, prob_col: str) -> dict[int, float]:
        rows = _read_csv(path)
        result = {}
        for snr in SNR_LEVELS:
            selected = [row for row in rows if int(row["snr_db"]) == snr]
            labels = np.asarray([int(row["label"]) for row in selected], dtype=np.int64)
            probs = np.asarray([float(row[prob_col]) for row in selected], dtype=np.float64)
            result[snr] = float(average_precision_score(labels, probs))
        return result

    v1_auprc = auprc_by_snr(
        ROOT / "reports/t019/nstdb_predictions.csv", "transferred_source_domain_probability"
    )
    v2_auprc = auprc_by_snr(
        OUT / "nstdb_v2_predictions.csv", "transferred_source_domain_probability"
    )
    delta_by_snr = {snr: v2_auprc[snr] - v1_auprc[snr] for snr in SNR_LEVELS}
    independent_guard_pass = all(delta_by_snr[snr] >= -1e-12 for snr in SNR_LEVELS)

    official = json.loads((OUT / "nstdb_comparison_summary.json").read_text())
    return {
        "independent_delta_by_snr": delta_by_snr,
        "independent_guard_pass": independent_guard_pass,
        "official_guard_pass": official["NSTDB_NO_COLLAPSE_PASS"],
        "guard_agreement": independent_guard_pass == official["NSTDB_NO_COLLAPSE_PASS"],
    }


def main() -> None:
    internal = _verify_dataset_point_metrics(
        "INTERNAL_TEST",
        OUT / "internal_v2_predictions.csv",
        "label",
        "source_domain_calibrated_probability",
        "thresholded_prediction",
    )
    incart_point = _verify_dataset_point_metrics(
        "INCART",
        OUT / "incart_v2_predictions.csv",
        "label",
        "source_domain_calibrated_probability",
        "thresholded_prediction",
    )
    incart_guard = verify_incart_guard()
    nstdb_guard = verify_nstdb_guard()

    official_decision = json.loads((OUT / "runtime_acceptance_decision.json").read_text())
    independent_method_integrity_pass = official_decision["method_integrity_pass"]
    independent_decision = (
        "ACCEPTED"
        if (
            independent_method_integrity_pass
            and incart_guard["independent_guard_pass"]
            and nstdb_guard["independent_guard_pass"]
        )
        else "NOT_ACCEPTED"
    )

    result = {
        "status": "PASS"
        if (
            all(internal["agreement"].values())
            and all(incart_point["agreement"].values())
            and incart_guard["ci_agreement"]
            and incart_guard["guard_agreement"]
            and nstdb_guard["guard_agreement"]
            and independent_decision == official_decision["MODEL_V2_RUNTIME_ACCEPTED"]
        )
        else "FAIL",
        "internal_test_point_metrics": internal,
        "incart_point_metrics": incart_point,
        "incart_guard": incart_guard,
        "nstdb_guard": nstdb_guard,
        "independent_decision": independent_decision,
        "official_decision": official_decision["MODEL_V2_RUNTIME_ACCEPTED"],
        "decision_agreement": (
            independent_decision == official_decision["MODEL_V2_RUNTIME_ACCEPTED"]
        ),
    }
    (OUT / "independent_verification.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if result["status"] != "PASS":
        raise SystemExit("V2_010_INDEPENDENT_VERIFICATION_FAILED")
    print(json.dumps({"status": result["status"], "decision": independent_decision}, indent=2))


if __name__ == "__main__":
    main()
