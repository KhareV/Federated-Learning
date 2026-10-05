#!/usr/bin/env python3
"""Fail closed on source, fact, catalog, or lock tampering."""

from __future__ import annotations

import json

from scripts.build_capstone_research_evidence_catalog import CATALOG, LOCK, build, sha


def verify() -> dict[str, object]:
    expected_catalog, expected_lock = build()
    actual_catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    actual_lock = json.loads(LOCK.read_text(encoding="utf-8"))
    expected_catalog_bytes = (json.dumps(expected_catalog, indent=2, sort_keys=True,
                                         ensure_ascii=False) + "\n").encode()
    expected_lock_bytes = (json.dumps(expected_lock, indent=2, sort_keys=True) + "\n").encode()
    if CATALOG.read_bytes() != expected_catalog_bytes or LOCK.read_bytes() != expected_lock_bytes:
        raise ValueError("RESEARCH_CATALOG_BYTE_DRIFT")
    if actual_catalog != expected_catalog or actual_lock != expected_lock:
        raise ValueError("RESEARCH_CATALOG_FACT_OR_SOURCE_DRIFT")
    if sha(CATALOG) != actual_lock["catalog_sha256"]:
        raise ValueError("RESEARCH_CATALOG_HASH_MISMATCH")
    ml = {f["fact_id"]: f["value"] for f in actual_catalog["ml_facts"]}
    fl = {f["fact_id"]: f["value"] for f in actual_catalog["fl_facts"]}
    if not (ml["promotion_decision"] == "MODEL_V2_NOT_PROMOTED_RELEASE_CI"
            and ml["promotion_eligible"] is False
            and ml["system_release_accepted"] is True
            and ml["model_id"] == "MODEL_V2_FINAL"
            and ml["calibration_domain"] == "MIT-BIH-v1.0.0"
            and fl["fedprox_no_general_win"] is True
            and fl["protected_clear_updates"] == 0
            and "differential privacy" in fl["secagg_unsupported_claims"]):
        raise ValueError("RESEARCH_NEGATIVE_FINDING_DRIFT")
    if "V2-FL-005" in actual_catalog["scientific_fl_phases"]:
        raise ValueError("ENGINEERING_DEMO_IN_SCIENTIFIC_SERIES")
    return {"status": "PASS", "catalog_sha256": sha(CATALOG),
            "source_count": len(actual_lock["source_hashes"]),
            "fact_count": len(actual_catalog["ml_facts"]) + len(actual_catalog["fl_facts"])}


if __name__ == "__main__":
    print(json.dumps(verify(), sort_keys=True))
