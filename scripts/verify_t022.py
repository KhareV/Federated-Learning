#!/usr/bin/env python3
"""Verification-only T022 checks; never access waveforms or run MODEL_V1."""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from fusion.episode_manager import verify_alert_policy_lock  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify() -> dict[str, object]:
    policy = verify_alert_policy_lock(ROOT)
    protocol = json.loads((ROOT / "reports/t022/protocol_audit.json").read_text())
    for relative, expected in protocol["upstream_hashes"].items():
        if sha256(ROOT / relative) != expected:
            raise RuntimeError(f"T022_UPSTREAM_IMMUTABILITY_FAILURE: {relative}")
    hashes = json.loads((ROOT / "reports/t022/artifact_hashes.json").read_text())
    for relative, expected in hashes["artifacts"].items():
        if sha256(ROOT / relative) != expected:
            raise RuntimeError(f"T022_ARTIFACT_HASH_MISMATCH: {relative}")
    with (ROOT / "manifests/task_registry_v1.csv").open(newline="", encoding="utf-8") as handle:
        tasks = {row["task_id"]: row for row in csv.DictReader(handle)}
    if tasks["T022"]["status"] != "PASS" or tasks["T023"]["status"] not in {
        "NOT_STARTED",
        "PASS",
    }:
        raise RuntimeError("T022_REGISTRY_STATE_MISMATCH")
    return {
        **policy,
        "upstream_immutability": "PASS",
        "artifact_hashes": "PASS",
        "T022": "PASS",
        "T023": tasks["T023"]["status"],
        "G9": "NOT_STARTED",
        "real_data_access": False,
    }


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2, sort_keys=True))
