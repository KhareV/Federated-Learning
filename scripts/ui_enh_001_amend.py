# ruff: noqa: E501
"""Write the pure SUCCESSOR_COMPATIBILITY_ONLY amendments that register UI-ENH-001's governed edits (Federation visualization/UX frontend files, successor-aware UI verifiers, frontend-delta accounting tests).
Derived from what actually changed: for every frozen method lock the files whose current SHA differs from the lock's expected SHA (after earlier amendments) are recorded old->new.
Refuses any changed file outside the authorised surface (frontend/**, scripts/verify_capstone_ui_v1*.py, the three frontend-delta accounting tests). Facts only; no result evidence."""

from __future__ import annotations

import json
import re
from pathlib import Path

from scripts import final_eval_repair_lib as lib
from scripts.final_eval_repair_002_amend import CAP, expected_map

ROOT = lib.ROOT
ACCOUNTING_TESTS = {"tests/test_capstone_federation_ui.py", "tests/test_capstone_full_demo.py", "tests/test_ufl_lite_presentation.py"}
FER = ROOT / "artifacts/final_eval_repair"
LOCKS = (
    (CAP / "CAPSTONE_FRONTEND_PRODUCT_PROTOCOL_V1.lock.json", "CAP-005"),
    (CAP / "CAPSTONE_FEDERATION_UX_PROTOCOL_V1.lock.json", "CAP-008"),
    (CAP / "CAPSTONE_HISTORY_EVIDENCE_PROTOCOL_V1.lock.json", "CAP-009"),
    (CAP / "CAPSTONE_FACULTY_DEMO_PROTOCOL_V1.lock.json", "CAP-010"),
    (ROOT / "artifacts/ufl_lite/UFL_LITE_002_PROTOCOL_V1.lock.json", "UFL-LITE-002"),
    (ROOT / "artifacts/ufl_lite/UFL_LITE_003_PROTOCOL_V1.lock.json", "UFL-LITE-003"),
    (FER / "FINAL_EVAL_REPAIR_001_PROTOCOL_V1.lock.json", "FINAL-EVAL-REPAIR-001"),
    (FER / "FINAL_EVAL_REPAIR_002_PROTOCOL_V1.lock.json", "FINAL-EVAL-REPAIR-002"),
)


def authorised(path: str) -> bool:
    return path.startswith("frontend/") or re.fullmatch(r"scripts/verify_capstone_ui_v1(_\d)?\.py", path) is not None or path in ACCOUNTING_TESTS


def next_id(lock_path: Path) -> tuple[str, str | None]:
    stem = lock_path.name.replace(".lock.json", "")
    names = sorted(a.name for a in lock_path.parent.glob(f"{stem}.amendment_*.json") if "UI_ENH" not in a.read_text()[:400])
    if not names:
        return f"{stem}_AMENDMENT_1", None
    last = names[-1].split("amendment_")[1].removesuffix(".json")
    prev = f"{stem}_AMENDMENT_{last.upper()}"
    parts = last.split("_")
    new = f"9_{int(parts[1]) + 1}" if len(parts) == 2 and parts[0] == "9" else str(int(parts[0]) + 1)
    return f"{stem}_AMENDMENT_{new.upper()}", prev


def main() -> None:
    written = []
    for lock_path, owner in LOCKS:
        if not lock_path.exists():
            continue
        exp = expected_map(lock_path)
        changed = {p: h for p, h in exp.items() if (ROOT / p).exists() and lib.sha(ROOT / p) != h}
        if not changed:
            continue
        outside = sorted(p for p in changed if not authorised(p))
        if outside:
            raise SystemExit(f"CHANGED_OUTSIDE_AUTHORISED_SURFACE:{lock_path.name}:{outside}")
        aid, prev = next_id(lock_path)
        out = lock_path.parent / (lock_path.name.replace(".lock.json", "") + ".amendment_" + aid.split("_AMENDMENT_")[1].lower() + ".json")
        doc = {"amendment_id": aid, "change": "Successor awareness / governed presentation edit only: files whose bytes changed under UI-ENH-001 (Federation visualization and UX, CAPSTONE_UI_V1_7 successor awareness) are re-pinned old->new. Historical lock files V1..V1_6 are unchanged; without a V1_7 lock the verifiers behave byte-identically to before.",
               "defect": "UI-ENH-001 redesigns the Federation presentation (visual implementation and UX only). The frozen UI-lock chain needs a registered CAPSTONE_UI_V1_7 successor and the frozen method locks must follow the governed file changes.",
               "files": {p: {"old_sha256": h, "new_sha256": lib.sha(ROOT / p)} for p, h in sorted(changed.items())}, "made_after_method_freeze": True, "owner_phase": f"{owner} (frozen files governed for UI-ENH-001)", "reason": "FEDERATION_VISUALIZATION_AND_UX_SUCCESSOR", "result_evidence_committed_with_amendment": False, "scope": "SUCCESSOR_COMPATIBILITY_ONLY"}
        if prev:
            doc["previous_amendment"] = prev
        out.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")
        written.append(str(out.relative_to(ROOT)))
    print(json.dumps({"written": written}, indent=1))


if __name__ == "__main__":
    main()
