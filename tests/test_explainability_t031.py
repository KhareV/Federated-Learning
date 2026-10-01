from __future__ import annotations

import numpy as np
import pytest
import torch

from evaluation.explain import gauss_legendre_rule, integrated_gradients


class LinearModel(torch.nn.Module):
    def __init__(self, weights: torch.Tensor) -> None:
        super().__init__()
        self.register_buffer("weights", weights)

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        return (value * self.weights).sum(dim=(1, 2))


def test_gauss_legendre_mapping_and_analytic_linear_ig() -> None:
    nodes, weights = gauss_legendre_rule()
    assert len(nodes) == len(weights) == 64
    assert np.all((nodes > 0) & (nodes < 1))
    assert float(weights.sum()) == pytest.approx(1.0, abs=1e-14)
    value = torch.linspace(-1, 1, 2500, dtype=torch.float32).reshape(1, 1, -1)
    model = LinearModel(torch.linspace(0.1, 1.0, 2500).reshape(1, 1, -1))
    result = integrated_gradients(model, value)
    expected = (value * model.weights).numpy().reshape(-1)
    assert np.allclose(result.signed, expected, atol=2e-6)
    assert result.absolute_delta <= 1e-3
    assert result.passed
    assert not model.training


def test_zero_baseline_raw_logit_and_per_window_normalization() -> None:
    value = torch.ones((1, 1, 2500), dtype=torch.float32)
    model = LinearModel(torch.full_like(value, 0.001))
    result = integrated_gradients(model, value)
    assert result.baseline_output == 0.0
    assert result.output == pytest.approx(float(model(value).item()))
    assert result.normalized_absolute.max() == pytest.approx(1.0)
    assert np.any(result.signed != 0)


def test_locked_step_count_and_input_contract() -> None:
    with pytest.raises(ValueError, match="64"):
        gauss_legendre_rule(32)
    with pytest.raises(ValueError, match="2500"):
        integrated_gradients(LinearModel(torch.ones((1, 1, 10))), torch.ones((1, 1, 10)))
