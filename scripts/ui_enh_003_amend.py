"""Generate pure, narrow CAPSTONE_UI_V1_9 successor-compatibility amendments."""

from __future__ import annotations

import json

from scripts import final_eval_repair_lib as lib
from scripts.final_eval_repair_002_amend import expected_map
from scripts.ui_enh_002_amend import LOCKS, amendment_number, authorised


def main() -> None:
    written: list[str] = []
    for lock_path in LOCKS:
        if not lock_path.exists():
            continue
        expected = expected_map(lock_path)
        changed = {
            path: digest for path, digest in expected.items()
            if (lib.ROOT / path).exists() and lib.sha(lib.ROOT / path) != digest
        }
        if not changed:
            continue
        outside = sorted(path for path in changed if not authorised(path))
        if outside:
            raise RuntimeError(f"UI_ENH_003_OUT_OF_SCOPE:{lock_path.name}:{outside}")
        stem = lock_path.name.removesuffix(".lock.json")
        prior = max(lock_path.parent.glob(f"{stem}.amendment_*.json"),
                    key=amendment_number, default=None)
        old_num = amendment_number(prior) if prior else ()
        new_num = (*old_num[:-1], old_num[-1] + 1) if old_num else (1,)
        suffix = "_".join(map(str, new_num))
        out = lock_path.parent / f"{stem}.amendment_{suffix}.json"
        if out.exists():
            raise RuntimeError(f"UI_ENH_003_AMENDMENT_ALREADY_EXISTS:{out}")
        doc = {
            "amendment_id": f"{stem}_AMENDMENT_{suffix}",
            "previous_amendment": (
                f"{stem}_AMENDMENT_{'_'.join(map(str, old_num))}" if prior else None
            ),
            "owner_phase": f"{stem} (historical files governed for UI-ENH-003)",
            "scope": "SUCCESSOR_COMPATIBILITY_ONLY",
            "reason": "FINAL_UI_POLISH_AND_BUG_FIX_SUCCESSOR",
            "defect": (
                "UI-ENH-003 changes governed frontend presentation and requires "
                "CAPSTONE_UI_V1_9 successor awareness in historical verifiers."
            ),
            "change": (
                "Re-pin only the listed presentation/verifier/accounting-test files to "
                "the CAPSTONE_UI_V1_9-governed bytes. Predecessor locks and frozen "
                "scientific evidence remain unchanged."
            ),
            "made_after_method_freeze": True,
            "result_evidence_committed_with_amendment": False,
            "files": {path: {"old_sha256": digest, "new_sha256": lib.sha(lib.ROOT / path)}
                      for path, digest in sorted(changed.items())},
        }
        if prior is None:
            doc.pop("previous_amendment")
        out.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        written.append(str(out.relative_to(lib.ROOT)))
    print(json.dumps({"written": written}, indent=1))


if __name__ == "__main__":
    main()
