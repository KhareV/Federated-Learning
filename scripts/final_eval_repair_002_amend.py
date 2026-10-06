# ruff: noqa: E501
"""Write the pure SUCCESSOR_COMPATIBILITY_ONLY amendments that register FINAL-EVAL-REPAIR-002's successor-aware edits (and its landing-surface edits) of historically bound files.
Derived from what actually changed: for every frozen method lock the files whose current SHA differs from the lock's expected SHA (after earlier amendments) are recorded old->new.
Refuses any changed file outside the authorised surface. Facts only; no result evidence. Historical lock files are never modified."""

from __future__ import annotations

import json
from pathlib import Path

from scripts import final_eval_repair_lib as lib

ROOT = lib.ROOT
CAP = ROOT / "artifacts/capstone"
SURFACE = json.loads((ROOT / "configs/final_eval_repair/fer_002_authorised_surface_v1.json").read_text())
AUTH = set(SURFACE["authorised_modifications"])
# (lock file, amendment file name, amendment id, previous amendment id, owner)
TARGETS = (
    (CAP / "CAPSTONE_FRONTEND_PRODUCT_PROTOCOL_V1.lock.json", "CAPSTONE_FRONTEND_PRODUCT_PROTOCOL_V1.amendment_9_3.json", "CAPSTONE_FRONTEND_PRODUCT_PROTOCOL_V1_AMENDMENT_9_3", "CAPSTONE_FRONTEND_PRODUCT_PROTOCOL_V1_AMENDMENT_9_2", "CAP-005 (historical UI verifier governed for FINAL-EVAL-REPAIR-002)"),
    (CAP / "CAPSTONE_FEDERATION_UX_PROTOCOL_V1.lock.json", "CAPSTONE_FEDERATION_UX_PROTOCOL_V1.amendment_6.json", "CAPSTONE_FEDERATION_UX_PROTOCOL_V1_AMENDMENT_6", "CAPSTONE_FEDERATION_UX_PROTOCOL_V1_AMENDMENT_5", "CAP-008 (historical UI verifiers/tests governed for FINAL-EVAL-REPAIR-002)"),
    (CAP / "CAPSTONE_HISTORY_EVIDENCE_PROTOCOL_V1.lock.json", "CAPSTONE_HISTORY_EVIDENCE_PROTOCOL_V1.amendment_9_6.json", "CAPSTONE_HISTORY_EVIDENCE_PROTOCOL_V1_AMENDMENT_9_6", "CAPSTONE_HISTORY_EVIDENCE_PROTOCOL_V1_AMENDMENT_9_5", "CAP-009 (historical UI verifier governed for FINAL-EVAL-REPAIR-002)"),
    (CAP / "CAPSTONE_FACULTY_DEMO_PROTOCOL_V1.lock.json", "CAPSTONE_FACULTY_DEMO_PROTOCOL_V1.amendment_5.json", "CAPSTONE_FACULTY_DEMO_PROTOCOL_V1_AMENDMENT_5", "CAPSTONE_FACULTY_DEMO_PROTOCOL_V1_AMENDMENT_4", "CAP-010 (historical frontend-drift test governed for FINAL-EVAL-REPAIR-002)"),
    (ROOT / "artifacts/ufl_lite/UFL_LITE_002_PROTOCOL_V1.lock.json", "UFL_LITE_002_PROTOCOL_V1.amendment_2.json", "UFL_LITE_002_PROTOCOL_V1_AMENDMENT_2", "UFL_LITE_002_PROTOCOL_V1_AMENDMENT_1", "UFL-LITE-002 (frozen verifier/test/UI file governed for FINAL-EVAL-REPAIR-002)"),
    (ROOT / "artifacts/ufl_lite/UFL_LITE_003_PROTOCOL_V1.lock.json", "UFL_LITE_003_PROTOCOL_V1.amendment_1.json", "UFL_LITE_003_PROTOCOL_V1_AMENDMENT_1", None, "UFL-LITE-003 (frozen UI file governed for FINAL-EVAL-REPAIR-002)"),
    (ROOT / "artifacts/final_eval_repair/FINAL_EVAL_REPAIR_001_PROTOCOL_V1.lock.json", "FINAL_EVAL_REPAIR_001_PROTOCOL_V1.amendment_1.json", "FINAL_EVAL_REPAIR_001_PROTOCOL_V1_AMENDMENT_1", None, "FINAL-EVAL-REPAIR-001 (frozen landing/UI/verifier files governed for FINAL-EVAL-REPAIR-002)"),
)


def expected_map(lock_path: Path) -> dict[str, str]:
    lock = json.loads(lock_path.read_text())
    expected = dict(lock["bound_files"])
    expected.update(lock.get("upstream_frozen_identity", {}))
    expected.update({c["path"]: c["sha256"] for c in lock.get("components", {}).values()})
    stem = lock_path.name.replace(".lock.json", "")
    for a in sorted(lock_path.parent.glob(f"{stem}.amendment_*.json")):
        data = json.loads(a.read_text())
        for path, ch in data["files"].items():
            expected[path] = ch["new_sha256"]
        expected.update(data.get("added_files", {}))
    return expected


def main() -> None:
    written = []
    for lock_path, fname, aid, prev, owner in TARGETS:
        out = lock_path.parent / fname
        if not lock_path.exists():
            continue
        exp = expected_map(lock_path)
        if out.exists():
            out.unlink()
            exp = expected_map(lock_path)
        changed = {p: h for p, h in exp.items() if (ROOT / p).exists() and lib.sha(ROOT / p) != h}
        if not changed:
            continue
        outside = sorted(p for p in changed if p not in AUTH)
        if outside:
            raise SystemExit(f"CHANGED_OUTSIDE_AUTHORISED_SURFACE:{lock_path.name}:{outside}")
        doc = {"amendment_id": aid, "change": "Successor awareness / governed presentation edit only: files whose bytes changed under FINAL-EVAL-REPAIR-002 (public landing presentation, accessibility, CAPSTONE_UI_V1_6 successor awareness) are re-pinned old->new. Historical lock files V1..V1_5 are unchanged; without a V1_6 lock the verifiers behave byte-identically to before.",
               "defect": "FINAL-EVAL-REPAIR-002 repairs the public landing presentation (second final audit F2-01..F2-03). The frozen UI-lock chain needs a registered CAPSTONE_UI_V1_6 successor and the frozen method locks must follow the governed file changes.",
               "files": {p: {"old_sha256": h, "new_sha256": lib.sha(ROOT / p)} for p, h in sorted(changed.items())}, "made_after_method_freeze": True, "owner_phase": owner, "reason": "FINAL_PUBLIC_PRESENTATION_REPAIR_SUCCESSOR", "result_evidence_committed_with_amendment": False, "scope": "SUCCESSOR_COMPATIBILITY_ONLY"}
        if prev:
            doc["previous_amendment"] = prev
        out.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")
        written.append(str(out.relative_to(ROOT)))
    print(json.dumps({"written": written}))


if __name__ == "__main__":
    main()
