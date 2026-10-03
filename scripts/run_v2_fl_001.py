#!/usr/bin/env python3
"""Guarded entry point for the single real V2-FL-001 run. Refuses to run unless the frozen method
is intact (method_freeze.json hashes), the METHOD commit is an ancestor of HEAD, and no result
exists yet (one real run; no silent retries with altered seeds)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from federated.model_v2_fedavg_runner import run
from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_fl_001"


def main() -> None:
    freeze = json.loads((OUT / "method_freeze.json").read_text())
    drift = [p for p, d in freeze["method_file_sha256"].items() if hash_file(ROOT / p) != d]
    if drift:
        sys.exit(f"V2_FL_001_METHOD_DRIFT_BEFORE_RUN:{drift}")
    method_commit = subprocess.run(
        ["git", "log", "--format=%H", "-n", "1", "--", "reports/model_v2/v2_fl_001/method_freeze.json"],  # noqa: E501
        cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    if not method_commit:
        sys.exit("V2_FL_001_METHOD_COMMIT_MISSING: commit the method before the real run")
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "federated", "configs", "scripts"],  # noqa: E501
                           cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    if dirty:
        sys.exit(f"V2_FL_001_UNCOMMITTED_METHOD_CHANGES:{dirty}")
    if (OUT / "fl_iid_model_v2_result.json").exists():
        sys.exit("V2_FL_001_RESULT_ALREADY_EXISTS: one real run only")
    report = run(ROOT)
    (OUT / "method_commit.txt").write_text(method_commit + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "best_round": report["best_round"],
                      "method_commit": method_commit}))


if __name__ == "__main__":
    main()
