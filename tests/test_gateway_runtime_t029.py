from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from deployment.runtime import GatewayModelRuntime

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "artifacts/deployment/MODEL_V1_GATEWAY_FP32.ts"


@pytest.fixture
def runtime() -> GatewayModelRuntime:
    if not ARTIFACT.exists():
        pytest.skip("gateway artifact not built yet")
    return GatewayModelRuntime(ROOT, ARTIFACT)


def test_input_validation(runtime: GatewayModelRuntime) -> None:
    valid = np.zeros((1, 1, 2500), dtype=np.float32)
    assert runtime.validate_input(valid).shape == (1, 1, 2500)
    with pytest.raises(TypeError):
        runtime.validate_input(valid.astype(np.float64))
    with pytest.raises(ValueError):
        runtime.validate_input(np.zeros((1, 2500), dtype=np.float32))
    invalid = valid.copy()
    invalid[0, 0, 0] = np.nan
    with pytest.raises(ValueError):
        runtime.validate_input(invalid)
    invalid[0, 0, 0] = np.inf
    with pytest.raises(ValueError):
        runtime.validate_input(invalid)


def test_calibration_and_threshold_identity(runtime: GatewayModelRuntime) -> None:
    calibration = json.loads((ROOT / "artifacts/CAL_V1.json").read_text())
    result = runtime.infer(np.zeros((1, 1, 2500), dtype=np.float32))
    assert result.calibration_id == "CAL_V1"
    assert result.calibration_domain == calibration["calibration_domain"]
    assert result.threshold == calibration["threshold"]
    assert result.model_id == "MODEL_V1"


def test_artifact_reload_f08_identity(runtime: GatewayModelRuntime) -> None:
    second = GatewayModelRuntime(ROOT, ARTIFACT)
    with np.load(ROOT / "tests/fixtures/model_v1_test_vector.npz") as fixture:
        window = fixture["normalized_inputs_float32"][0:1]
    assert runtime.infer(window).raw_logit == second.infer(window).raw_logit
