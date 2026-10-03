"""V2-009/CAL_V2 frozen-artifact fail-closed verification. Mirrors evaluation.calibration's
verify_cal_v1 pattern exactly (recompute every hash, never trust the artifact's own status
field, fail closed on any mismatch), bound to MODEL_V2_FINAL instead of MODEL_V1 and extended
with the mandatory status-distinction fields this lineage requires: a CAL_V2 artifact
asserting promotion_eligible=true, operational_lineage != MODEL_V1, or a non-COMPLETED guard
state is treated as tampered.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from models.model_v2_final_freeze import verify_model_v2_final
from nhm.hashing import hash_file
from nhm.model_v2_calibration_guard import read_guard_state

CALIBRATION_ID = "CAL_V2"
CALIBRATION_DOMAIN = "MIT-BIH-v1.0.0"
FIT_PARTITION = "CALIBRATION"
MODEL_ID = "MODEL_V2_FINAL"


class CalV2VerifyError(RuntimeError):
    """Raised when any bound CAL_V2 artifact or semantic invariant differs."""


def load_cal_v2(root: Path, artifact_path: Path | None = None) -> dict[str, Any]:
    path = artifact_path or root / "artifacts/CAL_V2.json"
    return json.loads(path.read_text(encoding="utf-8"))


def verify_cal_v2(root: Path, artifact_path: Path | None = None) -> dict[str, Any]:
    model_verification = verify_model_v2_final(root)

    path = artifact_path or root / "artifacts/CAL_V2.json"
    if not path.exists():
        raise CalV2VerifyError("CAL_V2_MISSING")
    artifact = load_cal_v2(root, path)

    checkpoint_sha = hash_file(root / "checkpoints/MODEL_V2_FINAL.pt")
    manifest_sha = hash_file(root / "checkpoints/MODEL_V2_FINAL.manifest.json")
    frozen_config_sha = hash_file(root / "configs/model_v2_final_frozen.yaml")
    protocol_v3_sha = hash_file(root / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V3.lock.json")
    split_sha = hash_file(root / "manifests/splits/MITDB_SPLIT_V1.csv")
    preproc_sha = hash_file(root / "manifests/preprocessing/PREPROC_V1.lock.json")
    window_manifest_sha = hash_file(root / "manifests/windows/MITDB_WINDOWS_V1.csv")

    guard_state = read_guard_state(root)

    required = {
        "calibration_id": artifact.get("calibration_id") == CALIBRATION_ID,
        "status": artifact.get("status") == "FROZEN",
        "model_id": artifact.get("model_id") == MODEL_ID,
        "fit_partition": artifact.get("fit_partition") == FIT_PARTITION,
        "domain": artifact.get("calibration_domain") == CALIBRATION_DOMAIN,
        "patient_count": isinstance(artifact.get("calibration_patient_count"), int)
        and artifact["calibration_patient_count"] > 0,
        "window_count": isinstance(artifact.get("calibration_window_count"), int)
        and artifact["calibration_window_count"] > 0,
        "temperature_finite_positive": (
            math.isfinite(float(artifact.get("temperature", math.nan)))
            and float(artifact["temperature"]) > 0
        ),
        "threshold_finite_in_range": (
            math.isfinite(float(artifact.get("threshold", math.nan)))
            and 0.0 <= float(artifact["threshold"]) <= 1.0
        ),
        "checkpoint_binding": artifact.get("model_checkpoint_sha256") == checkpoint_sha,
        "manifest_binding": artifact.get("model_manifest_sha256") == manifest_sha,
        "frozen_config_binding": artifact.get("model_frozen_config_sha256") == frozen_config_sha,
        "protocol_v3_binding": artifact.get("protocol_v3_lock_sha256") == protocol_v3_sha,
        "split_binding": artifact.get("split_sha256") == split_sha,
        "preproc_binding": artifact.get("preproc_sha256") == preproc_sha,
        "window_manifest_binding": artifact.get("window_manifest_sha256") == window_manifest_sha,
        "target": artifact.get("target_id") == "AAMI_SVF_WINDOW_V1",
        "map": artifact.get("map_id") == "AAMI_SVF_MAP_V1",
        "threshold_comparator": artifact.get("threshold_comparator") == ">=",
        "threshold_metric": artifact.get("threshold_metric") == "POOLED_CALIBRATION_WINDOW_F1",
        "threshold_tie_policy": (
            artifact.get("threshold_tie_policy") == "HIGHEST_THRESHOLD_AMONG_MAX_F1_V2"
        ),
        "internal_test_sealed": artifact.get("internal_test_accessed") is False,
        "external_sealed": artifact.get("external_data_accessed") is False,
        "operational_lineage": artifact.get("operational_lineage") == "MODEL_V1",
        "runtime_acceptance": artifact.get("runtime_acceptance") == "NOT_EVALUATED",
        "guard_completed": guard_state is not None and guard_state.get("state") == "COMPLETED",
    }
    failed = [name for name, passed in required.items() if not passed]
    if failed:
        raise CalV2VerifyError(f"CAL_V2_SEMANTIC_MISMATCH: {','.join(failed)}")

    for relative, expected in artifact["upstream_sha256"].items():
        if hash_file(root / relative) != expected:
            raise CalV2VerifyError(f"CAL_V2_UPSTREAM_HASH_MISMATCH: {relative}")

    if model_verification["status"] != "PASS":
        raise CalV2VerifyError("CAL_V2_MODEL_V2_FINAL_VERIFICATION_FAILED")

    return {
        "status": "PASS",
        "calibration_id": CALIBRATION_ID,
        "artifact_path": str(path.relative_to(root)),
        "artifact_sha256": hash_file(path),
        "model_v2_final_verification": model_verification,
    }


__all__ = [
    "CALIBRATION_DOMAIN",
    "CALIBRATION_ID",
    "FIT_PARTITION",
    "MODEL_ID",
    "CalV2VerifyError",
    "load_cal_v2",
    "verify_cal_v2",
]
