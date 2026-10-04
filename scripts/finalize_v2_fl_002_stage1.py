#!/usr/bin/env python3
"""Stage 1 of V2-FL-002 evidence assembly (everything except the regression criterion), so that
the chunked regression can run against complete evidence. Imports the frozen finalizer's functions
unchanged; the frozen finalizer's main() later overwrites v2flg1_criteria.json with the final,
regression-inclusive criteria. Stage-1 output marks regression PENDING_STAGE1 explicitly."""

from __future__ import annotations

import json
import subprocess

import scripts.finalize_v2_fl_002_evidence as fin
from nhm.hashing import hash_file

ROOT, OUT = fin.ROOT, fin.OUT


def main() -> None:
    fin.tables()
    boot = fin.bootstrap()
    acct = fin.accounting()
    firewall = fin.firewall()
    freeze = fin._load("method_freeze.json")
    changed = sorted(p for p, d in freeze["method_file_sha256"].items()
                     if hash_file(ROOT / p) != d)
    method_commit = (OUT / "method_commit.txt").read_text().strip()
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", method_commit, "HEAD"],
                              cwd=ROOT, check=False).returncode == 0
    baseline = fin._load("protected_baseline.json")["artifacts"]
    drift = sorted(p for p, d in baseline.items() if hash_file(ROOT / p) != d)
    fin._write("method_immutability_audit.json", {
        "method_commit": method_commit, "ancestor_of_head": ancestor,
        "method_files_changed_since_freeze": changed,
        "status": "PASS" if not changed and ancestor else "FAIL"})
    fin._write("protected_artifact_audit.json", {
        "checked": len(baseline), "drift": drift, "status": "PASS" if not drift else "FAIL"})
    runs = [fin._load(f"replay_verification_{n}.json") for n in ("run_1", "run_2")]
    manifest = fin._load("manifest_audit.json")
    noise = fin._load("noise_verification.json")
    tracked = subprocess.run(["git", "ls-files", "checkpoints/model_v2/v2_fl_002"], cwd=ROOT,
                             capture_output=True, text=True, check=True).stdout.split()
    criteria = {
        "all_four_conditions_ran": all((OUT / f"{n}_result.json").exists() for n in fin.ORDER),
        "exact_FL_INIT_V2_all": acct["round_0_matches_V2_FL_001"],
        "exact_frozen_manifests": manifest["status"] == "PASS",
        "patient_integrity_closure": all(c["closure_exact"] and not c["duplicates"]
                                         for c in manifest["conditions"].values()),
        "feature_noise_matches_frozen": noise["status"] == "PASS",
        "NSTDB_noise_training_only": firewall["NSTDB_only_as_pure_noise_training_resource"],
        "fifty_rounds_each": all(r["rounds"] == 50 for r in acct["conditions"].values()),
        "updates_1600_of_1600": acct["updates_valid"] == 1600,
        "finite_states": acct["nonfinite_tensors"] == 0 and acct["aggregation_failures"] == 0,
        "checkpoints_git_tracked": len(tracked) == 8,
        "replay_reconstruction": all(r["status"] == "PASS" for r in runs),
        "protected_unchanged": not drift, "method_unchanged": not changed and ancestor,
        "firewall": firewall["status"] == "PASS", "regression": "PENDING_STAGE1"}
    fin._write("v2flg1_criteria.json", {
        "criteria": criteria, "performance_direction_irrelevant": True,
        "status": "STAGE1_PENDING_REGRESSION"})
    print(json.dumps({"stage1_failed": [k for k, v in criteria.items() if v is False],
                      "bootstrap_B": boot["B"]}))


if __name__ == "__main__":
    main()
