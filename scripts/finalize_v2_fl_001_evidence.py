#!/usr/bin/env python3
"""V2-FL-001 evidence assembly (after the single real run, fresh-process replays and the chunked
regression). Descriptive V1-vs-V2 comparison and paired patient-cluster bootstrap (existing
2000-draw framework, seed 20260927), method-immutability, protected/held-out audits, decision,
run manifest and (last) artifact hashes. Nothing here changes the method or any scientific value."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

from evaluation.bootstrap import bootstrap_replicates, generate_patient_draws
from models.ecg_cnn import build_model_v1
from models.model_v2_architectures import count_trainable_parameters
from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_fl_001"
RUN_LOGS = {"pytest_collected_nodes.txt", "pytest_chunk_manifest.csv", "pytest_chunk_results.csv"}
BOOTSTRAP_SEED = 20260927


def _load(name: str) -> dict:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def _write(name: str, data: dict) -> None:
    (OUT / name).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _csv(path: Path) -> list[dict]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _sh(*args: str) -> str:
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True, check=False
                          ).stdout.strip()


def method_immutability() -> dict:
    freeze = _load("method_freeze.json")
    changed = sorted(p for p, d in freeze["method_file_sha256"].items()
                     if hash_file(ROOT / p) != d)
    method_commit = (OUT / "method_commit.txt").read_text().strip()
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", method_commit, "HEAD"],
                              cwd=ROOT, check=False).returncode == 0
    data = {"method_commit": method_commit, "method_commit_is_ancestor_of_head": ancestor,
            "method_files_changed_since_freeze": changed,
            "status": "PASS" if not changed and ancestor else "FAIL"}
    _write("method_immutability_audit.json", data)
    return data


def protected_and_firewall() -> tuple[dict, dict]:
    baseline = _load("protected_baseline.json")["artifacts"]
    drift = sorted(p for p, d in baseline.items() if hash_file(ROOT / p) != d)
    protected = {"checked": len(baseline), "drift": drift,
                 "status": "PASS" if not drift else "FAIL"}
    _write("protected_artifact_audit.json", protected)
    ledger = [json.loads(line) for line in
              (ROOT / "reports/model_v2/access_ledger.jsonl").read_text().splitlines()
              if line.strip()]
    mine = [r for r in ledger if r.get("stage_id") == "V2-FL-001"]
    partitions = sorted({r["partition"] for r in mine})
    firewall = {"v2_fl_001_ledger_rows": len(mine), "partitions_accessed": partitions,
                "CALIBRATION_accessed": "CALIBRATION" in partitions,
                "INTERNAL_TEST_accessed": "INTERNAL_TEST" in partitions,
                "INCART_accessed": "INCART" in partitions, "NSTDB_accessed": "NSTDB" in partitions,
                "BIDMC_accessed": "BIDMC" in partitions, "WEARABLE_SIM_efficacy_used": False,
                "status": "PASS" if set(partitions) <= {"TRAIN", "VALIDATION"} else "FAIL"}
    _write("heldout_firewall_audit.json", firewall)
    return protected, firewall


def comparison() -> dict:
    v2 = _load("fl_iid_model_v2_result.json")
    v1 = json.loads((ROOT / "reports/fl_iid.json").read_text())
    v1_rounds = _csv(ROOT / "reports/t025/fl_iid_rounds.csv")
    v2_rounds = _csv(OUT / "round_log.csv")
    v1_pred = {r["example_id"]: r for r in _csv(ROOT / "reports/t025/fl_iid_validation_predictions.csv")}  # noqa: E501
    v2_pred = _csv(OUT / "validation_predictions_best_round.csv")
    ids = [r["example_id"] for r in v2_pred]
    if set(ids) != set(v1_pred):
        raise RuntimeError("V1/V2 validation example sets differ")
    groups = np.asarray([r["participant_group_id"] for r in v2_pred])
    labels = np.asarray([int(r["label"]) for r in v2_pred])
    p2 = np.asarray([float(r["raw_sigmoid_probability"]) for r in v2_pred])
    p1 = np.asarray([float(v1_pred[i]["raw_sigmoid_probability"]) for i in ids])
    patients, draws = generate_patient_draws(groups, 2000, BOOTSTRAP_SEED)
    _, rows2 = bootstrap_replicates(groups, labels, p2, (p2 >= 0.5).astype(int),
                                    replicates=2000, seed=BOOTSTRAP_SEED, draws=draws)
    _, rows1 = bootstrap_replicates(groups, labels, p1, (p1 >= 0.5).astype(int),
                                    replicates=2000, seed=BOOTSTRAP_SEED, draws=draws)
    delta = np.asarray([float(a["AUPRC"]) - float(b["AUPRC"]) for a, b in zip(rows2, rows1,
                                                                                 strict=True)])
    lo, hi = np.percentile(delta, [2.5, 97.5])
    boot = {"method": "PATIENT_CLUSTER_PERCENTILE_95_V1 (existing framework), paired on identical "
            "draws", "replicates": 2000, "seed": BOOTSTRAP_SEED, "validation_patient_groups":
            int(patients.size), "delta_definition": "V2_FL_pooled_AUPRC - V1_FL_pooled_AUPRC "
            "(each at its own selected best round)", "mean_delta": float(delta.mean()),
            "ci95": [float(lo), float(hi)], "fraction_replicates_delta_positive": float(
                np.mean(delta > 0)), "role": "DESCRIPTIVE_DEVELOPMENT_EVIDENCE_NOT_A_PROMOTION_CRITERION"}  # noqa: E501
    _write("paired_bootstrap_v2_vs_v1_fl.json", boot)
    b1, b2 = v1["best_validation"], v2["best_validation"]
    r1 = {r["round"]: r for r in v1_rounds}
    r2 = {r["round"]: r for r in v2_rounds}
    n1 = count_trainable_parameters(build_model_v1())
    table = {
        "descriptive_only": True, "v2_protocol_not_modified_by_this_comparison": True,
        "architecture": {"V1_FL_IID_V1": "MODEL_V1_ARCHITECTURE_V1", "V2": "MODEL_V2_TCN_MEAN"},
        "parameter_count": {"V1": n1, "V2": 57553},
        "round_0_AUPRC": {"V1": v1["round_0_validation"]["AUPRC"], "V2": v2["round_0_validation"]["AUPRC"]},  # noqa: E501
        "best_round": {"V1": v1["best_round"], "V2": v2["best_round"]},
        "best_AUPRC": {"V1": b1["AUPRC"], "V2": b2["AUPRC"], "delta_V2_minus_V1": b2["AUPRC"] - b1["AUPRC"]},  # noqa: E501
        "round_50_AUPRC": {"V1": float(r1["50"]["validation_AUPRC"]), "V2": float(r2["50"]["validation_AUPRC"])},  # noqa: E501
        "best_AUROC": {"V1": b1["AUROC"], "V2": b2["AUROC"]},
        "F1_at_0_5": {"V1": b1["pooled_F1"], "V2": b2["pooled_F1"]},
        "patient_macro_F1": {"V1": b1["patient_macro_F1"], "V2": b2["patient_macro_F1"]},
        "BCE": {"V1": b1["BCE"], "V2": b2["BCE"]},
        "sensitivity_at_0_5": {"V1": b1["sensitivity"], "V2": b2["sensitivity"]},
        "specificity_at_0_5": {"V1": b1["specificity"], "V2": b2["specificity"]},
        "update_bytes_per_round_each_direction": {
            "V1": v1["communication"]["client_to_server_bytes_per_round"],
            "V2": v2["communication"]["client_to_server_bytes_per_round"]},
        "runtime": {"V1": "not recorded consistently in T025 (not comparable)",
                    "V2_total_round_wall_seconds": v2["total_round_wall_seconds"]},
        "paired_bootstrap": boot}
    _write("v1_vs_v2_iid_comparison.json", table)
    return table


def decision(table: dict, v2: dict) -> dict:
    stable = bool(v2["stability"]["stable_convergence"])
    weak = (not stable) or table["best_AUPRC"]["delta_V2_minus_V1"] < 0
    finite = (v2["stability"]["nonfinite_tensor_count"] == 0
              and v2["stability"]["aggregation_failures"] == 0
              and v2["stability"]["client_updates_received"] == 400
              and v2["stability"]["rounds_completed"] == 50)
    outcome = "FAIL" if not finite else (
        "PASS_WITH_SCIENTIFIC_WARNING" if weak else "PASS")
    data = {"outcome": outcome, "stable_convergence_flag": stable,
            "v2_best_below_historical_v1_best": table["best_AUPRC"]["delta_V2_minus_V1"] < 0,
            "integrity_finite_complete": finite,
            "warning_rule": "predeclared: stable_convergence false OR best V2 AUPRC < historical "
            "V1 FL best AUPRC; no retuning in either case"}
    _write("decision.json", data)
    return data


def main() -> None:
    if "--hashes-only" in sys.argv:
        _hashes()
        return
    v2 = _load("fl_iid_model_v2_result.json")
    table = comparison()
    method = method_immutability()
    protected, firewall = protected_and_firewall()
    replays = [_load(f"replay_verification_{n}.json") for n in ("run_1", "run_2")]
    chunked = _load("pre_export_regression.json")
    checks = {
        "ruff": subprocess.run([sys.executable, "-m", "ruff", "check", "src", "tests", "scripts",
                                "simulation", "deployment", "fusion", "api", "datasets",
                                "features", "models", "training", "evaluation", "preprocessing",
                                "federated"], cwd=ROOT).returncode,
        "pip_check": subprocess.run([sys.executable, "-m", "pip", "check"], cwd=ROOT).returncode}
    reg_ok = chunked["status"] == "PASS" and all(v == 0 for v in checks.values())
    _write("regression_audit.json", {"chunked_python_regression": chunked, "exit_codes": checks,
                                     "ci": "never queried or triggered",
                                     "status": "PASS" if reg_ok else "FAIL"})
    repro = {"replay_runs": replays,
             "fresh_init_sha_identical_in_both_processes": all(r["init_sha256_reproduced"]
                                                              for r in replays),
             "best_round_reconstructed": all(r["best_round_matches"] for r in replays),
             "predictions_replayed_identically": all(
                 r["validation_predictions_replayed_identically"] for r in replays),
             "checkpoint_sha_stable": len({r["best_checkpoint_sha256"] for r in replays}) == 1,
             "status": "PASS" if all(r["status"] == "PASS" for r in replays) else "FAIL"}
    _write("reproducibility.json", repro)
    decided = decision(table, v2)
    ok = all(x["status"] == "PASS" for x in (method, protected, firewall, repro)) and reg_ok
    _write("run_manifest.json", {
        "checkpoint_id": "V2-FL-001", "experiment_id": "FL_IID_MODEL_V2_V1",
        "phase_result": decided["outcome"] if ok else "FAIL", "gate": "V2FLG0",
        "rounds_completed": v2["stability"]["rounds_completed"],
        "client_updates": v2["stability"]["client_updates_received"],
        "best_round": v2["best_round"], "cumulative_note": "FL training; V2-FL-002 not started",
        "ci_queried": False, "ci_triggered": False,
        "status": "PASS" if ok else "FAIL"})
    print(json.dumps({"outcome": decided["outcome"], "ok": ok}))


def _hashes() -> None:
    files = sorted(p.name for p in OUT.iterdir() if p.is_file())
    _write("artifact_hashes.json", {"artifacts": {
        f"reports/model_v2/v2_fl_001/{n}": hash_file(OUT / n)
        for n in files if n not in RUN_LOGS and n != "artifact_hashes.json"}})
    print("hashes written")


if __name__ == "__main__":
    main()
