"""Generate pure successor-compatibility amendments for UI-ENH-002.

Only previously bound frontend presentation, UI verifiers, and frontend-drift
accounting tests may change. Existing frozen evidence and amendments are never
rewritten. Result evidence is intentionally excluded from these files.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from scripts import final_eval_repair_lib as lib
from scripts.final_eval_repair_002_amend import expected_map

ROOT = lib.ROOT
CAP = ROOT / "artifacts/capstone"
LOCKS = (
    CAP / "CAPSTONE_FRONTEND_PRODUCT_PROTOCOL_V1.lock.json",
    CAP / "CAPSTONE_FEDERATION_UX_PROTOCOL_V1.lock.json",
    CAP / "CAPSTONE_HISTORY_EVIDENCE_PROTOCOL_V1.lock.json",
    CAP / "CAPSTONE_FACULTY_DEMO_PROTOCOL_V1.lock.json",
    ROOT / "artifacts/ufl_lite/UFL_LITE_002_PROTOCOL_V1.lock.json",
    ROOT / "artifacts/ufl_lite/UFL_LITE_003_PROTOCOL_V1.lock.json",
    ROOT / "artifacts/final_eval_repair/FINAL_EVAL_REPAIR_001_PROTOCOL_V1.lock.json",
    ROOT / "artifacts/final_eval_repair/FINAL_EVAL_REPAIR_002_PROTOCOL_V1.lock.json",
)
ACCOUNTING_TESTS = {
    "tests/test_capstone_federation_ui.py",
    "tests/test_capstone_full_demo.py",
    "tests/test_ufl_lite_presentation.py",
}


def authorised(path: str) -> bool:
    return (
        path.startswith("frontend/")
        or re.fullmatch(r"scripts/verify_capstone_ui_v1(?:_\d)?\.py", path) is not None
        or path in ACCOUNTING_TESTS
    )


def amendment_number(path: Path) -> tuple[int, ...]:
    suffix = path.stem.split(".amendment_", 1)[1]
    return tuple(int(part) for part in suffix.split("_"))


def main() -> None:
    written: list[str] = []
    for lock_path in LOCKS:
        if not lock_path.exists():
            continue
        expected = expected_map(lock_path)
        changed = {
            path: digest for path, digest in expected.items()
            if (ROOT / path).exists() and lib.sha(ROOT / path) != digest
        }
        if not changed:
            continue
        outside = sorted(path for path in changed if not authorised(path))
        if outside:
            raise RuntimeError(f"UI_ENH_002_OUT_OF_SCOPE:{lock_path.name}:{outside}")
        stem = lock_path.name.removesuffix(".lock.json")
        prior = max(lock_path.parent.glob(f"{stem}.amendment_*.json"),
                    key=amendment_number, default=None)
        old_num = amendment_number(prior) if prior else ()
        new_num = (*old_num[:-1], old_num[-1] + 1) if old_num else (1,)
        suffix = "_".join(map(str, new_num))
        out = lock_path.parent / f"{stem}.amendment_{suffix}.json"
        if out.exists():
            raise RuntimeError(f"UI_ENH_002_AMENDMENT_ALREADY_EXISTS:{out}")
        doc = {
            "amendment_id": f"{stem}_AMENDMENT_{suffix}",
            "previous_amendment": (
                f"{stem}_AMENDMENT_{'_'.join(map(str, old_num))}" if prior else None
            ),
            "owner_phase": f"{stem} (historical files governed for UI-ENH-002)",
            "scope": "SUCCESSOR_COMPATIBILITY_ONLY",
            "reason": "PRODUCT_STORY_COMPARISON_AND_RESEARCH_VISUALIZATION_SUCCESSOR",
            "defect": (
                "UI-ENH-002 changes governed frontend presentation and requires "
                "CAPSTONE_UI_V1_8 successor awareness in historical verifiers."
            ),
            "change": (
                "Re-pin only the listed presentation/verifier/accounting-test files to "
                "the CAPSTONE_UI_V1_8-governed bytes. Predecessor locks and frozen "
                "scientific evidence remain unchanged."
            ),
            "made_after_method_freeze": True,
            "result_evidence_committed_with_amendment": False,
            "files": {path: {"old_sha256": digest, "new_sha256": lib.sha(ROOT / path)}
                      for path, digest in sorted(changed.items())},
        }
        if prior is None:
            doc.pop("previous_amendment")
        out.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        written.append(str(out.relative_to(ROOT)))
    print(json.dumps({"written": written}, indent=1))


if __name__ == "__main__":
    main()
