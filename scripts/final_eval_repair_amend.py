# ruff: noqa: E501
"""Write the pure SUCCESSOR_COMPATIBILITY_ONLY amendments that register FINAL-EVAL-REPAIR-001's successor-aware edits of historically bound verifier/test files.
Facts only: exact old (entry) and new SHA-256 per file; no result evidence. Historical lock files are never modified."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts import final_eval_repair_lib as lib

ROOT = lib.ROOT
CAP = ROOT / "artifacts/capstone"
SPEC = (
    (CAP / "CAPSTONE_FRONTEND_PRODUCT_PROTOCOL_V1.amendment_9_2.json", "CAPSTONE_FRONTEND_PRODUCT_PROTOCOL_V1_AMENDMENT_9_2", "CAPSTONE_FRONTEND_PRODUCT_PROTOCOL_V1_AMENDMENT_9_1", "CAP-005 (historical UI verifier governed for FINAL-EVAL-REPAIR-001)", ("scripts/verify_capstone_ui_v1.py",)),
    (CAP / "CAPSTONE_FEDERATION_UX_PROTOCOL_V1.amendment_5.json", "CAPSTONE_FEDERATION_UX_PROTOCOL_V1_AMENDMENT_5", "CAPSTONE_FEDERATION_UX_PROTOCOL_V1_AMENDMENT_4", "CAP-008 (historical UI verifiers/tests governed for FINAL-EVAL-REPAIR-001)", ("scripts/verify_capstone_ui_v1.py", "scripts/verify_capstone_ui_v1_1.py", "tests/test_capstone_federation_ui.py")),
    (CAP / "CAPSTONE_HISTORY_EVIDENCE_PROTOCOL_V1.amendment_9_5.json", "CAPSTONE_HISTORY_EVIDENCE_PROTOCOL_V1_AMENDMENT_9_5", "CAPSTONE_HISTORY_EVIDENCE_PROTOCOL_V1_AMENDMENT_9_4", "CAP-009 (historical UI verifier governed for FINAL-EVAL-REPAIR-001)", ("scripts/verify_capstone_ui_v1_2.py",)),
    (CAP / "CAPSTONE_FACULTY_DEMO_PROTOCOL_V1.amendment_4.json", "CAPSTONE_FACULTY_DEMO_PROTOCOL_V1_AMENDMENT_4", "CAPSTONE_FACULTY_DEMO_PROTOCOL_V1_AMENDMENT_3", "CAP-010 (historical frontend-drift test governed for FINAL-EVAL-REPAIR-001)", ("tests/test_capstone_full_demo.py",)),
)
UFL = (ROOT / "artifacts/ufl_lite/UFL_LITE_002_PROTOCOL_V1.amendment_1.json", "UFL_LITE_002_PROTOCOL_V1_AMENDMENT_1", None, "UFL-LITE-002 (frozen verifier/test governed for FINAL-EVAL-REPAIR-001)", ("scripts/verify_capstone_ui_v1_4.py", "tests/test_ufl_lite_presentation.py"))


def old_sha(rel: str) -> str:
    import hashlib

    return hashlib.sha256(subprocess.run(["git", "show", f"{lib.ENTRY}:{rel}"], cwd=ROOT, check=True, capture_output=True).stdout).hexdigest()


def write(path: Path, aid: str, prev: str | None, owner: str, files: tuple[str, ...]) -> None:
    doc = {"amendment_id": aid, "change": "Successor awareness only: when the registered CAPSTONE_UI_V1_5 lock exists and chains to CAPSTONE_UI_V1_4 (predecessor sha verified) the current frontend bytes are governed by it; without a V1_5 lock behaviour is byte-identical to before. Unaccounted frontend drift still fails. Historical lock files V1..V1_4 are unchanged. Named with a _ suffix where a numeric amendment would mis-sort lexicographically.",
           "defect": "FINAL-EVAL-REPAIR-001 repairs evaluator-facing frontend presentation (landing, About, legacy-route retirement). The frozen UI-lock chain needs a registered CAPSTONE_UI_V1_5 successor, and the historical UI verifiers / frontend-pin guards must understand it.",
           "files": {rel: {"old_sha256": old_sha(rel), "new_sha256": lib.sha(ROOT / rel)} for rel in files}, "made_after_method_freeze": True, "owner_phase": owner, "reason": "EVALUATOR_PRESENTATION_REPAIR_SUCCESSOR", "result_evidence_committed_with_amendment": False, "scope": "SUCCESSOR_COMPATIBILITY_ONLY"}
    if prev:
        doc["previous_amendment"] = prev
    path.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")


def main() -> None:
    for path, aid, prev, owner, files in SPEC:
        write(path, aid, prev, owner, files)
    write(UFL[0], UFL[1], UFL[2], UFL[3], UFL[4])
    print(json.dumps({"written": [str(p[0].relative_to(ROOT)) for p in (*SPEC, UFL)]}))


if __name__ == "__main__":
    main()
