"""Fail closed on CAP-010 method or predecessor drift (amendment-chain aware)."""

from __future__ import annotations

import json
from pathlib import Path

from nhm.hashing import hash_file
from scripts.cap_006_protected_audit import verify_amended_lock
from scripts.cap_008_protected_audit import all_locks

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "artifacts/capstone/CAPSTONE_FACULTY_DEMO_PROTOCOL_V1.lock.json"


def verify() -> dict[str, object]:
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    chain = verify_amended_lock(LOCK, "CAPSTONE_FACULTY_DEMO_PROTOCOL_V1.amendment_*.json")
    failures = list(chain["mismatches"]) + [str(c) for c in chain["broken_chain_links"]]
    if hash_file(ROOT / "reports/capstone/cap_010/entry_audit.json") != lock["entry_audit_sha256"]:
        failures.append("entry_audit")
    if not all(item["verified"] for item in all_locks().values()):
        failures.append("prior_lock_chain")
    return {"status": "PASS" if not failures else "FAIL", "failures": sorted(set(failures)),
            "lock_sha256": hash_file(LOCK), "bound_files": len(lock["bound_files"])}


if __name__ == "__main__":
    result = verify()
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result["status"] == "PASS" else 1)
