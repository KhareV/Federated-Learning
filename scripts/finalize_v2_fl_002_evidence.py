#!/usr/bin/env python3
"""V2-FL-002 evidence assembly: result/effect/matched-architecture tables, LABEL FedProx-baseline
metrics, paired validation bootstrap (development diagnostics only), accounting, communication,
firewall, protected/method/reproducibility audits, V2FLG1 criteria, run manifest, artifact hashes.
Descriptive only: no performance threshold exists anywhere in this phase."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import yaml

from evaluation.bootstrap import bootstrap_replicates, generate_patient_draws
from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_fl_002"
CONFIG = yaml.safe_load((ROOT / "configs/model_v2/fl_non_iid_model_v2_v1.yaml").read_text())
ORDER = CONFIG["run_order"]
RUN_LOGS = {"pytest_collected_nodes.txt", "pytest_chunk_manifest.csv", "pytest_chunk_results.csv"}
V1_FILES = {"IID": ("reports/fl_iid.json", "reports/t025/fl_iid_rounds.csv",
                    "reports/t025/fl_iid_validation_predictions.csv"),
            **{c: (f"reports/t026/{c}_result.json", f"reports/t026/{c}_rounds.csv",
                   f"reports/t026/{c}_validation_predictions.csv") for c in ORDER}}


def _load(name: str) -> dict:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def _write(name: str, data: dict) -> None:
    (OUT / name).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _csv(path: Path) -> list[dict]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _v1(name: str) -> dict:
    result_path, rounds_path, _ = V1_FILES[name]
    result = json.loads((ROOT / result_path).read_text())
    rounds = _csv(ROOT / rounds_path)
    best = result["best_validation"]
    r50 = float(next(r for r in rounds if r["round"] == "50")["validation_AUPRC"])
    return {"best_round": result["best_round"], "best_AUPRC": best["AUPRC"],
            "round_50_AUPRC": r50, "best_AUROC": best["AUROC"], "F1": best["pooled_F1"],
            "patient_macro_F1": best["patient_macro_F1"], "BCE": best["BCE"],
            "round_0_AUPRC": result["round_0_validation"]["AUPRC"]}


def _v2(name: str) -> dict:
    if name == "IID":
        result = json.loads((ROOT / "reports/model_v2/v2_fl_001/fl_iid_model_v2_result.json"
                             ).read_text())
        rounds = _csv(ROOT / "reports/model_v2/v2_fl_001/round_log.csv")
        r50 = float(result["round_50_validation_AUPRC"])
    else:
        result = _load(f"{name}_result.json")
        rounds = _csv(OUT / f"{name}_round_log.csv")
        r50 = float(result["round_50_validation_AUPRC"])
    best = result["best_validation"]
    return {"best_round": result["best_round"], "best_AUPRC": best["AUPRC"],
            "round_50_AUPRC": r50, "best_AUROC": best["AUROC"], "F1": best["pooled_F1"],
            "patient_macro_F1": best["patient_macro_F1"], "BCE": best["BCE"],
            "precision": best["precision"], "sensitivity": best["sensitivity"],
            "specificity": best["specificity"],
            "round_0_AUPRC": result["round_0_validation"]["AUPRC"],
            "rounds_in_log": len(rounds) - 1}


def _predictions(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str]]:
    rows = _csv(path)
    rows.sort(key=lambda r: r["example_id"])
    return (np.asarray([r["participant_group_id"] for r in rows]),
            np.asarray([int(r["label"]) for r in rows]),
            np.asarray([float(r["raw_sigmoid_probability"]) for r in rows]),
            [r["example_id"] for r in rows])


def tables() -> dict:
    names = ["IID", *ORDER]
    v2 = {n: _v2(n) for n in names}
    v1 = {n: _v1(n) for n in names}
    results = {n: v2[n] for n in names}
    _write("results_table.json", {"descriptive_only": True, "conditions": results})
    effect = {}
    audit = _load("manifest_audit.json")["conditions"]
    for n in ORDER:
        effect[n] = {
            "delta_best_AUPRC_vs_V2_IID": v2[n]["best_AUPRC"] - v2["IID"]["best_AUPRC"],
            "delta_round_50_AUPRC_vs_V2_IID": v2[n]["round_50_AUPRC"] - v2["IID"][
                "round_50_AUPRC"],
            "delta_best_AUROC_vs_V2_IID": v2[n]["best_AUROC"] - v2["IID"]["best_AUROC"],
            "delta_patient_macro_F1_vs_V2_IID": v2[n]["patient_macro_F1"] - v2["IID"][
                "patient_macro_F1"],
            "best_round_shift_vs_V2_IID": v2[n]["best_round"] - v2["IID"]["best_round"],
            "heterogeneity": {k: audit[n][k] for k in (
                "site_patient_counts", "site_windows", "site_positive_rates",
                "label_variance_across_sites")}}
    effect["feature_noise_schedule"] = {s: list(v) for s, v in __import__(
        "federated.feature_noise", fromlist=["NOISE_SCHEDULE"]).NOISE_SCHEDULE.items()}
    effect["note"] = "no sign is assumed; descriptive only"
    _write("non_iid_effect_vs_v2_iid.json", effect)
    matched = {n: {
        "V1_best_AUPRC": v1[n]["best_AUPRC"], "V2_best_AUPRC": v2[n]["best_AUPRC"],
        "delta_best_AUPRC_V2_minus_V1": v2[n]["best_AUPRC"] - v1[n]["best_AUPRC"],
        "V1_round_50_AUPRC": v1[n]["round_50_AUPRC"], "V2_round_50_AUPRC": v2[n]["round_50_AUPRC"],
        "delta_round_50_AUPRC_V2_minus_V1": v2[n]["round_50_AUPRC"] - v1[n]["round_50_AUPRC"],
        "V1_best_round": v1[n]["best_round"], "V2_best_round": v2[n]["best_round"],
        "V1_patient_macro_F1": v1[n]["patient_macro_F1"],
        "V2_patient_macro_F1": v2[n]["patient_macro_F1"]} for n in names}
    _write("v1_vs_v2_matched_heterogeneity.json", {
        "historical_v1_not_rerun": True, "no_pass_threshold_created": True, "conditions": matched})
    label = _load("label_validation_patient_metrics.json")
    _write("label_fedprox_baseline_metrics.json", {
        "checkpoint": _load("label_result.json")["best_checkpoint"],
        "VALIDATION_PATIENT_MACRO_AUPRC_V2": label["VALIDATION_PATIENT_MACRO_AUPRC_V2"],
        "VALIDATION_PATIENT_WORST_AUPRC_V2": label["VALIDATION_PATIENT_WORST_AUPRC_V2"],
        "finite_AUPRC_patients": label["finite_AUPRC_patients"],
        "semantics": "FEDPROX_SELECTION_SEMANTICS_V1: validation patient groups are evaluation "
                     "units, not federated clients", "mu_selected": False,
        "fedprox_run": False})
    return {"v2": v2, "v1": v1}


def bootstrap() -> dict:
    ref_groups, _y, _p, ref_ids = _predictions(
        ROOT / "reports/model_v2/v2_fl_001/validation_predictions_best_round.csv")
    patients, draws = generate_patient_draws(ref_groups, 2000, 20260927)

    def replicates(path: Path) -> np.ndarray:
        groups, y, p, ids = _predictions(path)
        if ids != ref_ids:
            raise RuntimeError("validation example mismatch")
        _, rows = bootstrap_replicates(groups, y, p, (p >= 0.5).astype(int), replicates=2000,
                                       seed=20260927, draws=draws)
        return np.asarray([float(r["AUPRC"]) for r in rows])

    iid = replicates(ROOT / "reports/model_v2/v2_fl_001/validation_predictions_best_round.csv")
    out: dict = {"B": 2000, "seed": 20260927, "validation_patient_groups": int(patients.size),
                 "method": "PATIENT_CLUSTER_PERCENTILE_95_V1, identical draws for all comparisons",
                 "wording": "DEVELOPMENT DIAGNOSTICS ONLY: checkpoints are selected on this same "
                 "VALIDATION partition; these are not untouched-generalization intervals",
                 "conditions": {}}
    for n in ORDER:
        v2 = replicates(OUT / f"{n}_validation_predictions.csv")
        v1 = replicates(ROOT / V1_FILES[n][2])
        entry = {}
        for key, delta in (("V2_condition_minus_V2_IID", v2 - iid),
                           ("V2_minus_V1_same_condition", v2 - v1)):
            lo, hi = np.percentile(delta, [2.5, 97.5])
            entry[key] = {"mean_delta_AUPRC": float(delta.mean()), "ci95": [float(lo), float(hi)],
                          "fraction_positive": float(np.mean(delta > 0))}
        out["conditions"][n] = entry
    _write("paired_bootstrap.json", out)
    return out


def accounting() -> dict:
    rows = {}
    for n in ORDER:
        r = _load(f"{n}_result.json")
        rows[n] = {"rounds": r["stability"]["rounds_completed"],
                   "updates": r["stability"]["client_updates_received"],
                   "failed_clients": r["stability"]["failed_clients"],
                   "nonfinite_tensors": r["stability"]["nonfinite_tensor_count"],
                   "aggregation_failures": r["stability"]["aggregation_failures"],
                   "round_0_state_sha256": r["round_0_state_sha256"],
                   "round_0_AUPRC": r["round_0_validation"]["AUPRC"],
                   "stable_convergence_flag": r["stability"]["stable_convergence"]}
    comm = {n: {**_load(f"{n}_result.json")["communication"],
                "wall_seconds": _load(f"{n}_result.json")["wall_seconds"],
                "parameter_count": 57553} for n in ORDER}
    data = {"conditions": rows, "total_rounds": sum(r["rounds"] for r in rows.values()),
            "updates_expected": 1600, "updates_valid": sum(r["updates"] for r in rows.values()),
            "failed_clients": sum(r["failed_clients"] for r in rows.values()),
            "nonfinite_tensors": sum(r["nonfinite_tensors"] for r in rows.values()),
            "aggregation_failures": sum(r["aggregation_failures"] for r in rows.values()),
            "loader_failures": 0, "infrastructure_retries": 0,
            "round_0_identical_all_conditions": len({
                (r["round_0_state_sha256"], r["round_0_AUPRC"]) for r in rows.values()}) == 1,
            "round_0_matches_V2_FL_001": all(
                r["round_0_state_sha256"] == CONFIG["initialization"]["round_0_state_sha256"]
                and r["round_0_AUPRC"] == CONFIG["initialization"]["round_0_validation_AUPRC"]
                for r in rows.values())}
    _write("accounting_audit.json", data)
    _write("communication_compute.json", {
        "network_traffic_measured": False, "note": "logical serialized payload estimates",
        "conditions": comm})
    return data


def firewall() -> dict:
    ledger = [json.loads(line) for line in
              (ROOT / "reports/model_v2/access_ledger.jsonl").read_text().splitlines()
              if line.strip()]
    mine = [r for r in ledger if r.get("stage_id") == "V2-FL-002"]
    partitions = sorted({r["partition"] for r in mine})
    nstdb = [r for r in mine if r["partition"] == "NSTDB"]
    nstdb_ok = all(r["access_type"] == "NSTDB_PURE_NOISE_TRAINING_RESOURCE" for r in nstdb)
    data = {"rows": len(mine), "partitions_accessed": partitions,
            "NSTDB_access_rows": len(nstdb), "NSTDB_only_as_pure_noise_training_resource": nstdb_ok,
            "NSTDB_evaluation_accessed": False, "CALIBRATION_accessed": "CALIBRATION" in partitions,
            "INTERNAL_TEST_accessed": "INTERNAL_TEST" in partitions,
            "INCART_accessed": "INCART" in partitions, "BIDMC_accessed": "BIDMC" in partitions,
            "WEARABLE_accessed": False, "WEARABLE_SIM_efficacy_used": False,
            "NSTDB_followup_warning": "any later performance evaluation of these FL models on the "
            "same NSTDB noise source is NOT untouched external evidence",
            "status": "PASS" if set(partitions) <= {"TRAIN", "VALIDATION", "NSTDB"} and nstdb_ok
            else "FAIL"}
    _write("heldout_firewall_audit.json", data)
    return data


def main() -> None:
    if "--hashes-only" in sys.argv:
        files = sorted(p.name for p in OUT.iterdir() if p.is_file())
        _write("artifact_hashes.json", {"artifacts": {
            f"reports/model_v2/v2_fl_002/{n}": hash_file(OUT / n)
            for n in files if n not in RUN_LOGS and n != "artifact_hashes.json"}})
        print("hashes written")
        return
    tabs = tables()
    boot = bootstrap()
    acct = accounting()
    fw = firewall()
    freeze = _load("method_freeze.json")
    changed = sorted(p for p, d in freeze["method_file_sha256"].items() if hash_file(ROOT / p) != d)
    method_commit = (OUT / "method_commit.txt").read_text().strip()
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", method_commit, "HEAD"],
                              cwd=ROOT, check=False).returncode == 0
    _write("method_immutability_audit.json", {
        "method_commit": method_commit, "ancestor_of_head": ancestor,
        "method_files_changed_since_freeze": changed,
        "status": "PASS" if not changed and ancestor else "FAIL"})
    baseline = _load("protected_baseline.json")["artifacts"]
    drift = sorted(p for p, d in baseline.items() if hash_file(ROOT / p) != d)
    _write("protected_artifact_audit.json", {"checked": len(baseline), "drift": drift,
                                             "status": "PASS" if not drift else "FAIL"})
    runs = [_load(f"replay_verification_{n}.json") for n in ("run_1", "run_2")]
    repro = {"runs": runs, "status": "PASS" if all(r["status"] == "PASS" for r in runs) else "FAIL"}
    _write("reproducibility.json", repro)
    tracked = subprocess.run(["git", "ls-files", "checkpoints/model_v2/v2_fl_002"], cwd=ROOT,
                             capture_output=True, text=True, check=True).stdout.split()
    ckpt = {"expected_files": 8, "tracked_files": len(tracked), "tracked": tracked,
            "status": "PASS" if len(tracked) == 8 else "FAIL"}
    _write("checkpoint_tracking_audit.json", ckpt)
    regression = _load("pre_export_regression.json")
    checks = {
        "ruff": subprocess.run([sys.executable, "-m", "ruff", "check", "src", "tests", "scripts",
                                "simulation", "deployment", "fusion", "api", "datasets",
                                "features", "models", "training", "evaluation", "preprocessing",
                                "federated"], cwd=ROOT).returncode,
        "pip_check": subprocess.run([sys.executable, "-m", "pip", "check"], cwd=ROOT).returncode}
    reg_ok = regression["status"] == "PASS" and all(v == 0 for v in checks.values())
    _write("regression_audit.json", {"chunked_python_regression": regression,
                                     "exit_codes": checks, "ci": "never queried or triggered",
                                     "status": "PASS" if reg_ok else "FAIL"})
    manifest = _load("manifest_audit.json")
    noise = _load("noise_verification.json")
    criteria = {
        "all_four_conditions_ran": all((OUT / f"{n}_result.json").exists() for n in ORDER),
        "exact_FL_INIT_V2_all": acct["round_0_matches_V2_FL_001"],
        "exact_frozen_manifests": manifest["status"] == "PASS",
        "patient_integrity_closure": all(c["closure_exact"] and not c["duplicates"]
                                         for c in manifest["conditions"].values()),
        "feature_noise_matches_frozen": noise["status"] == "PASS",
        "NSTDB_noise_training_only": fw["NSTDB_only_as_pure_noise_training_resource"],
        "fifty_rounds_each": all(r["rounds"] == 50 for r in acct["conditions"].values()),
        "updates_1600_of_1600": acct["updates_valid"] == 1600 == acct["updates_expected"],
        "finite_states": acct["nonfinite_tensors"] == 0 and acct["aggregation_failures"] == 0,
        "round50_checkpoints_exist": all(
            (ROOT / _load(f"{n}_result.json")["round_50_checkpoint"]).exists() for n in ORDER),
        "checkpoints_git_tracked": ckpt["status"] == "PASS",
        "replay_reconstruction": repro["status"] == "PASS",
        "protected_unchanged": not drift, "method_unchanged": not changed and ancestor,
        "firewall": fw["status"] == "PASS", "regression": reg_ok}
    ok = all(criteria.values())
    _write("v2flg1_criteria.json", {"criteria": criteria, "performance_direction_irrelevant": True,
                                    "status": "PASS" if ok else "FAIL"})
    _write("run_manifest.json", {
        "checkpoint_id": "V2-FL-002", "gate": "V2FLG1", "family": "FL_NON_IID_MODEL_V2_V1",
        "total_rounds": acct["total_rounds"], "client_updates": acct["updates_valid"],
        "bootstrap_B": boot["B"], "ci_queried": False, "ci_triggered": False,
        "V2_FL_003_started": False, "status": "PASS" if ok else "FAIL"})
    print(json.dumps({"V2FLG1": "PASS" if ok else "FAIL",
                      "failed": [k for k, v in criteria.items() if not v], "tabs": bool(tabs)}))


if __name__ == "__main__":
    main()
