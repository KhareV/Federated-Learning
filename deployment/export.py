"""Deterministic MODEL_V1 CPU-gateway FP32 export for T029."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import torch

from models.model_freeze import load_frozen_model_v1
from nhm.hashing import hash_file

ARTIFACT_ID = "GATEWAY_FP32_V1"
INPUT_ID = "GATEWAY_MODEL_INPUT_V1"
FORMAT = "TORCHSCRIPT_SCRIPT"
DEVELOPMENT_ATOL = 1e-5


def _fixture(root: Path) -> tuple[np.ndarray, np.ndarray]:
    with np.load(root / "tests/fixtures/model_v1_test_vector.npz", allow_pickle=False) as data:
        return data["normalized_inputs_float32"], data["expected_logits_float32"]


def build_gateway_artifact(root: Path, output: Path) -> dict[str, Any]:
    """Select the first passing format using F08 and synthetic inputs only."""

    model, metadata = load_frozen_model_v1(root)
    model.eval()
    inputs, expected = _fixture(root)
    scripted = torch.jit.script(model)
    output.parent.mkdir(parents=True, exist_ok=True)
    torch.jit.save(scripted, output)
    reloaded = torch.jit.load(str(output), map_location="cpu").eval()
    synthetic = np.stack(
        [
            np.zeros(2500, dtype=np.float32),
            np.linspace(-1.0, 1.0, 2500, dtype=np.float32),
            np.sin(np.linspace(0.0, 20.0, 2500, dtype=np.float32)),
        ]
    )[:, None, :]
    with torch.inference_mode():
        actual = reloaded(torch.from_numpy(inputs)).cpu().numpy()
        eager_synthetic = model(torch.from_numpy(synthetic)).cpu().numpy()
        deploy_synthetic = reloaded(torch.from_numpy(synthetic)).cpu().numpy()
    f08_delta = float(np.max(np.abs(actual - expected), initial=0.0))
    synthetic_delta = float(np.max(np.abs(eager_synthetic - deploy_synthetic), initial=0.0))
    passed = f08_delta <= DEVELOPMENT_ATOL and synthetic_delta <= DEVELOPMENT_ATOL
    if not passed:
        raise RuntimeError("GATEWAY_SCRIPT_DEVELOPMENT_EQUIVALENCE_FAILURE")
    return {
        "artifact_id": ARTIFACT_ID,
        "input_contract_id": INPUT_ID,
        "format": FORMAT,
        "selection_order": ["torch.jit.script", "torch.jit.trace", "eager"],
        "SCRIPT": "PASS",
        "TRACE": "NOT_ATTEMPTED_FIRST_OPTION_PASSED",
        "EAGER_fallback": False,
        "selection_data": ["F08 test vector", "deterministic synthetic fixtures"],
        "INTERNAL_TEST_used_for_selection": False,
        "source_model_sha256": metadata["checkpoint_sha256"],
        "artifact_path": str(output.relative_to(root)),
        "artifact_sha256": hash_file(output),
        "F08_expected_logits": expected[:, 0].astype(float).tolist(),
        "F08_deployment_logits": actual[:, 0].astype(float).tolist(),
        "F08_maximum_absolute_difference": f08_delta,
        "synthetic_maximum_absolute_difference": synthetic_delta,
        "threshold": DEVELOPMENT_ATOL,
        "status": "PASS",
    }


def write_export_audit(root: Path, output: Path) -> dict[str, Any]:
    result = build_gateway_artifact(root, output)
    path = root / "reports/t029/export_development_audit.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result
