"""Freeze CAP-009 method before canonical browser/result execution."""

from __future__ import annotations

import json
from pathlib import Path

from nhm.hashing import hash_file
from scripts.cap_008_protected_audit import all_locks

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "artifacts/capstone/CAPSTONE_HISTORY_EVIDENCE_PROTOCOL_V1.lock.json"
CONFIG = ROOT / "configs/capstone/cap_009_history_evidence_protocol_v1.json"
CATALOG_LOCK = ROOT / "artifacts/capstone/CAPSTONE_RESEARCH_EVIDENCE_CATALOG_V1.lock.json"
UI_LOCK = ROOT / "artifacts/capstone/CAPSTONE_UI_V1_2.lock.json"
ENTRY = ROOT / "reports/capstone/cap_009/entry_audit.json"

METHOD_FILES = (
    "api/product_app_v1_3.py",
    "capstone_persistence/session_evidence_store.py",
    "product/history/models.py",
    "product/research/catalog.py",
    "product/research/models.py",
    "product/research/service.py",
    "scripts/build_capstone_research_evidence_catalog.py",
    "scripts/verify_capstone_research_evidence_catalog.py",
    "scripts/run_capstone_product_v1_3.py",
    "scripts/run_capstone_history_e2e.py",
    "scripts/cap_009_cdp_driver.mjs",
    "scripts/freeze_capstone_ui_v1_2.py",
    "scripts/verify_capstone_ui_v1_2.py",
    "tests/test_capstone_history_evidence.py",
    "tests/test_capstone_research_catalog.py",
    "configs/capstone/cap_009_history_evidence_protocol_v1.json",
)
AMENDMENTS = (
    "artifacts/capstone/CAPSTONE_FRONTEND_PRODUCT_PROTOCOL_V1.amendment_8.json",
    "artifacts/capstone/CAPSTONE_FEDERATION_UX_PROTOCOL_V1.amendment_2.json",
)


def freeze() -> dict[str, object]:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    if len(config["capg8_criteria"]) != 145:
        raise RuntimeError("CAPG8_CRITERIA_COUNT_MISMATCH")
    prior = all_locks()
    if not all(item["verified"] for item in prior.values()):
        raise RuntimeError("PRIOR_LOCK_CHAIN_FAILED")
    catalog = json.loads(CATALOG_LOCK.read_text(encoding="utf-8"))
    prior_files = [item["lock"] for item in prior.values() if "lock" in item]
    binding = {
        path: hash_file(ROOT / path)
        for path in sorted(set(METHOD_FILES + AMENDMENTS + tuple(prior_files)))
    }
    lock = {
        "lock_id": "CAPSTONE_HISTORY_EVIDENCE_PROTOCOL_V1",
        "status": "FROZEN_ENGINEERING_PROTOCOL",
        "owner_phase": "CAP-009",
        "gate": "CAPG8",
        "entry_sha": config["entry_sha"],
        "entry_audit_sha256": hash_file(ENTRY),
        "ui_successor_sha256": hash_file(UI_LOCK),
        "catalog_sha256": hash_file(
            ROOT / "artifacts/capstone/CAPSTONE_RESEARCH_EVIDENCE_CATALOG_V1.json"
        ),
        "catalog_lock_sha256": hash_file(CATALOG_LOCK),
        "research_source_sha256": catalog["source_hashes"],
        "prior_locks_verified": sorted(prior),
        "criteria_count": len(config["capg8_criteria"]),
        "bound_files": binding,
        "freeze_basis": "before CAP-009 canonical browser and gate-result execution",
        "claim_boundary": "PERSISTED_HISTORY_AND_READ_ONLY_FROZEN_RESEARCH_EVIDENCE",
    }
    LOCK.write_text(json.dumps(lock, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return {"status": lock["status"], "sha256": hash_file(LOCK), "bound_files": len(binding)}


if __name__ == "__main__":
    print(json.dumps(freeze(), sort_keys=True))
