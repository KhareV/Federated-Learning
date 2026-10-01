"""Frozen CPU gateway runtime for MODEL_V1 and CAL_V1."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch

from nhm.hashing import hash_file


@dataclass(frozen=True)
class GatewayInferenceResult:
    model_id: str
    model_sha: str
    deployment_artifact_id: str
    deployment_artifact_sha: str
    calibration_id: str
    raw_logit: float
    calibrated_probability: float
    threshold: float
    above_threshold: bool
    calibration_domain: str
    inference_time_ms: float | None = None


class GatewayModelRuntime:
    """Strict batch-one CPU runtime; preprocessing remains upstream."""

    def __init__(self, root: Path, artifact_path: Path) -> None:
        self.root = root
        self.artifact_path = artifact_path
        self.calibration = json.loads((root / "artifacts/CAL_V1.json").read_text())
        self.model = torch.jit.load(str(artifact_path), map_location="cpu").eval()
        self.artifact_sha = hash_file(artifact_path)
        self.model_sha = hash_file(root / "checkpoints/MODEL_V1.pt")

    @staticmethod
    def validate_input(window: np.ndarray) -> np.ndarray:
        array = np.asarray(window)
        if array.dtype != np.float32:
            raise TypeError("GATEWAY_MODEL_INPUT_V1 requires float32")
        if array.shape != (1, 1, 2500):
            raise ValueError("GATEWAY_MODEL_INPUT_V1 requires shape [1,1,2500]")
        if not np.isfinite(array).all():
            raise ValueError("GATEWAY_MODEL_INPUT_V1 requires finite values")
        return np.ascontiguousarray(array)

    def infer(self, window: np.ndarray) -> GatewayInferenceResult:
        array = self.validate_input(window)
        with torch.inference_mode():
            logit = float(self.model(torch.from_numpy(array)).cpu().numpy()[0, 0])
        if not math.isfinite(logit):
            raise RuntimeError("nonfinite gateway logit")
        temperature = float(self.calibration["temperature"])
        scaled = logit / temperature
        probability = 1.0 / (1.0 + math.exp(-scaled))
        threshold = float(self.calibration["threshold"])
        return GatewayInferenceResult(
            model_id="MODEL_V1",
            model_sha=self.model_sha,
            deployment_artifact_id="GATEWAY_FP32_V1",
            deployment_artifact_sha=self.artifact_sha,
            calibration_id="CAL_V1",
            raw_logit=logit,
            calibrated_probability=probability,
            threshold=threshold,
            above_threshold=probability >= threshold,
            calibration_domain=str(self.calibration["calibration_domain"]),
        )
