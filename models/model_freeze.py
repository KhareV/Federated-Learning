"""F08/MODEL_V1 frozen-package loading and fail-closed verification."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import torch
import yaml

from models.ecg_cnn import EXPECTED_TRAINABLE_PARAMETERS, MODEL_ID, build_model_v1
from nhm.hashing import hash_file


class ModelFreezeError(RuntimeError):
    """Raised when any bound F08 artifact or semantic invariant differs."""


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _verify_hash(root: Path, relative: str, expected: str, label: str) -> None:
    path = root / relative
    if not path.exists():
        raise ModelFreezeError(f"{label}_MISSING: {relative}")
    actual = hash_file(path)
    if actual != expected:
        raise ModelFreezeError(f"{label}_HASH_MISMATCH: expected {expected}, got {actual}")


def _validate_config(config: dict[str, Any], checkpoint_sha: str) -> None:
    checks = {
        "model_id": config.get("model_id") == MODEL_ID,
        "freeze_id": config.get("freeze_id") == "F08",
        "status": config.get("status") == "FROZEN",
        "release_seed": config.get("release_seed") == 20260927,
        "input_channels": config.get("input", {}).get("channels") == 1,
        "input_samples": config.get("input", {}).get("samples") == 2500,
        "parameter_count": config.get("architecture", {}).get(
            "expected_trainable_parameters"
        )
        == EXPECTED_TRAINABLE_PARAMETERS,
        "preproc_id": config.get("preproc_id") == "PREPROC_V1",
        "split_id": config.get("split_id") == "MITDB_SPLIT_V1",
        "checkpoint_sha": config.get("checkpoint", {}).get("sha256") == checkpoint_sha,
        "calibration_null": config.get("calibration_id") is None,
        "temperature_null": config.get("temperature") is None,
        "threshold_null": config.get("operating_threshold") is None,
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise ModelFreezeError(f"MODEL_CONFIG_SEMANTIC_MISMATCH: {','.join(failed)}")


def load_frozen_model_v1(
    root: Path, manifest_path: Path | None = None
) -> tuple[torch.nn.Module, dict[str, Any]]:
    """Verify F08, then return the canonical model in eval mode and metadata."""
    result = verify_frozen_model_v1(root, manifest_path=manifest_path, run_inference=False)
    checkpoint_path = root / result["checkpoint_path"]
    payload = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    model = build_model_v1()
    incompatible = model.load_state_dict(payload["state_dict"], strict=True)
    if incompatible.missing_keys or incompatible.unexpected_keys:
        raise ModelFreezeError("MODEL_CHECKPOINT_STATE_DICT_MISMATCH")
    model.eval()
    return model, result


def verify_frozen_model_v1(
    root: Path,
    manifest_path: Path | None = None,
    *,
    run_inference: bool = True,
) -> dict[str, Any]:
    """Recompute hashes and semantics; never trust the manifest PASS field alone."""
    manifest_path = manifest_path or root / "checkpoints/MODEL_V1.manifest.json"
    if not manifest_path.exists():
        raise ModelFreezeError(f"MODEL_MANIFEST_MISSING: {manifest_path}")
    manifest = _read_json(manifest_path)
    if (
        manifest.get("freeze_id") != "F08"
        or manifest.get("gate_id") != "G8"
        or manifest.get("model_id") != MODEL_ID
        or manifest.get("release_seed") != 20260927
        or manifest.get("status") != "FROZEN"
    ):
        raise ModelFreezeError("MODEL_MANIFEST_IDENTITY_MISMATCH")

    checkpoint = manifest["checkpoint"]
    config_record = manifest["frozen_config"]
    vector = manifest["test_vector"]
    freeze_audit = manifest["freeze_audit"]
    _verify_hash(root, checkpoint["path"], checkpoint["sha256"], "MODEL_CHECKPOINT")
    _verify_hash(root, config_record["path"], config_record["sha256"], "MODEL_CONFIG")
    _verify_hash(root, vector["path"], vector["sha256"], "MODEL_TEST_VECTOR")
    _verify_hash(root, freeze_audit["path"], freeze_audit["sha256"], "MODEL_FREEZE_AUDIT")
    for relative, expected in manifest["upstream_sha256"].items():
        _verify_hash(root, relative, expected, "MODEL_UPSTREAM")

    config = yaml.safe_load((root / config_record["path"]).read_text(encoding="utf-8"))
    _validate_config(config, checkpoint["sha256"])
    payload = torch.load(root / checkpoint["path"], map_location="cpu", weights_only=True)
    if (
        payload.get("model_id") != MODEL_ID
        or payload.get("seed") != 20260927
        or payload.get("best_epoch") != manifest["selected_epoch"]
    ):
        raise ModelFreezeError("MODEL_CHECKPOINT_IDENTITY_MISMATCH")
    model = build_model_v1()
    incompatible = model.load_state_dict(payload["state_dict"], strict=True)
    if incompatible.missing_keys or incompatible.unexpected_keys:
        raise ModelFreezeError("MODEL_CHECKPOINT_STATE_DICT_MISMATCH")
    if sum(p.numel() for p in model.parameters() if p.requires_grad) != 13_185:
        raise ModelFreezeError("MODEL_ARCHITECTURE_PARAMETER_MISMATCH")

    maximum_absolute_error = None
    maximum_relative_error = None
    if run_inference:
        with np.load(root / vector["path"], allow_pickle=False) as fixture:
            inputs = fixture["normalized_inputs_float32"]
            expected = fixture["expected_logits_float32"]
        if inputs.shape != (3, 1, 2500) or expected.shape != (3, 1):
            raise ModelFreezeError("MODEL_TEST_VECTOR_SHAPE_MISMATCH")
        model.eval()
        with torch.inference_mode():
            actual = model(torch.from_numpy(inputs)).cpu().numpy()
        difference = np.abs(actual - expected)
        maximum_absolute_error = float(difference.max(initial=0.0))
        denominator = np.maximum(np.abs(expected), np.finfo(np.float32).tiny)
        maximum_relative_error = float((difference / denominator).max(initial=0.0))
        if not np.allclose(
            actual,
            expected,
            atol=float(vector["logit_atol"]),
            rtol=float(vector["logit_rtol"]),
        ):
            raise ModelFreezeError("MODEL_TEST_VECTOR_LOGIT_MISMATCH")

    return {
        "status": "PASS",
        "freeze_id": "F08",
        "checkpoint_path": checkpoint["path"],
        "checkpoint_sha256": checkpoint["sha256"],
        "maximum_absolute_error": maximum_absolute_error,
        "maximum_relative_error": maximum_relative_error,
    }
