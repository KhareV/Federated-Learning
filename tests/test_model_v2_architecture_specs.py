"""V2-001 / C-V2-001-VERIFY architecture pre-registration tests (Sections 8E/13, C-V2-001-
VERIFY Section 4).

Only minimal synthetic shape/parameter-count instantiation is performed here -- these
architectures are never trained on real patient data. Proves the raw-logit output contract
with BOTH a structural check (no Sigmoid/Softmax/LogSoftmax module anywhere in the model) and
a behavioral check (forcing the final Linear head's weight to zero and its bias to a value
outside [0, 1] and confirming the forward output reproduces that bias exactly -- a squashed
probability output could never reach a value like 2.0), plus the TCN parameter cap and its
analytic receptive field >= 2500 samples. The frozen architecture specification itself
(models/model_v2_architectures.py) is not modified -- these tests only manipulate a local,
disposable copy of the model's own parameters.
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
RAW_LOGIT_PROBE_BIAS = 2.0


def _synthetic_batch(batch_size: int = 2) -> torch.Tensor:
    # Deterministic synthetic data only -- never real patient ECG.
    return torch.zeros(batch_size, 1, WINDOW_SAMPLES)


def _random_synthetic_batch(batch_size: int = 3, seed: int = 123) -> torch.Tensor:
    # Still synthetic only -- a fixed-seed generator, never real patient ECG. Used for the
    # behavioral raw-logit probe so the zeroed-weight head is tested against non-trivial
    # input, not just all-zero input (which the probe would trivially pass regardless of
    # whether a sigmoid were present or not, since sigmoid(2.0) != 0 either).
    generator = torch.Generator().manual_seed(seed)
    return torch.randn(batch_size, 1, WINDOW_SAMPLES, generator=generator)


def _assert_no_probability_squashing_module(model: torch.nn.Module) -> None:
    forbidden = (torch.nn.Sigmoid, torch.nn.Softmax, torch.nn.LogSoftmax)
    for module in model.modules():
        assert not isinstance(module, forbidden), f"found forbidden module: {type(module)}"


def _assert_raw_logit_behavioral_probe(model: torch.nn.Module) -> None:
    """Zero the final Linear head's weight and set its bias to RAW_LOGIT_PROBE_BIAS (outside
    [0, 1]); the forward output must reproduce that bias exactly regardless of input, which
    is only possible if the exposed output is the unsquashed raw logit. If a sigmoid were
    applied after the head, the output would instead be sigmoid(2.0) = 0.8808, never 2.0."""
    head = model.output
    assert isinstance(head, torch.nn.Linear)
    with torch.no_grad():
        head.weight.zero_()
        head.bias.fill_(RAW_LOGIT_PROBE_BIAS)

    model.eval()
    with torch.no_grad():
        output = model(_random_synthetic_batch())

    assert torch.allclose(
        output, torch.full_like(output, RAW_LOGIT_PROBE_BIAS), atol=1e-5
    ), f"expected every output == {RAW_LOGIT_PROBE_BIAS} (raw logit), got {output.tolist()}"
    sigmoid_of_probe = torch.sigmoid(torch.tensor(RAW_LOGIT_PROBE_BIAS)).item()
    assert not torch.allclose(
        output, torch.full_like(output, sigmoid_of_probe), atol=1e-3
    ), "output matches sigmoid(bias) instead of raw bias -- a squashing layer is present"


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


def test_capctrl_structural_no_probability_squashing_module() -> None:
    _assert_no_probability_squashing_module(ModelV2CapCtrl())


def test_tcn_mean_structural_no_probability_squashing_module() -> None:
    _assert_no_probability_squashing_module(ModelV2TcnMean())


def test_tcn_meanmax_structural_no_probability_squashing_module() -> None:
    _assert_no_probability_squashing_module(ModelV2TcnMeanMax())


def test_capctrl_behavioral_raw_logit_probe() -> None:
    _assert_raw_logit_behavioral_probe(ModelV2CapCtrl())


def test_tcn_mean_behavioral_raw_logit_probe() -> None:
    _assert_raw_logit_behavioral_probe(ModelV2TcnMean())


def test_tcn_meanmax_behavioral_raw_logit_probe() -> None:
    _assert_raw_logit_behavioral_probe(ModelV2TcnMeanMax())
