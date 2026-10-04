#!/usr/bin/env python3
"""V2_FL_003_EVIDENCE_FINALIZER_V2 (C-V2-FL-003-FREEZE-INTEGRITY). Additive, reconstruction-only
successor of the frozen scripts/finalize_v2_fl_003_evidence.py (restored byte-identically).

SCIENTIFIC METHOD UNCHANGED. TRAINING OUTPUTS ALREADY FROZEN. EVIDENCE-FINALIZATION CORRECTION ONLY.

The ONLY code change relative to the frozen finalizer's evidence functions is a lazy,
schema-aware communication logical-byte extraction (`_logical_bytes`): the historical code evaluated
an eager dict default and raised KeyError on V2-FL-002 records. Nothing about training, the FedProx
objective, mu candidates/selection/guardrail, checkpoint selection, bootstrap method, patient
metrics, firewall rules or PASS criteria changes. Inputs are read from the committed V2-FL-003
evidence (IN); every recomputed artifact is written to a separate directory (OUT) and compared with
the historical file; no historical evidence is overwritten. The firewall is reconstructed from the
access ledger as committed in the V2-FL-003 result commit.
"""

from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path

import numpy as np
import yaml

from evaluation.bootstrap import bootstrap_replicates, generate_patient_draws
from federated.model_v2_fedprox import CANDIDATES
from federated.model_v2_fedprox_runner import mu_token, run_key
from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
IN = ROOT / "reports/model_v2/v2_fl_003"
OUT = ROOT / "reports/model_v2/c_v2_fl_003_freeze_integrity/reconstruction"
RESULT_COMMIT = "87943640b86fcca2dd769690e5df2706c2f2a793"
CONFIG = yaml.safe_load((ROOT / "configs/model_v2/fedprox_v2.yaml").read_text())
CONDS = ["iid", "label", "quantity", "feature", "combined"]
RUN_LOGS = {"pytest_collected_nodes.txt", "pytest_chunk_manifest.csv", "pytest_chunk_results.csv"}


def _load(name: str) -> dict:
    return json.loads((IN / name).read_text(encoding="utf-8"))


def _write(name: str, data: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _csv(path: Path) -> list[dict]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _sh(*args: str) -> str:
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True, check=False
                          ).stdout.strip()


def selected_mu() -> float:
    return float(json.loads((ROOT / "artifacts/FEDPROX_MU_V2.lock.json").read_text())[
        "selected_mu"])


def fedprox_dir(condition: str) -> Path:
    mu = selected_mu()
    if condition == "label":
        return IN / run_key("label", mu, "candidate")[1]
    return IN / run_key(condition, mu, "transfer")[1]


def fedavg_paths(condition: str) -> dict[str, Path]:
    if condition == "iid":
        base = ROOT / "reports/model_v2/v2_fl_001"
        return {"result": base / "fl_iid_model_v2_result.json", "rounds": base / "round_log.csv",
                "predictions": base / "validation_predictions_best_round.csv",
                "patients": base / "validation_patient_metrics_best_round.json"}
    base = ROOT / "reports/model_v2/v2_fl_002"
    return {"result": base / f"{condition}_result.json",
            "rounds": base / f"{condition}_round_log.csv",
            "predictions": base / f"{condition}_validation_predictions.csv",
            "patients": base / f"{condition}_validation_patient_metrics.json"}


def _patient_stats(patients: dict) -> dict:
    values = [g["AUPRC"] for g in patients["per_group"] if g["AUPRC"] is not None]
    return {"mean_AUPRC": float(np.mean(values)), "median_AUPRC": float(np.median(values)),
            "worst_AUPRC": float(np.min(values)), "finite_patients": len(values)}


def _logical_bytes(communication: dict) -> int:
    """Lazy, schema-aware: V2-FL-001 stores directional totals, V2-FL-002/003 one logical total."""
    if "total_logical_payload_bytes" in communication:
        return int(communication["total_logical_payload_bytes"])
    return int(communication["total_server_to_client_bytes"]
               + communication["total_client_to_server_bytes"])


def _runtime(result: dict) -> float:
    return float(result.get("wall_seconds", result.get("total_round_wall_seconds", 0.0)))


def comparison() -> dict:
    out: dict = {"descriptive_only": True, "no_claim_that_fedprox_wins": True, "conditions": {}}
    patient_rows: dict = {}
    for c in CONDS:
        avg_p = fedavg_paths(c)
        avg = json.loads(avg_p["result"].read_text())
        prox_dir = fedprox_dir(c)
        prox = json.loads((prox_dir / "result.json").read_text())
        avg_patients = json.loads(avg_p["patients"].read_text())
        prox_patients = json.loads((prox_dir / "validation_patient_metrics.json").read_text())
        ab, pb = avg["best_validation"], prox["best_validation"]

        def metrics(r: dict, b: dict) -> dict:
            return {"best_round": r["best_round"], "best_AUPRC": b["AUPRC"],
                    "round_50_AUPRC": float(r["round_50_validation_AUPRC"]),
                    "AUROC": b["AUROC"], "F1_at_0_5": b["pooled_F1"],
                    "precision": b["precision"], "sensitivity": b["sensitivity"],
                    "specificity": b["specificity"], "BCE": b["BCE"],
                    "patient_macro_F1": b["patient_macro_F1"], "rounds_to_best": r["best_round"]}

        fa, fp = metrics(avg, ab), metrics(prox, pb)
        out["conditions"][c] = {
            "FedAvg": {**fa, **{f"validation_patient_{k}": v for k, v in _patient_stats(
                avg_patients).items()},
                "logical_bytes": _logical_bytes(avg["communication"]),
                "runtime_seconds": _runtime(avg)},
            "FedProx": {**fp, **{f"validation_patient_{k}": v for k, v in _patient_stats(
                prox_patients).items()},
                "logical_bytes": prox["communication"]["total_logical_payload_bytes"],
                "runtime_seconds": _runtime(prox)},
            "delta_best_AUPRC_FedProx_minus_FedAvg": fp["best_AUPRC"] - fa["best_AUPRC"],
            "delta_round_50_AUPRC": fp["round_50_AUPRC"] - fa["round_50_AUPRC"],
            "delta_AUROC": fp["AUROC"] - fa["AUROC"],
            "delta_patient_macro_F1": fp["patient_macro_F1"] - fa["patient_macro_F1"],
            "best_round_shift": fp["best_round"] - fa["best_round"],
            "mu": selected_mu(), "FedProx_is_label_alias_of_selected_candidate": c == "label"}
        patient_rows[c] = {
            "FedAvg": avg_patients["per_group"], "FedProx": prox_patients["per_group"],
            "delta_AUPRC_by_patient": {
                a["participant_group_id"]: (
                    None if a["AUPRC"] is None or b["AUPRC"] is None else b["AUPRC"] - a["AUPRC"])
                for a, b in zip(avg_patients["per_group"], prox_patients["per_group"],
                                strict=True)}}
    _write("fedavg_vs_fedprox_comparison.json", out)
    _write("patient_level_comparison.json", {
        "validation_patients_are_clients": False, "undefined_values_preserved": True,
        "conditions": patient_rows})
    return out


def bootstrap() -> dict:
    base_paths = fedavg_paths("iid")["predictions"]
    rows = sorted(_csv(base_paths), key=lambda r: r["example_id"])
    groups = np.asarray([r["participant_group_id"] for r in rows])
    ids = [r["example_id"] for r in rows]
    patients, draws = generate_patient_draws(groups, 2000, 20260927)

    def replicates(path: Path) -> np.ndarray:
        data = sorted(_csv(path), key=lambda r: r["example_id"])
        if [r["example_id"] for r in data] != ids:
            raise RuntimeError("validation example mismatch")
        y = np.asarray([int(r["label"]) for r in data])
        p = np.asarray([float(r["raw_sigmoid_probability"]) for r in data])
        _, boot = bootstrap_replicates(groups, y, p, (p >= 0.5).astype(int), replicates=2000,
                                       seed=20260927, draws=draws)
        return np.asarray([float(r["AUPRC"]) for r in boot])

    out: dict = {"B": 2000, "seed": 20260927, "validation_patient_groups": int(patients.size),
                 "draw_source": "evaluation.bootstrap.generate_patient_draws (deterministic PCG64; "
                 "identical draws to V2-FL-001/002)",
                 "wording": "DEVELOPMENT DIAGNOSTICS ONLY: both methods select their checkpoint "
                 "on this VALIDATION partition and mu was selected on it too; not untouched-"
                 "generalization intervals; not a V2FLG2 criterion",
                 "conditions": {}}
    for c in CONDS:
        d = replicates(fedprox_dir(c) / "validation_predictions.csv") - replicates(
            fedavg_paths(c)["predictions"])
        lo, hi = np.percentile(d, [2.5, 97.5])
        out["conditions"][c] = {"FedProx_minus_FedAvg_mean_delta_AUPRC": float(d.mean()),
                                "ci95": [float(lo), float(hi)],
                                "fraction_positive": float(np.mean(d > 0))}
    _write("paired_bootstrap.json", out)
    return out


def accounting() -> dict:
    cand = {}
    for mu in CANDIDATES:
        r = json.loads((IN / f"candidates/mu_{mu_token(mu)}/result.json").read_text())
        cand[str(mu)] = r
    trans = {c: json.loads((fedprox_dir(c) / "result.json").read_text())
             for c in CONFIG["transfer_order"]}

    def tally(group: dict) -> dict:
        return {"rounds": sum(r["stability"]["rounds_completed"] for r in group.values()),
                "updates": sum(r["stability"]["client_updates_received"] for r in group.values()),
                "failed_clients": sum(r["stability"]["failed_clients"] for r in group.values()),
                "nonfinite_tensors": sum(r["stability"]["nonfinite_tensor_count"]
                                         for r in group.values()),
                "aggregation_failures": sum(r["stability"]["aggregation_failures"]
                                            for r in group.values())}

    c, t = tally(cand), tally(trans)
    data = {"candidates": c, "transfer": t,
            "total_positive_mu_updates": c["updates"] + t["updates"],
            "expected": CONFIG["expected_accounting"], "loader_failures": 0,
            "infrastructure_retries": 0, "selected_label_candidate_retrained": False,
            "round_0_all_FL_INIT_V2": all(
                r["round_0_state_sha256"] == CONFIG["initialization"]["round_0_state_sha256"]
                and r["round_0_validation"]["AUPRC"]
                == CONFIG["initialization"]["round_0_validation_AUPRC"]
                for r in [*cand.values(), *trans.values()])}
    _write("accounting_audit.json", data)
    comm = {"parameter_count": 57553, "network_traffic_measured": False,
            "runs": {k: {**v["communication"], "wall_seconds": v["wall_seconds"]}
                     for k, v in {**{f"candidate_mu_{m}": r for m, r in cand.items()},
                                  **{f"transfer_{k}": r for k, r in trans.items()}}.items()},
            "fedavg_reference_bytes_per_round": 1926624,
            "note": "FedProx changes the local objective, not the transported state size"}
    _write("communication_compute.json", comm)
    return data


def firewall() -> dict:
    ledger_text = _sh("git", "show", f"{RESULT_COMMIT}:reports/model_v2/access_ledger.jsonl")
    ledger = [json.loads(line) for line in ledger_text.splitlines() if line.strip()]
    mine = [r for r in ledger if r.get("stage_id") == "V2-FL-003"]
    partitions = sorted({r["partition"] for r in mine})
    nstdb = [r for r in mine if r["partition"] == "NSTDB"]
    ok_noise = all(r["access_type"] == "NSTDB_PURE_NOISE_TRAINING_RESOURCE" for r in nstdb)
    data = {"rows": len(mine), "partitions_accessed": partitions, "NSTDB_rows": len(nstdb),
            "NSTDB_only_as_pure_noise_training_resource": ok_noise,
            "CALIBRATION_accessed": "CALIBRATION" in partitions,
            "INTERNAL_TEST_accessed": "INTERNAL_TEST" in partitions,
            "INCART_accessed": "INCART" in partitions, "BIDMC_accessed": "BIDMC" in partitions,
            "WEARABLE_accessed": False, "WEARABLE_SIM_efficacy_used": False,
            "status": "PASS" if set(partitions) <= {"TRAIN", "VALIDATION", "NSTDB"} and ok_noise
            else "FAIL"}
    _write("heldout_firewall_audit.json", data)
    return data


def chronology() -> dict:
    lock = ROOT / "artifacts/FEDPROX_MU_V2.lock.json"
    added = _sh("git", "log", "--diff-filter=A", "--format=%H", "--", str(lock.relative_to(ROOT))
                ).splitlines()
    lock_commit = added[-1] if added else ""
    ancestor = bool(lock_commit) and subprocess.run(
        ["git", "merge-base", "--is-ancestor", lock_commit, "HEAD"], cwd=ROOT,
        check=False).returncode == 0
    in_lock_commit = _sh("git", "ls-tree", "-r", "--name-only", lock_commit,
                         "reports/model_v2/v2_fl_003/transfer") if lock_commit else "x"
    lock_time = int(_sh("git", "show", "-s", "--format=%ct", lock_commit) or 0)
    earlier = []
    for c in CONFIG["transfer_order"]:
        path = fedprox_dir(c) / "result.json"
        if path.stat().st_mtime < lock_time:
            earlier.append(c)
    method_commit = _sh("git", "log", "--format=%H", "-n", "1", "--",
                        "reports/model_v2/v2_fl_003/method_freeze.json")
    candidates_before_lock = in_lock_commit == "" or "result.json" not in in_lock_commit
    data = {"method_commit": method_commit, "selection_freeze_commit": lock_commit,
            "selection_freeze_is_ancestor_of_head": ancestor,
            "transfer_results_in_or_before_freeze_commit": bool(
                "result.json" in in_lock_commit),
            "transfer_result_files_older_than_freeze": earlier,
            "frozen_before_transfer_runs": ancestor and candidates_before_lock and not earlier,
            "status": "PASS" if ancestor and candidates_before_lock and not earlier else "FAIL"}
    _write("chronology_audit.json", data)
    return data


def selection_audit() -> dict:
    lock = json.loads((ROOT / "artifacts/FEDPROX_MU_V2.lock.json").read_text())
    selection = json.loads((IN / "selection/selection.json").read_text())
    table = (IN / "selection/mu_candidates.csv").read_bytes()
    from nhm.hashing import hash_bytes

    data = {"lock_selected_mu": lock["selected_mu"], "selection_selected_mu": selection[
        "selected_mu"], "consistent": lock["selected_mu"] == selection["selected_mu"],
            "candidate_table_hash_matches": hash_bytes(table) == lock["candidate_table_sha256"],
            "candidate_set": lock["candidate_set"], "ranking": selection["ranking"],
            "human_override": lock["human_override"],
            "guardrail_threshold": selection["guardrail_threshold"],
            "guardrail_nonbinding": all(c["guardrail_pass"]
                                        for c in selection["evaluated_candidates"]),
            "status": "PASS" if (lock["selected_mu"] == selection["selected_mu"]
                                 and hash_bytes(table) == lock["candidate_table_sha256"]
                                 and lock["candidate_set"] == list(CANDIDATES)) else "FAIL"}
    _write("selection_audit.json", data)
    return data


RECONSTRUCTED = ["fedavg_vs_fedprox_comparison.json", "patient_level_comparison.json",
                 "paired_bootstrap.json", "accounting_audit.json", "communication_compute.json",
                 "heldout_firewall_audit.json", "chronology_audit.json", "selection_audit.json"]


def main() -> None:
    comparison()
    bootstrap()
    accounting()
    firewall()
    chronology()
    selection_audit()
    results = {}
    for name in RECONSTRUCTED:
        historical = json.loads((IN / name).read_text())
        rebuilt = json.loads((OUT / name).read_text())
        results[name] = {"identical": historical == rebuilt,
                         "historical_sha256": hash_file(IN / name),
                         "reconstructed_sha256": hash_file(OUT / name)}
    lock = json.loads((ROOT / "artifacts/FEDPROX_MU_V2.lock.json").read_text())
    candidate_table_identical = hash_file(IN / "selection/mu_candidates.csv") == lock[
        "candidate_table_sha256"]
    data = {"finalizer_id": "V2_FL_003_EVIDENCE_FINALIZER_V2", "files": results,
            "all_identical": all(r["identical"] for r in results.values()),
            "candidate_table_sha256": hash_file(IN / "selection/mu_candidates.csv"),
            "candidate_table_identical": candidate_table_identical,
            "scientific_method_changed": False, "training_changed": False,
            "historical_evidence_overwritten": False,
            "status": "PASS" if (all(r["identical"] for r in results.values())
                         and candidate_table_identical) else "FAIL"}
    _write("reconstruction_equality.json", data)
    print(json.dumps({"status": data["status"], "all_identical": data["all_identical"]}))


if __name__ == "__main__":
    main()
