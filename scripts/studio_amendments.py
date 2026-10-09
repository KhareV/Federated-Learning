# ruff: noqa: E501
"""Generate the additive compatibility amendments that the accepted CAP-005 / CAP-008 amended-lock audits require for the frontend files changed by
NHM_UNIFIED_LIVE_FEDERATION_STUDIO_001 (the same mechanism NHM_FL10_001 used: new ``*.amendment_*.json`` files recording ``old_sha256 -> new_sha256``).

The expected digest of every bound file is replayed from the accepted lock plus every existing amendment (exactly as ``cap_006_protected_audit.verify_amended_lock`` does);
a file whose current bytes differ is recorded as ``old = expected, new = current``. Nothing historical is edited; running it twice is a no-op."""

from __future__ import annotations

import json
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
CAPSTONE = ROOT / "artifacts/capstone"
TARGETS = {
    "CAPSTONE_FRONTEND_PRODUCT_PROTOCOL_V1": ("CAP005_LOCK", "CAPSTONE_FRONTEND_PRODUCT_PROTOCOL_V1.lock.json", "amendment_9_6_1_1_3.json"),
    "CAPSTONE_FEDERATION_UX_PROTOCOL_V1": ("CAP008_LOCK", "CAPSTONE_FEDERATION_UX_PROTOCOL_V1.lock.json", "amendment_9_1_1_3.json"),
}
AMENDMENT_ID = "NHM_UNIFIED_LIVE_FEDERATION_STUDIO_001_SUCCESSOR_COMPATIBILITY"


def expected_digests(protocol: str, lock_name: str, exclude: str) -> dict[str, str]:
    lock = json.loads((CAPSTONE / lock_name).read_text())
    expected = {**lock["bound_files"], **lock.get("upstream_frozen_identity", {})}
    expected.update({c["path"]: c["sha256"] for c in lock.get("components", {}).values()})
    for amendment in sorted(CAPSTONE.glob(f"{protocol}.amendment_*.json")):
        if amendment.name == exclude:
            continue
        data = json.loads(amendment.read_text())
        for path, change in data["files"].items():
            expected[path] = change["new_sha256"]
        expected.update(data.get("added_files", {}))
    return expected


def build() -> dict[str, dict]:
    out = {}
    for protocol, (_, lock_name, suffix) in TARGETS.items():
        name = f"{protocol}.{suffix}"
        expected = expected_digests(protocol, lock_name, name)
        changed = {path: {"old_sha256": digest, "new_sha256": hash_file(ROOT / path)} for path, digest in sorted(expected.items())
                   if path.startswith("frontend/") and (ROOT / path).is_file() and hash_file(ROOT / path) != digest}
        out[name] = {"amendment_id": AMENDMENT_ID, "scope": "SUCCESSOR_COMPATIBILITY_ONLY", "made_after_method_freeze": True, "result_evidence_committed_with_amendment": False,
                     "reason": "The unified Federation Studio adds the Studio client methods, run-scoped stores and components to the product frontend; no frozen frontend product behavior, federation method or historical lock is edited.", "files": changed}
    return out


def main() -> int:
    for name, body in build().items():
        path = CAPSTONE / name
        text = json.dumps(body, indent=1, sort_keys=True) + "\n"
        if body["files"] and (not path.exists() or path.read_text() != text):
            path.write_text(text)
        print(name, len(body["files"]), "files", "written" if body["files"] else "nothing to record")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
