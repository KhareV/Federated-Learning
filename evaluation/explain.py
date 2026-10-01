"""Locked EXPLAINABILITY_V1 Integrated Gradients implementation."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import torch
from numpy.polynomial.legendre import leggauss

IG_STEPS = 64
IG_TARGET = "MODEL_V1_PRE_SIGMOID_LOGIT"
IG_BASELINE = "ZERO_NORMALIZED_INPUT"


@dataclass(frozen=True)
class IGResult:
    signed: np.ndarray
    absolute: np.ndarray
    normalized_absolute: np.ndarray
    output: float
    baseline_output: float
    attribution_sum: float
    signed_delta: float
    absolute_delta: float
    relative_delta: float
    passed: bool


def gauss_legendre_rule(steps: int = IG_STEPS) -> tuple[np.ndarray, np.ndarray]:
    """Return Gauss-Legendre nodes and weights mapped exactly from [-1, 1] to [0, 1]."""
    if steps != IG_STEPS:
        raise ValueError("EXPLAINABILITY_V1 requires exactly 64 Gauss-Legendre points")
    nodes, weights = leggauss(steps)
    return (nodes + 1.0) / 2.0, weights / 2.0


def normalize_absolute_attribution(signed: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    absolute = np.abs(np.asarray(signed, dtype=np.float64))
    maximum = float(absolute.max(initial=0.0))
    normalized = absolute / maximum if maximum > 0.0 else np.zeros_like(absolute)
    return absolute, normalized


def integrated_gradients(
    model: torch.nn.Module,
    value: torch.Tensor,
    *,
    steps: int = IG_STEPS,
) -> IGResult:
    """Explain the scalar pre-sigmoid MODEL_V1 logit from an exact zero baseline."""
    if value.shape != (1, 1, 2500) or not value.is_floating_point():
        raise ValueError("IG input must be one floating [1,1,2500] normalized model window")
    model.eval()
    baseline = torch.zeros_like(value)
    if torch.count_nonzero(baseline).item() != 0:
        raise RuntimeError("IG baseline must be exact zero")
    nodes, weights = gauss_legendre_rule(steps)
    accumulated = torch.zeros_like(value)
    for alpha, weight in zip(nodes, weights, strict=True):
        interpolated = (baseline + float(alpha) * (value - baseline)).detach()
        interpolated.requires_grad_(True)
        output = model(interpolated).reshape(-1)
        if output.numel() != 1:
            raise ValueError("IG target must be one raw scalar logit")
        gradient = torch.autograd.grad(output[0], interpolated)[0]
        accumulated += float(weight) * gradient.detach()
    signed_tensor = (value - baseline) * accumulated
    signed = signed_tensor.detach().cpu().numpy().reshape(-1).astype(np.float64)
    with torch.inference_mode():
        output_value = float(model(value).reshape(-1)[0].item())
        baseline_value = float(model(baseline).reshape(-1)[0].item())
    output_difference = output_value - baseline_value
    attribution_sum = float(np.sum(signed, dtype=np.float64))
    signed_delta = attribution_sum - output_difference
    absolute_delta = abs(signed_delta)
    relative_delta = absolute_delta / max(abs(output_difference), 1e-12)
    absolute, normalized = normalize_absolute_attribution(signed)
    return IGResult(
        signed=signed,
        absolute=absolute,
        normalized_absolute=normalized,
        output=output_value,
        baseline_output=baseline_value,
        attribution_sum=attribution_sum,
        signed_delta=signed_delta,
        absolute_delta=absolute_delta,
        relative_delta=relative_delta,
        passed=absolute_delta <= 1e-3 or relative_delta <= 1e-3,
    )
