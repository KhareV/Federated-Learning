# ruff: noqa: E501
"""FINAL-EVAL-REPAIR-002 shared helpers (extends, never edits, the FER-001 lib): amendment-aware verification of ANY frozen method lock (UFL / FER) and tag/registry helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts import final_eval_repair_lib as lib

ROOT = lib.ROOT
ENTRY = "3402dc1da1c6d5c029903a9a51a74e4ecc427ec8"
FER1_TARGET = "ce6fe2b10b13fbe494f5f531a8ac953a7b958f73"
LOCKS = {
    "UFL_LITE_001": "artifacts/ufl_lite/UFL_LITE_001_PROTOCOL_V1.lock.json", "UFL_LITE_002": "artifacts/ufl_lite/UFL_LITE_002_PROTOCOL_V1.lock.json", "UFL_LITE_003": "artifacts/ufl_lite/UFL_LITE_003_PROTOCOL_V1.lock.json",
    "FER_001": "artifacts/final_eval_repair/FINAL_EVAL_REPAIR_001_PROTOCOL_V1.lock.json",
}


def verify_lock(lock_rel: str, root: Path = ROOT) -> dict[str, Any]:
    """Bound-file hashes, with pure SUCCESSOR_COMPATIBILITY_ONLY old->new amendments (<lockdir>/<LOCKSTEM>.amendment_*.json) applied in order."""
    lock_path = root / lock_rel
    lock = json.loads(lock_path.read_text())
    expected = dict(lock["bound_files"])
    stem = lock_path.name.replace(".lock.json", "")
    chain = []
    for a in sorted(lock_path.parent.glob(f"{stem}.amendment_*.json")):
        data = json.loads(a.read_text())
        if data.get("scope") != "SUCCESSOR_COMPATIBILITY_ONLY" or data.get("result_evidence_committed_with_amendment") is not False:
            return {"lock": lock_rel, "verified": False, "reason": "AMENDMENT_NOT_PURE"}
        for path, ch in data["files"].items():
            chain.append({"amendment": a.name, "path": path, "old_matches_previous_link": expected.get(path) == ch["old_sha256"]})
            expected[path] = ch["new_sha256"]
    broken = [c for c in chain if not c["old_matches_previous_link"]]
    mismatches = [p for p, h in expected.items() if not (root / p).exists() or lib.sha(root / p) != h]
    return {"lock": lock_rel, "verified": not broken and not mismatches, "amendments": len({c["amendment"] for c in chain}), "mismatches": mismatches, "broken_chain_links": broken}


def verify_all_locks(root: Path = ROOT) -> dict[str, dict[str, Any]]:
    return {k: verify_lock(v, root) for k, v in LOCKS.items()}
