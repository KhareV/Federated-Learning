#!/usr/bin/env python3
"""Deterministically copy CAP-009 facts from approved frozen JSON summaries only.

Never opens prediction tables, raw biomedical records, or scientific execution modules.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from product.research.catalog import FL, ML, SCIENTIFIC_FL_PHASES, FactSpec

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "artifacts/capstone/CAPSTONE_RESEARCH_EVIDENCE_CATALOG_V1.json"
LOCK = ROOT / "artifacts/capstone/CAPSTONE_RESEARCH_EVIDENCE_CATALOG_V1.lock.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_path(spec: FactSpec) -> Path:
    if spec.source == "../artifacts/CAL_V2.json":
        return ROOT / "artifacts/CAL_V2.json"
    path = ROOT / "reports/model_v2" / spec.source
    if path.suffix not in (".json", ".md") or not path.resolve().is_relative_to(
        (ROOT / "reports/model_v2").resolve()
    ):
        raise ValueError("NON_APPROVED_SOURCE_PATH")
    return path


def extraction(spec: FactSpec) -> dict[str, Any]:
    path = source_path(spec)
    if path.suffix == ".md":
        if spec.source != "v2_fl_eval_001/final_handoff.md" or spec.locator != ("line", 16):
            raise ValueError("NON_APPROVED_MARKDOWN_LOCATOR")
        value: Any = path.read_text(encoding="utf-8").splitlines()[15]
    else:
        value = json.loads(path.read_text(encoding="utf-8"))
        for part in spec.locator:
            value = value[part]
    return {
        "fact_id": spec.fact_id, "value": value, "unit": spec.unit, "role": spec.role,
        "phase": spec.phase, "source_relative_path": path.relative_to(ROOT).as_posix(),
        "source_sha256": sha(path), "source_locator": list(spec.locator),
        "interpretation": f"Direct frozen summary value; role {spec.role}.",
        "limitations": "Research/engineering evidence only; not diagnostic or clinical efficacy.",
    }


def build() -> tuple[dict[str, Any], dict[str, Any]]:
    ml = [extraction(spec) for spec in ML]
    fl = [extraction(spec) for spec in FL]
    catalog = {
        "catalog_id": "CAPSTONE_RESEARCH_EVIDENCE_CATALOG_V1",
        "evidence_version": "FROZEN_SUMMARY_PROJECTION_V1",
        "generated_from_frozen_sources": True,
        "ml_facts": ml, "fl_facts": fl,
        "scientific_fl_phases": list(SCIENTIFIC_FL_PHASES),
        "v2_fl_005_role": "FL_ENGINEERING_DEMO_NOT_SCIENTIFIC_EFFICACY",
        "claim_boundary": "READ_ONLY_NON_DIAGNOSTIC_RESEARCH_EVIDENCE",
    }
    raw = (json.dumps(catalog, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()
    sources = {f["source_relative_path"]: f["source_sha256"] for f in ml + fl}
    lock = {
        "lock_id": "CAPSTONE_RESEARCH_EVIDENCE_CATALOG_V1",
        "catalog_sha256": hashlib.sha256(raw).hexdigest(),
        "source_hashes": dict(sorted(sources.items())),
        "status": "FROZEN_READ_ONLY_PRESENTATION",
    }
    return catalog, lock


def write() -> None:
    catalog, lock = build()
    CATALOG.parent.mkdir(parents=True, exist_ok=True)
    CATALOG.write_text(json.dumps(catalog, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    LOCK.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n")
    print(lock["catalog_sha256"])


if __name__ == "__main__":
    write()
