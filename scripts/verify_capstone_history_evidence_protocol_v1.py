"""Fail closed on CAP-009 method, source, or predecessor drift."""

from __future__ import annotations

import json
from pathlib import Path

from nhm.hashing import hash_file
from scripts.cap_008_protected_audit import all_locks
from scripts.verify_capstone_research_evidence_catalog import verify as verify_catalog
from scripts.verify_capstone_ui_v1_2 import verify as verify_ui

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "artifacts/capstone/CAPSTONE_HISTORY_EVIDENCE_PROTOCOL_V1.lock.json"


def verify() -> dict[str, object]:
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    expected = dict(lock["bound_files"])
    for path, key in (
        ("reports/capstone/cap_009/entry_audit.json", "entry_audit_sha256"),
        ("artifacts/capstone/CAPSTONE_UI_V1_2.lock.json", "ui_successor_sha256"),
        ("artifacts/capstone/CAPSTONE_RESEARCH_EVIDENCE_CATALOG_V1.json", "catalog_sha256"),
        (
            "artifacts/capstone/CAPSTONE_RESEARCH_EVIDENCE_CATALOG_V1.lock.json",
            "catalog_lock_sha256",
        ),
    ):
        expected[path] = lock[key]
    expected.update(lock["research_source_sha256"])
    chain_failures: list[str] = []
    for amendment in sorted((ROOT / "artifacts/capstone").glob(
        "CAPSTONE_HISTORY_EVIDENCE_PROTOCOL_V1.amendment_*.json"
    )):
        data = json.loads(amendment.read_text(encoding="utf-8"))
        for path, change in data["files"].items():
            # Individual frontend files are transitively bound by the UI successor
            # lock. The protocol binds that lock's SHA, not every frontend path.
            if path in expected and expected[path] != change["old_sha256"]:
                chain_failures.append(f"{amendment.name}:{path}")
            expected[path] = change["new_sha256"]
    failures = [path for path, digest in expected.items()
                if hash_file(ROOT / path) != digest]
    failures.extend(chain_failures)
    if not all(item["verified"] for item in all_locks().values()):
        failures.append("prior_lock_chain")
    if verify_ui()["status"] != "PASS":
        failures.append("ui_successor")
    if verify_catalog()["status"] != "PASS":
        failures.append("research_catalog")
    return {"status": "PASS" if not failures else "FAIL", "failures": sorted(set(failures)),
            "lock_sha256": hash_file(LOCK), "bound_files": len(lock["bound_files"])}


if __name__ == "__main__":
    result = verify()
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result["status"] == "PASS" else 1)
