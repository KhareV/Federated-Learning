#!/usr/bin/env python3
"""V2-011 Section 4: first-principles reconstruction of the V2-010 paired statistics.

Uses ONLY frozen V1/V2 prediction tables and the frozen T018/T020 bootstrap draw matrices.
Reconstructs BOTH the V1 and the V2 bootstrap metric distributions from prediction rows
(historical replicate-metric CSVs are read only AFTER the reconstruction, for comparison).
Does not import evaluation.metrics, evaluation.bootstrap or scripts._v2_010_stats. No
waveform access and no model inference.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_011"
V2_010 = ROOT / "reports/model_v2/v2_010"
METRICS = ("AUPRC", "AUROC", "pooled_F1", "precision", "sensitivity", "specificity",
           "patient_macro_F1")
SNRS = (24, 18, 12, 6, 0, -6)
TOL = 1e-9
FLOAT_TOL = 1e-12


def read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def f1(tp: int, fp: int, fn: int) -> float:
    d = 2 * tp + fp + fn
    return 2 * tp / d if d else 0.0


class Table:
    """Per-patient arrays from one prediction table."""

    def __init__(self, rows: list[dict[str, str]], prob_col: str):
        self.patients = sorted({r["participant_group_id"] for r in rows})
        by: dict[str, list[dict[str, str]]] = {p: [] for p in self.patients}
        for r in rows:
            by[r["participant_group_id"]].append(r)
        self.y, self.p, self.pred, self.f1 = {}, {}, {}, {}
        for pat in self.patients:
            rr = sorted(by[pat], key=lambda r: r["example_id"])
            y = np.array([int(r["label"]) for r in rr])
            pr = np.array([float(r[prob_col]) for r in rr])
            pd = np.array([int(r["thresholded_prediction"]) for r in rr])
            self.y[pat], self.p[pat], self.pred[pat] = y, pr, pd
            tp = int(np.sum((y == 1) & (pd == 1)))
            fp = int(np.sum((y == 0) & (pd == 1)))
            fn = int(np.sum((y == 1) & (pd == 0)))
            self.f1[pat] = f1(tp, fp, fn)

    def metrics(self, slots: list[str]) -> dict[str, float | None]:
        y = np.concatenate([self.y[s] for s in slots])
        p = np.concatenate([self.p[s] for s in slots])
        pd = np.concatenate([self.pred[s] for s in slots])
        both = len(np.unique(y)) == 2
        tp = int(np.sum((y == 1) & (pd == 1)))
        fp = int(np.sum((y == 0) & (pd == 1)))
        tn = int(np.sum((y == 0) & (pd == 0)))
        fn = int(np.sum((y == 1) & (pd == 0)))
        return {
            "AUPRC": float(average_precision_score(y, p)) if both else None,
            "AUROC": float(roc_auc_score(y, p)) if both else None,
            "pooled_F1": f1(tp, fp, fn),
            "precision": tp / (tp + fp) if tp + fp else 0.0,
            "sensitivity": tp / (tp + fn) if tp + fn else None,
            "specificity": tn / (tn + fp) if tn + fp else None,
            "patient_macro_F1": float(np.mean([self.f1[s] for s in slots])),
        }


def reconstruct(v1: Table, v2: Table, draws: np.ndarray, frozen_patients: list[str]) -> dict:
    assert v1.patients == v2.patients == frozen_patients
    point1, point2 = v1.metrics(v1.patients), v2.metrics(v2.patients)
    dist1 = {m: np.full(len(draws), np.nan) for m in METRICS}
    dist2 = {m: np.full(len(draws), np.nan) for m in METRICS}
    unique_counts = []
    for i, draw in enumerate(draws):
        slots = [frozen_patients[int(k)] for k in draw]
        unique_counts.append(len(set(slots)))
        m1, m2 = v1.metrics(slots), v2.metrics(slots)
        for m in METRICS:
            if m1[m] is not None:
                dist1[m][i] = m1[m]
            if m2[m] is not None:
                dist2[m][i] = m2[m]
    return {"point1": point1, "point2": point2, "dist1": dist1, "dist2": dist2,
            "slots": int(draws.shape[1]), "min_unique": int(min(unique_counts))}


def delta_summary(point1, point2, dist1, dist2) -> dict:
    out = {}
    for m in METRICS:
        delta = dist2[m] - dist1[m]
        finite = delta[np.isfinite(delta)]
        out[m] = {
            "v1_point": point1[m], "v2_point": point2[m],
            "point_delta": None if point1[m] is None or point2[m] is None
            else point2[m] - point1[m],
            "ci_lower_95": float(np.quantile(finite, 0.025, method="linear")),
            "ci_upper_95": float(np.quantile(finite, 0.975, method="linear")),
            "valid_replicates": int(finite.size),
        }
    return out


def compare_historical(name: str, rec: dict, v1_csv: Path, v2_csv: Path, summary: dict) -> dict:
    h1, h2 = read(v1_csv), read(v2_csv)
    diffs1, diffs2 = {}, {}
    for m in METRICS:
        a1 = np.array([float(r[m]) if r[m] not in ("", "None") else np.nan for r in h1])
        a2 = np.array([float(r[m]) if r[m] not in ("", "None") else np.nan for r in h2])
        d1 = np.nanmax(np.abs(a1 - rec["dist1"][m])) if np.isfinite(a1).any() else 0.0
        d2 = np.nanmax(np.abs(a2 - rec["dist2"][m])) if np.isfinite(a2).any() else 0.0
        diffs1[m], diffs2[m] = float(d1), float(d2)
    comp_name = {"INTERNAL_TEST": "internal_comparison.json",
                 "INCART": "incart_comparison.json"}[name]
    official = json.loads((V2_010 / comp_name).read_text())["paired_bootstrap_deltas"]
    ci_diff = {m: max(abs(summary[m]["ci_lower_95"] - official[m]["ci_lower_95"]),
                       abs(summary[m]["ci_upper_95"] - official[m]["ci_upper_95"]))
               for m in METRICS}
    return {
        "max_abs_diff_v1_replicates_vs_historical_csv": diffs1,
        "max_abs_diff_v2_replicates_vs_v2_010_csv": diffs2,
        "max_abs_diff_delta_ci_vs_v2_010": ci_diff,
        "all_within_tolerance": all(v <= TOL for v in
                                    [*diffs1.values(), *diffs2.values(), *ci_diff.values()]),
    }


def dataset(name: str, v1_path: str, v1_prob: str, v2_path: str, draws_path: str,
            hist_v1: str, hist_v2: str) -> dict:
    draws_npz = np.load(ROOT / draws_path, allow_pickle=False)
    draws = draws_npz["draws_int64"]
    frozen_patients = [p.decode() for p in draws_npz["patient_ids_utf8"]]
    v1 = Table(read(ROOT / v1_path), v1_prob)
    v2 = Table(read(V2_010 / v2_path), "source_domain_calibrated_probability")
    rec = reconstruct(v1, v2, draws, frozen_patients)
    summary = delta_summary(rec["point1"], rec["point2"], rec["dist1"], rec["dist2"])
    hist = compare_historical(name, rec, ROOT / hist_v1, V2_010 / hist_v2, summary)
    return {
        "patients": len(frozen_patients), "slots_per_replicate": rec["slots"],
        "replicates": int(draws.shape[0]), "multiplicity_preserved": True,
        "min_unique_patients_in_a_replicate": rec["min_unique"],
        "deltas": summary, "comparison_to_historical_tables": hist,
    }


def nstdb() -> dict:
    def ap_by_snr(path: Path, col: str) -> dict[int, float]:
        rows = read(path)
        out = {}
        for snr in SNRS:
            sel = [r for r in rows if int(r["snr_db"]) == snr]
            out[snr] = float(average_precision_score(
                [int(r["label"]) for r in sel], [float(r[col]) for r in sel]))
        return out

    col = "transferred_source_domain_probability"
    v1 = ap_by_snr(ROOT / "reports/t019/nstdb_predictions.csv", col)
    v2 = ap_by_snr(V2_010 / "nstdb_v2_predictions.csv", col)
    delta = {snr: v2[snr] - v1[snr] for snr in SNRS}
    official = json.loads((V2_010 / "nstdb_comparison_summary.json").read_text())
    off = {int(k): v for k, v in official["delta_auprc_by_snr"].items()}
    return {
        "v1_auprc": {str(k): v for k, v in v1.items()},
        "v2_auprc": {str(k): v for k, v in v2.items()},
        "delta_auprc_v2_minus_v1": {str(k): v for k, v in delta.items()},
        "max_abs_diff_vs_v2_010": max(abs(delta[s] - off[s]) for s in SNRS),
        "all_six_nonnegative": all(delta[s] >= -FLOAT_TOL for s in SNRS),
    }


def main() -> None:
    internal = dataset(
        "INTERNAL_TEST", "reports/internal_test_predictions.csv",
        "source_domain_calibrated_probability", "internal_v2_predictions.csv",
        "reports/t018/bootstrap_draws.npz", "reports/t018/bootstrap_replicates.csv",
        "internal_bootstrap_replicates.csv")
    incart = dataset(
        "INCART", "reports/external_incart_predictions.csv",
        "source_domain_calibrated_probability", "incart_v2_predictions.csv",
        "reports/t020/bootstrap_draws.npz", "reports/t020/bootstrap_replicates.csv",
        "incart_bootstrap_replicates.csv")
    ns = nstdb()
    lower = incart["deltas"]["AUROC"]["ci_lower_95"]
    incart_guard = lower >= -FLOAT_TOL
    guards_completed = all(
        json.loads((V2_010 / f).read_text())["state"] == "COMPLETED"
        for f in ("internal_test_second_look_guard.json", "incart_second_look_guard.json",
                  "nstdb_second_look_guard.json"))
    decision = "ACCEPTED" if (guards_completed and incart_guard and ns["all_six_nonnegative"]) \
        else "NOT_ACCEPTED"
    original = json.loads((V2_010 / "runtime_acceptance_decision.json").read_text())
    agree = (
        internal["comparison_to_historical_tables"]["all_within_tolerance"]
        and incart["comparison_to_historical_tables"]["all_within_tolerance"]
        and ns["max_abs_diff_vs_v2_010"] <= TOL
        and decision == original["MODEL_V2_RUNTIME_ACCEPTED"] == "ACCEPTED"
    )
    report = {
        "method": "FIRST_PRINCIPLES_BOTH_SIDES_FROM_FROZEN_PREDICTIONS_AND_DRAW_MATRICES",
        "waveform_access": False, "model_inference": False,
        "historical_replicate_csvs_used_as_numerical_source": False,
        "tolerance": TOL,
        "INTERNAL_TEST_descriptive": internal,
        "INCART": incart,
        "INCART_AUROC_delta_ci_lower_95": lower,
        "INCART_AUROC_RUNTIME_GUARD_PASS": bool(incart_guard),
        "NSTDB": ns,
        "NSTDB_NO_COLLAPSE_PASS": bool(ns["all_six_nonnegative"]),
        "reevaluated_runtime_decision": decision,
        "v2_010_recorded_runtime_decision": original["MODEL_V2_RUNTIME_ACCEPTED"],
        "agrees_with_v2_010": bool(agree),
        "status": "PASS" if agree else "FAIL",
    }
    (OUT / "v2_010_statistical_reverification.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "incart_lower_ci": lower,
                      "decision": decision}, indent=2))
    if not agree:
        raise SystemExit("V2_011_V2_010_REVERIFICATION_DISAGREES")


if __name__ == "__main__":
    main()
