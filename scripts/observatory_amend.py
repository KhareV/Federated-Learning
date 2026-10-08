# ruff: noqa: E501
"""Pure SUCCESSOR_COMPATIBILITY_ONLY amendments that register NHM_RESEARCH_OBSERVATORY_V1's governed edits of historically bound files
(successor-aware UI verifiers/resolver, route-policy classification, accounting tests, minimal copy compatibility in two presentation pages).
Derived from what changed; refuses any change outside the authorised surface; historical lock files are never modified; no result evidence."""

from __future__ import annotations

import json
import re

from scripts import final_eval_repair_lib as lib
from scripts.final_eval_repair_002_amend import expected_map

ROOT = lib.ROOT
ACCOUNTING_TESTS = {"tests/test_capstone_federation_ui.py", "tests/test_capstone_full_demo.py", "tests/test_ufl_lite_presentation.py"}
EXTRA = {"scripts/capstone_ui_v1_8_successor.py", "configs/final_eval_repair/legacy_route_policy_v1.json"}


def authorised(path: str) -> bool:
    return (path.startswith("frontend/") or re.fullmatch(r"scripts/verify_capstone_ui_v1(?:_\d)?\.py", path) is not None
            or path in ACCOUNTING_TESTS or path in EXTRA)


def lock_files() -> list:
    found = []
    for path in sorted(ROOT.glob("artifacts/**/*.lock.json")):
        name = path.name
        if "CAPSTONE_UI_V1" in name or name.startswith(("NHM_RESEARCH_OBSERVATORY", "CLERK_LIVE")):
            continue
        try:
            expected_map(path)
        except (KeyError, TypeError, ValueError):
            continue
        found.append(path)
    return found


def main() -> None:
    written: list[str] = []
    for lock_path in lock_files():
        expected = expected_map(lock_path)
        changed = {p: h for p, h in expected.items() if (ROOT / p).exists() and lib.sha(ROOT / p) != h}
        if not changed:
            continue
        outside = sorted(p for p in changed if not authorised(p))
        if outside:
            raise RuntimeError(f"OBSERVATORY_OUT_OF_SCOPE:{lock_path.name}:{outside}")
        stem = lock_path.name.removesuffix(".lock.json")
        existing = sorted(lock_path.parent.glob(f"{stem}.amendment_*.json"))   # the chain verifiers apply amendments in LEXICOGRAPHIC order
        prior = existing[-1] if existing else None
        last = prior.name.removesuffix(".json").split(".amendment_")[1] if prior else None
        suffix = f"{last}_1" if last else "1"      # 'X_1' sorts after 'X', so this amendment is applied last
        out = lock_path.parent / f"{stem}.amendment_{suffix}.json"
        if out.exists():
            raise RuntimeError(f"OBSERVATORY_AMENDMENT_ALREADY_EXISTS:{out}")
        doc = {"amendment_id": f"{stem}_AMENDMENT_{suffix}", "owner_phase": f"{stem} (historical files governed for NHM_RESEARCH_OBSERVATORY_V1)",
               "scope": "SUCCESSOR_COMPATIBILITY_ONLY", "reason": "RESEARCH_OBSERVATORY_ADDITIVE_SUCCESSOR",
               "defect": "NHM_RESEARCH_OBSERVATORY_V1 adds read-only Observatory frontend routes and needs successor awareness in historical UI verifiers, route classification and frontend-drift accounting.",
               "change": "Re-pin only the listed successor-aware verifier/resolver/route-policy/accounting-test/presentation files. Predecessor locks, CAPSTONE_UI_V1_9 and frozen scientific evidence are unchanged.",
               "made_after_method_freeze": True, "result_evidence_committed_with_amendment": False,
               "files": {p: {"old_sha256": h, "new_sha256": lib.sha(ROOT / p)} for p, h in sorted(changed.items())}}
        if prior:
            doc["previous_amendment"] = f"{stem}_AMENDMENT_{last}"
        out.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        written.append(str(out.relative_to(ROOT)))
    print(json.dumps({"written": written}, indent=1))


if __name__ == "__main__":
    main()
