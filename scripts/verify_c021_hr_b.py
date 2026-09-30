#!/usr/bin/env python3
"""Verification-only C021-HR-B checks from frozen rows; never read raw BIDMC."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from evaluation.bidmc_context_v2 import sha256, verify_context_lock  # noqa: E402


def main() -> None:
    result = verify_context_lock(ROOT)
    manifest = json.loads((ROOT / "reports/c021_hr_b/run_manifest.json").read_text())
    for path, expected in manifest["protected_upstream_hashes"].items():
        if sha256(ROOT / path) != expected:
            raise RuntimeError(f"C021_HR_B_UPSTREAM_IMMUTABILITY_FAILURE: {path}")
    artifacts = json.loads((ROOT / "reports/c021_hr_b/artifact_hashes.json").read_text())
    for path, expected in artifacts["artifacts"].items():
        if sha256(ROOT / path) != expected:
            raise RuntimeError(f"C021_HR_B_ARTIFACT_HASH_MISMATCH: {path}")
    with (ROOT / "manifests/task_registry_v1.csv").open(newline="", encoding="utf-8") as handle:
        tasks = {row["task_id"]: row for row in csv.DictReader(handle)}
    if tasks["T022"]["status"] != "PASS" or tasks["T023"]["status"] not in {
        "NOT_STARTED",
        "PASS",
    }:
        raise RuntimeError("C021_HR_B_TASK_STATE_MISMATCH")
    print(json.dumps({**result, "upstream_immutability": "PASS"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
