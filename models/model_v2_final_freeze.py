"""V2-008/MODEL_V2_FINAL frozen-package loading and fail-closed verification.

Mirrors models/model_freeze.py's F08/MODEL_V1 pattern exactly (recompute every hash, never
trust the manifest's own PASS field, fail closed on any mismatch), adapted for the scientific
(non-operational) MODEL_V2_FINAL freeze. Unlike F08, this verifier additionally enforces the
mandatory status-distinction fields from V2-008 Section 7: MODEL_V2_FINAL being FROZEN never
implies operational promotion, so the manifest must always assert
official_validation_promotion_eligible=false and operational_lineage=MODEL_V1 for the
currently-frozen V2-007 result; a manifest asserting otherwise is treated as tampered.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import torch
import yaml

from models.model_v2_architectures import ModelV2TcnMean, count_trainable_parameters
from nhm.hashing import hash_file

MODEL_ID = "MODEL_V2_FINAL"
PARENT_ARCHITECTURE_ID = "MODEL_V2_TCN_MEAN"
EXPECTED_PARAMETER_COUNT = 57553
EXPECTED_RELEASE_SEED = 20260927
EXPECTED_PROMOTION_DECISION = "MODEL_V2_NOT_PROMOTED_RELEASE_CI"
EXPECTED_OPERATIONAL_LINEAGE = "MODEL_V1"
EXPECTED_RUNTIME_ACCEPTANCE = "NOT_EVALUATED"


class ModelV2FinalFreezeError(RuntimeError):
    """Raised when any bound MODEL_V2_FINAL artifact or semantic invariant differs."""


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _verify_hash(root: Path, relative: str, expected: str, label: str) -> None:
    path = root / relative
    if not path.exists():
        raise ModelV2FinalFreezeError(f"{label}_MISSING: {relative}")
    actual = hash_file(path)
    if actual != expected:
        raise ModelV2FinalFreezeError(f"{label}_HASH_MISMATCH: expected {expected}, got {actual}")


def _validate_config(config: dict[str, Any], checkpoint_sha: str) -> None:
    checks = {
        "model_id": config.get("model_id") == MODEL_ID,
        "parent_architecture": config.get("parent_architecture") == PARENT_ARCHITECTURE_ID,
        "schedule_id": config.get("schedule_id") == "CONFIG_V2_TCN_MEAN_ORIGINAL_V1",
        "release_seed": config.get("release_seed") == EXPECTED_RELEASE_SEED,
        "selected_epoch": config.get("selected_epoch") == 5,
        "parameter_count": config.get("parameter_count") == EXPECTED_PARAMETER_COUNT,
        "input_shape": config.get("input_shape") == [1, 2500],
        "target": config.get("target") == "AAMI_SVF_WINDOW_V1",
        "label_map": config.get("label_map") == "AAMI_SVF_MAP_V1",
        "preprocessing": config.get("preprocessing") == "PREPROC_V1",
        "checkpoint_sha": config.get("checkpoint", {}).get("sha256") == checkpoint_sha,
        "calibration_null": config.get("calibration") == "NONE_YET",
        "operating_threshold_null": config.get("operating_threshold") == "NONE_YET",
        "promotion_eligible_false": (
            config.get("official_validation_promotion_eligible") is False
        ),
        "promotion_decision": (
            config.get("official_validation_promotion_decision")
            == EXPECTED_PROMOTION_DECISION
        ),
        "operational_lineage": config.get("operational_lineage") == EXPECTED_OPERATIONAL_LINEAGE,
        "runtime_acceptance": config.get("runtime_acceptance") == EXPECTED_RUNTIME_ACCEPTANCE,
        "scientific_final_frozen": config.get("scientific_final_frozen") is True,
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise ModelV2FinalFreezeError(
            f"MODEL_V2_FINAL_CONFIG_SEMANTIC_MISMATCH: {','.join(failed)}"
        )


def load_model_v2_final(
    root: Path, manifest_path: Path | None = None
) -> tuple[torch.nn.Module, dict[str, Any]]:
    """Verify MODEL_V2_FINAL, then return the canonical model in eval mode and metadata."""
    result = verify_model_v2_final(root, manifest_path=manifest_path, run_inference=False)
    checkpoint_path = root / result["checkpoint_path"]
    payload = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    model = ModelV2TcnMean()
    incompatible = model.load_state_dict(payload["state_dict"], strict=True)
    if incompatible.missing_keys or incompatible.unexpected_keys:
        raise ModelV2FinalFreezeError("MODEL_V2_FINAL_CHECKPOINT_STATE_DICT_MISMATCH")
    model.eval()
    return model, result


def verify_model_v2_final(
    root: Path,
    manifest_path: Path | None = None,
    *,
    run_inference: bool = True,
) -> dict[str, Any]:
    """Recompute hashes and semantics; never trust the manifest PASS field alone."""
    manifest_path = manifest_path or root / "checkpoints/MODEL_V2_FINAL.manifest.json"
    if not manifest_path.exists():
        raise ModelV2FinalFreezeError(f"MODEL_V2_FINAL_MANIFEST_MISSING: {manifest_path}")
    manifest = _read_json(manifest_path)
    if (
        manifest.get("model_id") != MODEL_ID
        or manifest.get("release_seed") != EXPECTED_RELEASE_SEED
        or manifest.get("status") != "FROZEN"
        or manifest.get("architecture_id") != PARENT_ARCHITECTURE_ID
        or manifest.get("promotion_decision") != EXPECTED_PROMOTION_DECISION
        or manifest.get("promotion_eligible") is not False
        or manifest.get("operational_lineage") != EXPECTED_OPERATIONAL_LINEAGE
        or manifest.get("runtime_acceptance") != EXPECTED_RUNTIME_ACCEPTANCE
    ):
        raise ModelV2FinalFreezeError("MODEL_V2_FINAL_MANIFEST_IDENTITY_MISMATCH")

    checkpoint = manifest["checkpoint"]
    config_record = manifest["frozen_config"]
    vector = manifest["test_vector"]
    _verify_hash(root, checkpoint["path"], checkpoint["sha256"], "MODEL_V2_FINAL_CHECKPOINT")
    _verify_hash(root, config_record["path"], config_record["sha256"], "MODEL_V2_FINAL_CONFIG")
    _verify_hash(root, vector["path"], vector["sha256"], "MODEL_V2_FINAL_TEST_VECTOR")
    for relative, expected in manifest["upstream_sha256"].items():
        _verify_hash(root, relative, expected, "MODEL_V2_FINAL_UPSTREAM")

    if checkpoint["sha256"] != manifest["source_checkpoint"]["sha256"]:
        raise ModelV2FinalFreezeError("MODEL_V2_FINAL_SOURCE_IDENTITY_MISMATCH")

    config = yaml.safe_load((root / config_record["path"]).read_text(encoding="utf-8"))
    _validate_config(config, checkpoint["sha256"])

    payload = torch.load(root / checkpoint["path"], map_location="cpu", weights_only=False)
    model = ModelV2TcnMean()
    incompatible = model.load_state_dict(payload["state_dict"], strict=True)
    if incompatible.missing_keys or incompatible.unexpected_keys:
        raise ModelV2FinalFreezeError("MODEL_V2_FINAL_CHECKPOINT_STATE_DICT_MISMATCH")
    if count_trainable_parameters(model) != EXPECTED_PARAMETER_COUNT:
        raise ModelV2FinalFreezeError("MODEL_V2_FINAL_ARCHITECTURE_PARAMETER_MISMATCH")

    maximum_absolute_error = None
    maximum_relative_error = None
    if run_inference:
        with np.load(root / vector["path"], allow_pickle=False) as fixture:
            inputs = fixture["normalized_inputs_float32"]
            expected = fixture["expected_logits_float32"]
        if inputs.shape != (3, 1, 2500) or expected.shape != (3, 1):
            raise ModelV2FinalFreezeError("MODEL_V2_FINAL_TEST_VECTOR_SHAPE_MISMATCH")
        model.eval()
        with torch.inference_mode():
            actual = model(torch.from_numpy(inputs)).cpu().numpy()
        difference = np.abs(actual - expected)
        maximum_absolute_error = float(difference.max(initial=0.0))
        denominator = np.maximum(np.abs(expected), np.finfo(np.float32).tiny)
        maximum_relative_error = float((difference / denominator).max(initial=0.0))
        if not np.allclose(
            actual, expected,
            atol=float(vector["logit_atol"]), rtol=float(vector["logit_rtol"]),
        ):
            raise ModelV2FinalFreezeError("MODEL_V2_FINAL_TEST_VECTOR_LOGIT_MISMATCH")

    return {
        "status": "PASS",
        "model_id": MODEL_ID,
        "checkpoint_path": checkpoint["path"],
        "checkpoint_sha256": checkpoint["sha256"],
        "maximum_absolute_error": maximum_absolute_error,
        "maximum_relative_error": maximum_relative_error,
    }


__all__ = [
    "EXPECTED_OPERATIONAL_LINEAGE",
    "EXPECTED_PARAMETER_COUNT",
    "EXPECTED_PROMOTION_DECISION",
    "EXPECTED_RELEASE_SEED",
    "EXPECTED_RUNTIME_ACCEPTANCE",
    "MODEL_ID",
    "PARENT_ARCHITECTURE_ID",
    "ModelV2FinalFreezeError",
    "load_model_v2_final",
    "verify_model_v2_final",
]
