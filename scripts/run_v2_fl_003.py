#!/usr/bin/env python3
"""Guarded V2-FL-003 entry point.
    python -m scripts.run_v2_fl_003 candidate <mu>      # LABEL-only mu candidate (0.001/0.01/0.1)
    python -m scripts.run_v2_fl_003 transfer <condition> # selected-mu run, ONLY after FEDPROX_MU_V2
Refuses unless the frozen method is intact and committed, mu=0 equivalence passed, and (for
transfer) the selection was frozen and COMMITTED earlier. One real run per run key."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

from federated.model_v2_fedprox import CANDIDATES
from federated.model_v2_fedprox_runner import CONFIG_RELATIVE, OUT_RELATIVE, run_fedprox, run_key
from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / OUT_RELATIVE
MU_LOCK = ROOT / "artifacts/FEDPROX_MU_V2.lock.json"


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                          check=True).stdout.strip()


def main() -> None:
    mode, target = sys.argv[1], sys.argv[2]
    config = yaml.safe_load((ROOT / CONFIG_RELATIVE).read_text())
    freeze = json.loads((OUT / "method_freeze.json").read_text())
    drift = [p for p, d in freeze["method_file_sha256"].items() if hash_file(ROOT / p) != d]
    if drift:
        sys.exit(f"V2_FL_003_METHOD_DRIFT_BEFORE_RUN:{drift}")
    if not _git("log", "--format=%H", "-n", "1", "--",
                "reports/model_v2/v2_fl_003/method_freeze.json"):
        sys.exit("V2_FL_003_METHOD_COMMIT_MISSING")
    dirty = _git("status", "--porcelain", "--", "federated", "configs", "scripts", "manifests",
                 "artifacts")
    if dirty:
        sys.exit(f"V2_FL_003_UNCOMMITTED_METHOD_OR_LOCK_CHANGES:{dirty}")
    if json.loads((OUT / "mu0_equivalence.json").read_text())["status"] != "PASS":
        sys.exit("V2_FL_003_MU0_EQUIVALENCE_NOT_PASS")
    if mode == "candidate":
        mu, condition, role = float(target), "label", "candidate"
        if mu not in CANDIDATES:
            sys.exit("V2_FL_003_MU_NOT_IN_PREDECLARED_SET")
    elif mode == "transfer":
        condition, role = target, "transfer"
        if condition not in config["transfer_order"]:
            sys.exit("V2_FL_003_CONDITION_NOT_A_TRANSFER_RUN (label reuses the selected candidate)")
        if not MU_LOCK.exists() or not _git("log", "--format=%H", "-n", "1", "--",
                                            "artifacts/FEDPROX_MU_V2.lock.json"):
            sys.exit("V2_FL_003_MU_NOT_FROZEN_AND_COMMITTED_BEFORE_TRANSFER")
        lock = json.loads(MU_LOCK.read_text())
        mu = float(lock["selected_mu"])
        previous = config["transfer_order"].index(condition) - 1
        if previous >= 0:
            prior_key = run_key(config["transfer_order"][previous], mu, "transfer")[1]
            if not (OUT / prior_key / "result.json").exists():
                sys.exit("V2_FL_003_ORDER_VIOLATION")
    else:
        sys.exit("mode must be candidate|transfer")
    _, report_sub, _ = run_key(condition, mu, role)
    if (OUT / report_sub / "result.json").exists():
        sys.exit("V2_FL_003_RESULT_ALREADY_EXISTS: one real run per run key")
    report = run_fedprox(ROOT, condition, mu, role)
    print(json.dumps({"mode": mode, "condition": condition, "mu": mu,
                      "best_round": report["best_round"], "status": report["status"]}))


if __name__ == "__main__":
    main()
