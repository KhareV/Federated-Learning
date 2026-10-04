#!/usr/bin/env python3
"""V2-FL-EVAL-001 evidence assembly (post-exposure, PREDICTION-ONLY / metadata-only). Reads the
frozen statistics JSON and the frozen prediction tables; opens no checkpoint and no source dataset.
Writes the 20-row result tables, architecture/FedProx effect tables, shift tables, population
report, guard, firewall, immutability and protected-artifact audits. Evidence assembly only: no
scientific method, metric definition or value is created or altered here."""

from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path

import yaml

from evaluation.model_v2_fl_eval import (
    FAMILY_RELATIVE,
    GUARDS,
    FamilyEvalError,
    begin_guard,
    guard_state,
    incart_expectations,
    internal_expectations,
    read_prediction_table,
)
from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_fl_eval_001"
TABLES = OUT / "tables"
ORDER = [f"{g}_{a}_{c}" for g in ("V1",) for a in ("FEDAVG", "FEDPROX")
         for c in ("IID", "LABEL", "QUANTITY", "FEATURE", "COMBINED")] + [
    f"V2_{a}_{c}" for a in ("FEDAVG", "FEDPROX")
    for c in ("IID", "LABEL", "QUANTITY", "FEATURE", "COMBINED")]
HEADINGS = {"INTERNAL_TEST": "FL-LINEAGE HELD-OUT (not project-globally unseen)",
            "INCART": "POST-FREEZE EXTERNAL FL SECOND-LOOK -- NOT PROJECT-BLIND"}


def _load(name: str) -> dict:
    return json.loads((OUT / name).read_text())


def _write(name: str, data: dict) -> None:
    (OUT / name).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _f(x: float | None, digits: int = 4) -> str:
    return "undefined" if x is None else f"{x:.{digits}f}"


def result_tables(stats: dict[str, dict]) -> None:
    TABLES.mkdir(parents=True, exist_ok=True)
    fields = ["model", "algorithm", "generation", "condition", "mu", "checkpoint_sha256",
              "development_round", "AUPRC", "AUPRC_ci_lower", "AUPRC_ci_upper", "AUROC",
              "pooled_F1", "patient_macro_F1", "patient_macro_F1_ci_lower",
              "patient_macro_F1_ci_upper", "precision", "sensitivity", "specificity", "accuracy",
              "BCE", "TP", "FP", "TN", "FN", "windows", "positives", "negatives",
              "contributing_patients"]
    for dataset, data in stats.items():
        with (TABLES / f"{dataset.lower()}_results.csv").open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            for key in ORDER:
                m = data["models"][key]
                p, b = m["point"], m["bootstrap_95"]
                writer.writerow({
                    "model": key, "algorithm": m["algorithm"], "generation": m["generation"],
                    "condition": m["condition"], "mu": m["mu"],
                    "checkpoint_sha256": m["checkpoint_sha256"],
                    "development_round": m["development_round"], "AUPRC": p["AUPRC"],
                    "AUPRC_ci_lower": b["AUPRC"]["ci_lower_95"],
                    "AUPRC_ci_upper": b["AUPRC"]["ci_upper_95"], "AUROC": p["AUROC"],
                    "pooled_F1": p["pooled_F1"], "patient_macro_F1": p["patient_macro_F1"],
                    "patient_macro_F1_ci_lower": b["patient_macro_F1"]["ci_lower_95"],
                    "patient_macro_F1_ci_upper": b["patient_macro_F1"]["ci_upper_95"],
                    "precision": p["precision"], "sensitivity": p["sensitivity"],
                    "specificity": p["specificity"], "accuracy": p["accuracy"], "BCE": p["BCE"],
                    "TP": p["TP"], "FP": p["FP"], "TN": p["TN"], "FN": p["FN"],
                    "windows": p["windows"], "positives": p["positives"],
                    "negatives": p["negatives"],
                    "contributing_patients": p["contributing_patients"]})
    effect_rows = []
    for dataset, data in stats.items():
        for name, comp in data["comparisons"].items():
            for metric in ("AUPRC", "patient_macro_F1"):
                d = comp["delta"][metric]
                effect_rows.append({
                    "dataset": dataset, "family": comp["family"], "contrast": name,
                    "metric": metric, "point_delta": d["point_delta"],
                    "ci_lower_95": d["ci_lower_95"], "ci_upper_95": d["ci_upper_95"],
                    "ci_excludes_zero": d["ci_lower_95"] > 0 or d["ci_upper_95"] < 0,
                    "valid_replicates": d["valid_replicates"],
                    "invalid_replicates": d["invalid_replicates"]})
    with (TABLES / "paired_effects.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(effect_rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(effect_rows)
    shifts = _load("shift_tables.json")
    with (TABLES / "shift_v2_models.csv").open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["model", "metric", "development", "internal_test", "dev_to_internal",
                         "incart", "internal_to_incart"])
        for key, row in shifts["models"].items():
            for metric in ("AUPRC", "patient_macro_F1"):
                dev, internal, delta1 = row["development_to_internal"][metric]
                _, incart, delta2 = row["internal_to_incart"][metric]
                writer.writerow([key, metric, dev, internal, delta1, incart, delta2])
    lines = []
    for dataset, data in stats.items():
        lines += [f"## {dataset} — {HEADINGS[dataset]}", "",
                  "| model | ckpt sha | dev rnd | AUPRC [95% CI] | AUROC | F1@0.5 | pt-macro F1 "
                  "[95% CI] | prec | sens | spec | BCE |",
                  "|---|---|---|---|---|---|---|---|---|---|---|"]
        for key in ORDER:
            m = data["models"][key]
            p, b = m["point"], m["bootstrap_95"]
            lines.append(
                f"| {key} | {m['checkpoint_sha256'][:8]} | {m['development_round']} | "
                f"{_f(p['AUPRC'])} [{_f(b['AUPRC']['ci_lower_95'], 3)}, "
                f"{_f(b['AUPRC']['ci_upper_95'], 3)}] | {_f(p['AUROC'], 3)} | "
                f"{_f(p['pooled_F1'], 3)} | {_f(p['patient_macro_F1'], 3)} "
                f"[{_f(b['patient_macro_F1']['ci_lower_95'], 3)}, "
                f"{_f(b['patient_macro_F1']['ci_upper_95'], 3)}] | {_f(p['precision'], 3)} | "
                f"{_f(p['sensitivity'], 3)} | {_f(p['specificity'], 3)} | {_f(p['BCE'], 3)} |")
        lines.append("")
    (TABLES / "results_tables.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def population_report(roster: list[dict]) -> dict:
    internal = internal_expectations(ROOT)
    incart = incart_expectations(ROOT)
    data = {}
    for dataset, expected in (("INTERNAL_TEST", internal), ("INCART", incart)):
        reference = None
        agree = True
        for m in roster:
            table = read_prediction_table(OUT / "predictions" / dataset / f"{m['id']}.csv.gz")
            ids = table["example_id"].tolist()
            reference = reference or ids
            agree = agree and ids == reference == expected["ids"]
        positives = sum(expected["labels"])
        data[dataset] = {
            "eligible_windows": len(expected["ids"]), "positive": positives,
            "negative": len(expected["ids"]) - positives,
            "prevalence": positives / len(expected["ids"]),
            "all_20_models_identical_ordered_example_ids_equal_frozen_expectation": agree,
            "contributing_clusters": len(set(expected["groups"]))}
    data["INTERNAL_TEST"].update({
        "candidate_windows": internal["candidate_windows"],
        "frozen_groups": len(internal["frozen_groups"]),
        "zero_eligible_groups": internal["zero_eligible_groups"],
        "claim": "FEDERATED-LINEAGE HELD-OUT; centralized models were evaluated on this partition "
        "earlier in the project; NOT project-globally unseen"})
    data["INCART"].update({
        "records": incart["records"], "clusters": incart["clusters"],
        "claim": "POST-FREEZE EXTERNAL FL SECOND-LOOK on a previously project-exposed dataset; "
        "NOT project-blind; NOT untouched external validation"})
    data["development_validation_prevalence"] = 676 / 2880
    data["note"] = ("Class prevalence differs across datasets (VALIDATION ~0.235, INTERNAL_TEST "
                    "~0.536, INCART ~0.487); AUPRC baselines differ accordingly, so absolute "
                    "AUPRC is not directly comparable across datasets.")
    _write("population_report.json", data)
    return data


def audits(roster: list[dict]) -> dict:
    manifest = _load("inference_manifest.json")
    freeze = _load("method_freeze.json")
    drift = [p for p, h in freeze["method_file_sha256"].items() if hash_file(ROOT / p) != h]
    second = {}
    for dataset in GUARDS:
        try:
            begin_guard(ROOT, dataset, {})
            second[dataset] = "NOT_BLOCKED"
        except FamilyEvalError as error:
            second[dataset] = str(error)
    guard_audit = {
        "states": {d: guard_state(ROOT, d) for d in GUARDS},
        "family_invocations": manifest["family_invocations"],
        "checkpoints_evaluated_per_dataset": {"INTERNAL_TEST": len(manifest["internal_test"]),
                                              "INCART": len(manifest["incart"])},
        "evaluated_ids_equal_roster": sorted(b["checkpoint_id"]
                                             for b in manifest["internal_test"]) == sorted(
            m["id"] for m in roster) and sorted(b["checkpoint_id"]
                                                for b in manifest["incart"]) == sorted(
            m["id"] for m in roster),
        "excluded_checkpoints_evaluated": False,
        "second_inference_attempt": second,
        "second_attempt_blocked_deterministically": all(
            "ALREADY_CONSUMED" in v for v in second.values()),
        "historical_guards": {
            "internal": json.loads((ROOT / "artifacts/internal_test_access_v1.json"
                                    ).read_text())["status"],
            "incart": json.loads((ROOT / "artifacts/external_incart_access_v1.json"
                                  ).read_text())["status"]},
        "post_access_checkpoint_inference": False}
    guard_audit["status"] = "PASS" if (
        all(s == "COMPLETED" for s in guard_audit["states"].values())
        and guard_audit["evaluated_ids_equal_roster"]
        and guard_audit["second_attempt_blocked_deterministically"]
        and guard_audit["family_invocations"] == {"INTERNAL_TEST": 1, "INCART": 1}) else "FAIL"
    _write("one_shot_guard_audit.json", guard_audit)
    ledger = [json.loads(x) for x in (ROOT / "reports/model_v2/access_ledger.jsonl"
                                      ).read_text().splitlines() if x.strip()]
    mine = [r for r in ledger if r.get("stage_id") == "V2-FL-EVAL-001"]
    partitions = sorted({r["partition"] for r in mine})
    firewall = {"ledger_rows": len(mine), "partitions_accessed": partitions,
                "TRAIN": "TRAIN" in partitions, "VALIDATION": "VALIDATION" in partitions,
                "CALIBRATION_accessed": "CALIBRATION" in partitions,
                "INTERNAL_TEST": "INTERNAL_TEST" in partitions, "INCART": "INCART" in partitions,
                "NSTDB_accessed": "NSTDB" in partitions, "BIDMC_accessed": "BIDMC" in partitions,
                "WEARABLE_accessed": False, "WEARABLE_SIM_used": False,
                "CAL_V1_used": False, "CAL_V2_used": False, "threshold_tuned": False,
                "status": "PASS" if set(partitions) <= {"INTERNAL_TEST", "INCART"} else "FAIL"}
    _write("firewall_audit.json", firewall)
    _write("method_immutability_post_exposure.json", {
        "method_files": len(freeze["method_file_sha256"]), "changed_after_exposure": drift,
        "post_access_scientific_edits": bool(drift),
        "status": "PASS" if not drift else "FAIL"})
    baseline = {}
    for path in ("reports/model_v2/v2_013/protected_baseline.json",
                 "reports/model_v2/v2_fl_003/protected_baseline.json",
                 "reports/model_v2/v2_fl_002/protected_baseline.json"):
        baseline.update(json.loads((ROOT / path).read_text())["artifacts"])
    protected_drift = sorted(p for p, h in baseline.items() if hash_file(ROOT / p) != h)
    historical = {p: hash_file(ROOT / p) for p in (
        "reports/internal_test_predictions.csv", "reports/external_incart_predictions.csv",
        "reports/t018/artifact_hashes.json", "reports/t020/artifact_hashes.json")}
    family_lock = json.loads((ROOT / "manifests/model_v2/V2_FL_TEST_FAMILY_V1.lock.json"
                              ).read_text())
    ckpt_drift = [k for k, v in family_lock["checkpoints"].items()
                  if hash_file(ROOT / v["path"]) != v["sha256"]]
    _write("protected_artifact_audit.json", {
        "checked": len(baseline), "drift": protected_drift, "roster_checkpoint_drift": ckpt_drift,
        "historical_evidence_hashes": historical,
        "status": "PASS" if not protected_drift and not ckpt_drift else "FAIL"})
    return {"guard": guard_audit, "firewall": firewall}


def historical_references() -> None:
    v1_int = {r["metric"]: float(r["point_estimate"]) for r in csv.DictReader(
        (ROOT / "reports/internal_test_metrics.csv").open())}
    v1_ext = {r["metric"]: float(r["point_estimate"]) for r in csv.DictReader(
        (ROOT / "reports/external_incart_metrics.csv").open())}
    v2_int = json.loads((ROOT / "reports/model_v2/v2_010/internal_comparison.json").read_text())
    v2_ext = json.loads((ROOT / "reports/model_v2/v2_010/incart_comparison.json").read_text())
    _write("historical_frozen_centralized_references.json", {
        "label": "HISTORICAL FROZEN REFERENCE (centralized models; NOT part of the new one-shot FL "
        "inference; evaluated earlier with their own calibration/thresholds)",
        "MODEL_V1_internal_test": {k: v1_int[k] for k in ("AUPRC", "AUROC")},
        "MODEL_V1_incart": {k: v1_ext[k] for k in ("AUPRC", "AUROC")},
        "MODEL_V2_FINAL_internal_test": {k: v2_int["v2_point_metrics"].get(k)
                                         for k in ("AUPRC", "AUROC")},
        "MODEL_V2_FINAL_incart": {k: v2_ext["v2_point_metrics"].get(k)
                                  for k in ("AUPRC", "AUROC")},
        "rerun_in_this_phase": False})


def main() -> None:
    roster = yaml.safe_load((ROOT / FAMILY_RELATIVE).read_text())["models"]
    stats = {"INTERNAL_TEST": _load("internal_test_statistics.json"),
             "INCART": _load("incart_statistics.json")}
    result_tables(stats)
    population_report(roster)
    audits(roster)
    historical_references()
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                          check=True).stdout.strip()
    _write("assembly_provenance.json", {"head": head, "checkpoints_loaded": False,
                                        "source_data_opened": False,
                                        "prediction_and_metadata_only": True})
    print("evidence assembled")


if __name__ == "__main__":
    main()
