#!/usr/bin/env python3
"""Verify T029 gateway artifact, benchmark, equivalence, and F14."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from nhm.hashing import hash_file
from scripts.verify_t028 import verify as verify_t028

ROOT = Path(__file__).resolve().parents[1]


def verify_bindings(lock: dict[str, object], root: Path, label: str) -> None:
    """Reject any byte change to a hash-bound T029 artifact."""
    bindings = lock.get("bound_artifacts")
    if not isinstance(bindings, dict):
        raise RuntimeError(f"{label}_LOCK_MISMATCH")
    for path, expected in bindings.items():
        if not isinstance(path, str) or not isinstance(expected, str):
            raise RuntimeError(f"{label}_LOCK_MISMATCH")
        if hash_file(root / path) != expected:
            raise RuntimeError(f"{label}_TAMPER:{path}")


def verify() -> dict[str, object]:
    verify_t028()
    method = json.loads((ROOT / "artifacts/GATEWAY_FP32_METHOD_V1.lock.json").read_text())
    verify_bindings(method, ROOT, "GATEWAY_METHOD")
    equivalence = json.loads((ROOT / "reports/t029/deployment_equivalence.json").read_text())
    if equivalence["status"] != "PASS" or equivalence["rows_compared"] != 2157:
        raise RuntimeError("GATEWAY_EQUIVALENCE_FAILURE")
    if equivalence["maximum_absolute_raw_logit_delta"] > 1e-5:
        raise RuntimeError("GATEWAY_EQUIVALENCE_FAILURE")
    if equivalence["decision_agreement_fraction"] != 1.0:
        raise RuntimeError("GATEWAY_DECISION_MISMATCH")
    with (ROOT / "reports/t029/latency_samples.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 1000 or not all(row["finite_output"] == "True" for row in rows):
        raise RuntimeError("GATEWAY_BENCHMARK_INVALID")
    latency = json.loads((ROOT / "reports/t029/latency_summary.json").read_text())
    memory = json.loads((ROOT / "reports/t029/memory_benchmark.json").read_text())
    if latency["status"] != "PASS" or memory["status"] != "PASS":
        raise RuntimeError("GATEWAY_RESOURCE_EVIDENCE_INVALID")
    lock = json.loads((ROOT / "artifacts/GATEWAY_ARTIFACT_V1.lock.json").read_text())
    if lock["freeze_id"] != "F14" or lock["status"] != "FROZEN":
        raise RuntimeError("F14_LOCK_MISMATCH")
    verify_bindings(lock, ROOT, "F14")
    inventory = json.loads((ROOT / "reports/t029/artifact_hashes.json").read_text())
    for path, expected in inventory.items():
        if hash_file(ROOT / path) != expected:
            raise RuntimeError(f"T029_ARTIFACT_HASH_MISMATCH:{path}")
    return {
        "status": "PASS",
        "artifact": "GATEWAY_FP32_V1",
        "format": "TORCHSCRIPT_SCRIPT",
        "rows": 2157,
        "latencies": 1000,
        "F14": "FROZEN",
        "G15": "PASS",
    }


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2, sort_keys=True))
