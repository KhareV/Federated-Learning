"""F06/PREPROC_V1 freeze-lock verification."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from nhm.hashing import hash_file


class PreprocFreezeError(RuntimeError):
    pass


def verify_preproc_freeze(root: Path, lock_path: Path | None = None) -> dict[str, Any]:
    lock_path = lock_path or root / "manifests/preprocessing/PREPROC_V1.lock.json"
    if not lock_path.exists():
        raise PreprocFreezeError(f"F06 lock absent: {lock_path}")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if lock.get("freeze_id") != "F06" or lock.get("status") != "FROZEN":
        raise PreprocFreezeError("F06 lock identity/status invalid")
    bound_hashes = {
        **lock.get("artifact_sha256", {}),
        **lock.get("upstream_evidence_sha256", {}),
    }
    for relative_path, expected in bound_hashes.items():
        path = root / relative_path
        if not path.exists():
            raise PreprocFreezeError(f"F06 bound artifact absent: {relative_path}")
        actual = hash_file(path)
        if actual != expected:
            raise PreprocFreezeError(
                f"F06_HASH_MISMATCH: {relative_path}: expected {expected}, got {actual}"
            )

    config = yaml.safe_load((root / "configs/preproc_v1.yaml").read_text(encoding="utf-8"))
    quality = yaml.safe_load((root / "configs/quality_v1.yaml").read_text(encoding="utf-8"))
    semantic = {
        "preproc_id": config["preproc_id"],
        "gap_policy_id": config["gap_policy"]["policy_id"],
        "windowing_id": config["windowing"]["windowing_id"],
        "quality_id": quality["quality_id"],
        "ecg_rate_hz": config["windowing"]["sample_rate_hz"],
        "window_samples": config["windowing"]["window_samples"],
        "stride_samples": config["windowing"]["stride_samples"],
        "signal_interval": config["windowing"]["signal_interval"],
        "annotation_interval": config["windowing"]["annotation_interval"],
        "timestamp_mapping_id": config["resampler"]["timestamp_mapping_id"],
        "resampler_delay_us": int(
            1_000_000
            * config["resampler"]["conversions"]["MITDB_360_TO_250_V1"][
                "group_delay_seconds"
            ]
        ),
        "timestamp_backdating": config["windowing"]["timestamp_backdating"],
        "normalization_id": config["normalization"]["normalization_id"],
        "normalization_epsilon": float(config["normalization"]["epsilon"]),
    }
    expected_semantic = lock["semantic_contract"]
    if semantic != expected_semantic:
        raise PreprocFreezeError(
            f"F06_SEMANTIC_MISMATCH: expected {expected_semantic}, got {semantic}"
        )
    return {
        "status": "PASS",
        "freeze_id": "F06",
        "lock_path": str(lock_path.relative_to(root)),
        "bound_artifact_count": len(bound_hashes),
    }
