#!/usr/bin/env python3
"""Guarded single-condition entry point (label|quantity|feature|combined):
python -m scripts.run_v2_fl_002 <condition>.
Refuses unless the frozen method is intact and committed, the entry reference verifies, the
previous condition in the historical order has completed, and this condition has no result yet.
No scientific retry with altered seeds/configuration is possible."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from federated.model_v2_non_iid_runner import ORDER, run_condition, verify_entry
from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_fl_002"


def main() -> None:
    condition = sys.argv[1]
    if condition not in ORDER:
        sys.exit(f"unknown condition {condition}")
    freeze = json.loads((OUT / "method_freeze.json").read_text())
    drift = [p for p, d in freeze["method_file_sha256"].items() if hash_file(ROOT / p) != d]
    if drift:
        sys.exit(f"V2_FL_002_METHOD_DRIFT_BEFORE_RUN:{drift}")
    if not subprocess.run(
            ["git", "log", "--format=%H", "-n", "1", "--",
             "reports/model_v2/v2_fl_002/method_freeze.json"],
            cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip():
        sys.exit("V2_FL_002_METHOD_COMMIT_MISSING")
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "federated", "configs",
                            "scripts", "manifests"], cwd=ROOT, capture_output=True, text=True,
                           check=True).stdout.strip()
    if dirty:
        sys.exit(f"V2_FL_002_UNCOMMITTED_METHOD_CHANGES:{dirty}")
    entry = verify_entry(ROOT)
    if entry["status"] != "PASS":
        sys.exit(f"V2_FL_002_ENTRY_VERIFICATION_FAILED:{entry['problems']}")
    previous = ORDER.index(condition) - 1
    if previous >= 0 and not (OUT / f"{ORDER[previous]}_result.json").exists():
        sys.exit(f"V2_FL_002_ORDER_VIOLATION: run {ORDER[previous]} first")
    if (OUT / f"{condition}_result.json").exists():
        sys.exit("V2_FL_002_RESULT_ALREADY_EXISTS: one real run per condition")
    report = run_condition(ROOT, condition)
    (OUT / "method_commit.txt").write_text(subprocess.run(
        ["git", "log", "--format=%H", "-n", "1", "--",
         "reports/model_v2/v2_fl_002/method_freeze.json"],
        cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip() + "\n")
    print(json.dumps({"condition": condition, "best_round": report["best_round"],
                      "status": report["status"]}))


if __name__ == "__main__":
    main()
