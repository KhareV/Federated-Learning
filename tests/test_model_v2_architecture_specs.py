"""V2-001 architecture pre-registration tests (Sections 8E/13).

Only minimal synthetic shape/parameter-count instantiation is performed here -- these
architectures are never trained on real patient data in V2-001. Proves: raw-logit output
contract (no sigmoid, shape (batch, 1)), the TCN parameter cap, and the TCN's analytic
receptive field >= 2500 samples.
"""

from __future__ import annotations

import torch

from models.model_v2_architectures import (
    TCN_PARAMETER_CAP,
    ModelV2CapCtrl,
    ModelV2TcnMean,
    ModelV2TcnMeanMax,
    analytic_tcn_receptive_field_samples,
    count_trainable_parameters,
)

WINDOW_SAMPLES = 2500


def _synthetic_batch(batch_size: int = 2) -> torch.Tensor:
    # Deterministic synthetic data only -- never real patient ECG.
    return torch.zeros(batch_size, 1, WINDOW_SAMPLES)


def test_capctrl_raw_logit_contract_and_parameter_count() -> None:
    model = ModelV2CapCtrl()
    model.eval()
    with torch.no_grad():
        output = model(_synthetic_batch())
    assert tuple(output.shape) == (2, 1)
    assert torch.isfinite(output).all()
    params = count_trainable_parameters(model)
    assert params == 51969


def test_tcn_mean_raw_logit_contract_and_parameter_cap() -> None:
    model = ModelV2TcnMean()
    model.eval()
    with torch.no_grad():
        output = model(_synthetic_batch())
    assert tuple(output.shape) == (2, 1)
    params = count_trainable_parameters(model)
    assert params <= TCN_PARAMETER_CAP
    assert 40000 <= params <= 70000


def test_tcn_meanmax_raw_logit_contract_and_parameter_cap() -> None:
    model = ModelV2TcnMeanMax()
    model.eval()
    with torch.no_grad():
        output = model(_synthetic_batch())
    assert tuple(output.shape) == (2, 1)
    params = count_trainable_parameters(model)
    assert params <= TCN_PARAMETER_CAP
    assert 40000 <= params <= 70000


def test_tcn_analytic_receptive_field_meets_window_requirement() -> None:
    rf = analytic_tcn_receptive_field_samples()
    assert rf == 3063
    assert rf >= WINDOW_SAMPLES


def test_no_sigmoid_module_present_in_any_v2_architecture() -> None:
    for model in (ModelV2CapCtrl(), ModelV2TcnMean(), ModelV2TcnMeanMax()):
        assert not any(isinstance(m, torch.nn.Sigmoid) for m in model.modules())
