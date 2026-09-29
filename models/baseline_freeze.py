"""F07/BASELINE_V1 freeze-lock verification."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from nhm.hashing import hash_file


class BaselineFreezeError(RuntimeError):
    pass


def verify_baseline_freeze(root: Path, lock_path: Path | None = None) -> dict[str, Any]:
    path = lock_path or root / "manifests/baselines/BASELINE_V1.lock.json"
    if not path.exists():
        raise BaselineFreezeError(f"F07 lock absent: {path}")
    lock = json.loads(path.read_text(encoding="utf-8"))
    if lock.get("freeze_id") != "F07" or lock.get("status") != "FROZEN":
        raise BaselineFreezeError("F07 lock identity/status invalid")
    for relative, expected in lock.get("artifact_sha256", {}).items():
        artifact = root / relative
        if not artifact.exists():
            raise BaselineFreezeError(f"F07 bound artifact absent: {relative}")
        actual = hash_file(artifact)
        if actual != expected:
            raise BaselineFreezeError(
                f"F07_HASH_MISMATCH: {relative}: expected {expected}, got {actual}"
            )
    upstream = lock["upstream_frozen_sha256"]
    for relative, expected in upstream.items():
        if hash_file(root / relative) != expected:
            raise BaselineFreezeError(f"F07_UPSTREAM_MISMATCH: {relative}")
    if lock.get("fit_partition") != "TRAIN" or lock.get("validation_role") != "EVALUATE_ONLY":
        raise BaselineFreezeError("F07 fit/report scope invalid")
    return {
        "status": "PASS",
        "freeze_id": "F07",
        "lock_path": str(path.relative_to(root)),
        "bound_artifact_count": len(lock["artifact_sha256"]),
    }
