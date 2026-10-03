"""Locked EXPLAINABILITY_V2 Integrated Gradients for MODEL_V2_FINAL.

Reuses the generic, model-agnostic EXPLAINABILITY_V1 quadrature/attribution code
(evaluation.explain.integrated_gradients takes the model as a parameter) without altering it,
and adds the V2 identity constants, the strict V2-011 completeness rule, and model-immutability
snapshots. Target is the raw pre-sigmoid scalar logit; CAL_V2 never enters the attribution.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass

import numpy as np
import torch

from evaluation.explain import (
    IG_STEPS,
    gauss_legendre_rule,
    integrated_gradients,
    normalize_absolute_attribution,
)

IG_TARGET_V2 = "MODEL_V2_FINAL_PRE_SIGMOID_LOGIT"
IG_BASELINE_V2 = "ALL_ZERO_NORMALIZED_INPUT"
IG_INTEGRATION_V2 = "GAUSS_LEGENDRE"
COMPLETENESS_ABSOLUTE_THRESHOLD = 1e-3
COMPLETENESS_RELATIVE_THRESHOLD = 1e-3
RELATIVE_DENOMINATOR_FLOOR = 1e-12


@dataclass(frozen=True)
class V2IGResult:
    signed: np.ndarray
    absolute: np.ndarray
    normalized_absolute: np.ndarray
    output: float
    baseline_output: float
    output_difference: float
    attribution_sum: float
    signed_delta: float
    absolute_delta: float
    relative_delta: float
    passed: bool
    max_abs_attribution_index: int


def completeness(
    attribution_sum: float,
    output: float,
    baseline_output: float,
    *,
    absolute_threshold: float = COMPLETENESS_ABSOLUTE_THRESHOLD,
    relative_threshold: float = COMPLETENESS_RELATIVE_THRESHOLD,
) -> dict[str, float | bool]:
    """V2-011 Section 18: strict '<' acceptance on absolute OR relative delta."""
    output_difference = output - baseline_output
    signed_delta = attribution_sum - output_difference
    absolute_delta = abs(signed_delta)
    relative_delta = absolute_delta / max(abs(output_difference), RELATIVE_DENOMINATOR_FLOOR)
    return {
        "output_difference": output_difference,
        "signed_delta": signed_delta,
        "absolute_delta": absolute_delta,
        "relative_delta": relative_delta,
        "passed": bool(absolute_delta < absolute_threshold or relative_delta < relative_threshold),
    }


def explain_window(model: torch.nn.Module, value: torch.Tensor) -> V2IGResult:
    base = integrated_gradients(model, value, steps=IG_STEPS)
    verdict = completeness(base.attribution_sum, base.output, base.baseline_output)
    return V2IGResult(
        signed=base.signed,
        absolute=base.absolute,
        normalized_absolute=base.normalized_absolute,
        output=base.output,
        baseline_output=base.baseline_output,
        output_difference=float(verdict["output_difference"]),
        attribution_sum=base.attribution_sum,
        signed_delta=float(verdict["signed_delta"]),
        absolute_delta=float(verdict["absolute_delta"]),
        relative_delta=float(verdict["relative_delta"]),
        passed=bool(verdict["passed"]),
        max_abs_attribution_index=int(np.argmax(np.abs(base.signed))),
    )


def snapshot_model_state(model: torch.nn.Module) -> dict[str, torch.Tensor]:
    """Deep copy of every parameter AND buffer (BatchNorm running statistics included)."""
    return copy.deepcopy({key: value.detach().clone() for key, value in model.state_dict().items()})


def model_state_unchanged(model: torch.nn.Module, before: dict[str, torch.Tensor]) -> bool:
    after = model.state_dict()
    return set(after) == set(before) and all(torch.equal(before[k], after[k]) for k in before)


__all__ = [
    "IG_BASELINE_V2",
    "IG_INTEGRATION_V2",
    "IG_STEPS",
    "IG_TARGET_V2",
    "V2IGResult",
    "completeness",
    "explain_window",
    "gauss_legendre_rule",
    "model_state_unchanged",
    "normalize_absolute_attribution",
    "snapshot_model_state",
]
