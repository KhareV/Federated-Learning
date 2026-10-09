# ruff: noqa: E501
"""Pure SUCCESSOR_COMPATIBILITY_ONLY amendments registering NHM_UNIFIED_LIVE_FEDERATION_STUDIO_001's governed edits of historically bound files
(frontend files, the three frontend-accounting tests, the legacy route-policy classification). Same mechanism and the same authorised surface as
``scripts/observatory_amend`` (NHM_RESEARCH_OBSERVATORY_V1) and NHM_FL10_001: derived from what changed, refuses any change outside that surface, never modifies a
historical lock or amendment, carries no result evidence. Running it again replaces only this work's own amendments."""

from __future__ import annotations

import json

from scripts import final_eval_repair_lib as lib
from scripts.final_eval_repair_002_amend import expected_map
from scripts.observatory_amend import authorised, lock_files

ROOT = lib.ROOT
PREFIX = "NHM_UNIFIED_LIVE_FEDERATION_STUDIO_001"


def own(path) -> bool:
    return json.loads(path.read_text()).get("amendment_id", "").startswith(PREFIX)


def main() -> dict:
    written: list[str] = []
    for lock_path in lock_files():
        stem = lock_path.name.removesuffix(".lock.json")
        for mine in sorted(p for p in lock_path.parent.glob(f"{stem}.amendment_*.json") if own(p)):
            mine.unlink()                                          # regenerate only this work's own amendment
        expected = expected_map(lock_path)
        changed = {p: h for p, h in expected.items() if (ROOT / p).exists() and lib.sha(ROOT / p) != h}
        if not changed:
            continue
        outside = sorted(p for p in changed if not authorised(p))
        if outside:
            raise RuntimeError(f"STUDIO_OUT_OF_SCOPE:{lock_path.name}:{outside}")
        existing = sorted(lock_path.parent.glob(f"{stem}.amendment_*.json"))           # the chain verifiers apply amendments in LEXICOGRAPHIC order
        prior = existing[-1] if existing else None
        last = prior.name.removesuffix(".json").split(".amendment_")[1] if prior else None
        suffix = f"{last}_1" if last else "1"                                          # 'X_1' sorts after 'X', so this amendment is applied last
        out = lock_path.parent / f"{stem}.amendment_{suffix}.json"
        if out.exists():
            raise RuntimeError(f"STUDIO_AMENDMENT_NAME_TAKEN:{out}")
        doc = {"amendment_id": f"{PREFIX}_{stem}_AMENDMENT_{suffix}", "owner_phase": f"{stem} (historical files governed for {PREFIX})", "scope": "SUCCESSOR_COMPATIBILITY_ONLY", "reason": "UNIFIED_LIVE_FEDERATION_STUDIO_ADDITIVE_SUCCESSOR",
               "defect": f"{PREFIX} extends the product frontend (Studio client methods, run-scoped stores and components) and the federation store, and needs successor awareness in the frontend-accounting tests and the legacy route classification.",
               "change": "Re-pin only the listed frontend files, accounting tests and route-policy classification. Predecessor locks, CAPSTONE_UI_V1_9, NHM_FL10_001 and frozen scientific evidence are unchanged.",
               "made_after_method_freeze": True, "result_evidence_committed_with_amendment": False,
               "files": {p: {"old_sha256": h, "new_sha256": lib.sha(ROOT / p)} for p, h in sorted(changed.items())}}
        if prior:
            doc["previous_amendment"] = prior.name.removesuffix(".json").replace(".amendment_", "_AMENDMENT_")
        out.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        written.append(str(out.relative_to(ROOT)))
    return {"written": written}


if __name__ == "__main__":
    print(json.dumps(main(), indent=1))
