#!/usr/bin/env python3
"""V2-014 DATA-FREE reconstruction of the V2-FL-001/002/003 development statistics from the
COMMITTED round logs, committed VALIDATION prediction tables and committed result files ONLY.
No waveform, window cache, raw dataset or model inference is touched (the historical
verify_v2_fl_00x_replay scripts re-infer on real windows and are therefore NOT used here).

Usage: python -m scripts.v2_014_fl_dev_reconstruct <output.json>
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from federated.fedavg_runner import choose_best_round
from federated.model_v2_fedprox import WORST_ID, select_mu
from models.baselines import descriptive_metrics
from nhm.hashing import hash_file
from scripts.select_v2_fedprox_mu import load_rows

ROOT = Path(__file__).resolve().parents[1]
V1 = ROOT / "reports/model_v2/v2_fl_001"
V2 = ROOT / "reports/model_v2/v2_fl_002"
V3 = ROOT / "reports/model_v2/v2_fl_003"
FL_INIT_SHA = "6a2923ca87793fb78571b4cffad4026f8b4ce99d9dfcb3abe885e259c68a572f"
POINT = ("AUPRC", "AUROC", "pooled_F1", "precision", "sensitivity", "specificity",
         "patient_macro_F1", "accuracy")
TOL = 1e-9
TRAIN_POS_WEIGHT = 1.7157717177396683


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def reconstruct(name: str, result_path: Path, log_path: Path, pred_path: Path) -> dict[str, Any]:
    result = json.loads(result_path.read_text())
    rounds = _csv(log_path)
    stored = _csv(pred_path)
    labels = np.array([int(r["label"]) for r in stored])
    probs = np.array([float(r["raw_sigmoid_probability"]) for r in stored])
    logits = np.array([float(r["raw_logit"]) for r in stored], dtype=np.float64)
    groups = np.array([r["participant_group_id"] for r in stored])
    metrics = descriptive_metrics(labels, probs, groups, threshold=0.5)
    best = result["best_validation"]
    deltas = {k: abs(float(metrics[k]) - float(best[k])) for k in POINT}
    pos_weight = TRAIN_POS_WEIGHT  # global TRAIN negatives/positives used by every FL run
    sig = 1.0 / (1.0 + np.exp(-logits))
    bce = float(np.mean(-(pos_weight * labels * np.log(sig) + (1 - labels) * np.log(1 - sig))))
    best_round = choose_best_round(rounds)
    log_row = next(r for r in rounds if int(r["round"]) == best_round)
    r50 = next(r for r in rounds if int(r["round"]) == 50)
    checks = {
        "best_round_recomputed_equals_recorded": best_round == result["best_round"],
        "prediction_rows_are_best_round": {int(r["round"]) for r in stored} == {best_round},
        "point_metrics_reconstruct": max(deltas.values()) <= TOL,
        "bce_reconstructs_within_1e-5": abs(bce - float(best["BCE"])) <= 1e-5,
        "round_log_best_AUPRC_equals_result": abs(
            float(log_row["validation_AUPRC"]) - float(best["AUPRC"])) <= TOL,
        "round_50_AUPRC_equals_result": abs(
            float(r50["validation_AUPRC"]) - float(result["round_50_validation_AUPRC"])) <= TOL,
        "round_0_is_FL_INIT_V2": rounds[0]["global_state_sha256"] == FL_INIT_SHA
        == result["round_0_state_sha256"],
        "best_checkpoint_sha_matches": hash_file(ROOT / result["best_checkpoint"]) == result[
            "best_checkpoint_sha256"],
        "round_50_checkpoint_sha_matches": hash_file(ROOT / result["round_50_checkpoint"])
        == result["round_50_checkpoint_sha256"],
        "prediction_windows_equal_recorded": len(stored) == int(best["windows"])}
    return {"run": name, "best_round": best_round, "max_point_metric_delta": max(deltas.values()),
            "bce_delta": abs(bce - float(best["BCE"])), "best_validation_AUPRC": metrics["AUPRC"],
            "checks": checks, "status": "PASS" if all(checks.values()) else "FAIL"}


def main() -> None:
    out = Path(sys.argv[1])
    runs: list[dict[str, Any]] = []
    runs.append(reconstruct("V2-FL-001/iid", V1 / "fl_iid_model_v2_result.json",
                            V1 / "round_log.csv", V1 / "validation_predictions_best_round.csv"))
    for cond in ("label", "quantity", "feature", "combined"):
        runs.append(reconstruct(f"V2-FL-002/{cond}", V2 / f"{cond}_result.json",
                                V2 / f"{cond}_round_log.csv",
                                V2 / f"{cond}_validation_predictions.csv"))
    for mu in ("0p001", "0p01", "0p1"):
        d = V3 / "candidates" / f"mu_{mu}"
        runs.append(reconstruct(f"V2-FL-003/candidate/mu_{mu}", d / "result.json",
                                d / "round_log.csv", d / "validation_predictions.csv"))
    for cond in ("iid", "quantity", "feature", "combined"):
        d = V3 / "transfer" / cond
        runs.append(reconstruct(f"V2-FL-003/transfer/{cond}", d / "result.json",
                                d / "round_log.csv", d / "validation_predictions.csv"))
    config = yaml.safe_load((ROOT / "configs/model_v2/fedprox_v2.yaml").read_text())
    lock = json.loads((ROOT / "artifacts/FEDPROX_MU_V2.lock.json").read_text())
    baseline = config["label_fedavg_baseline"][WORST_ID]
    selected = [select_mu(load_rows(), baseline)["selected_mu"] for _ in range(2)]
    selection = {"recomputed_twice": selected, "lock_selected_mu": lock["selected_mu"],
                 "status": "PASS" if all(s == lock["selected_mu"] == 0.1 for s in selected)
                 else "FAIL"}
    comparison = json.loads((V3 / "fedavg_vs_fedprox_comparison.json").read_text())
    fedavg = {"iid": V1 / "fl_iid_model_v2_result.json"}
    fedavg |= {c: V2 / f"{c}_result.json" for c in ("quantity", "feature", "combined")}
    matched, matched_ok = {}, True
    for cond, path in fedavg.items():
        avg = json.loads(path.read_text())
        prox = json.loads((V3 / "transfer" / cond / "result.json").read_text())
        stored = comparison["conditions"][cond]
        delta = {
            "delta_best_AUPRC": prox["best_validation"]["AUPRC"] - avg["best_validation"]["AUPRC"],
            "delta_AUROC": prox["best_validation"]["AUROC"] - avg["best_validation"]["AUROC"],
            "delta_patient_macro_F1": prox["best_validation"]["patient_macro_F1"]
            - avg["best_validation"]["patient_macro_F1"],
            "best_round_shift": prox["best_round"] - avg["best_round"]}
        ok = (abs(delta["delta_best_AUPRC"] - stored["delta_best_AUPRC_FedProx_minus_FedAvg"])
              <= TOL and abs(delta["delta_AUROC"] - stored["delta_AUROC"]) <= TOL
              and abs(delta["delta_patient_macro_F1"] - stored["delta_patient_macro_F1"]) <= TOL
              and delta["best_round_shift"] == stored["best_round_shift"])
        matched[cond] = {**delta, "matches_frozen_comparison": ok}
        matched_ok &= ok
    report = {
        "scope": "committed round logs + committed VALIDATION prediction tables + result files",
        "real_waveforms_opened": False, "model_inference_run": False, "training_run": False,
        "runs": runs, "fedprox_mu_selection": selection, "matched_comparisons": matched,
        "status": "PASS" if (all(r["status"] == "PASS" for r in runs)
                             and selection["status"] == "PASS" and matched_ok) else "FAIL"}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "runs": len(runs)}))
    if report["status"] != "PASS":
        sys.exit(1)


if __name__ == "__main__":
    main()
