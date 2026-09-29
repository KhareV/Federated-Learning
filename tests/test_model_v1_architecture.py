from __future__ import annotations

import torch
from torch import nn

from models.ecg_cnn import (
    EXPECTED_TRAINABLE_PARAMETERS,
    ModelV1,
    build_model_v1,
    intermediate_shapes,
)


def test_exact_ordered_architecture_and_parameter_count() -> None:
    model = build_model_v1()
    children = list(model.children())
    assert [type(module) for module in children] == [
        nn.Conv1d,
        nn.BatchNorm1d,
        nn.ReLU,
        nn.MaxPool1d,
        nn.Conv1d,
        nn.BatchNorm1d,
        nn.ReLU,
        nn.MaxPool1d,
        nn.Conv1d,
        nn.ReLU,
        nn.AdaptiveAvgPool1d,
        nn.Flatten,
        nn.Dropout,
        nn.Linear,
    ]
    assert sum(parameter.numel() for parameter in model.parameters()) == 13_185
    assert EXPECTED_TRAINABLE_PARAMETERS == 13_185
    assert model.conv1.kernel_size == (7,)
    assert model.conv2.kernel_size == model.conv3.kernel_size == (5,)
    assert model.conv1.padding == model.conv2.padding == model.conv3.padding == (0,)
    assert model.dropout.p == 0.2
    assert model.output.in_features == 64 and model.output.out_features == 1


def test_intermediate_and_output_shapes() -> None:
    shapes = intermediate_shapes(1)
    assert shapes == {
        "input": (1, 1, 2500),
        "conv1": (1, 16, 2494),
        "bn1": (1, 16, 2494),
        "relu1": (1, 16, 2494),
        "pool1": (1, 16, 1247),
        "conv2": (1, 32, 1243),
        "bn2": (1, 32, 1243),
        "relu2": (1, 32, 1243),
        "pool2": (1, 32, 621),
        "conv3": (1, 64, 617),
        "relu3": (1, 64, 617),
        "global_pool": (1, 64, 1),
        "flatten": (1, 64),
        "dropout": (1, 64),
        "output": (1, 1),
    }
    model = build_model_v1()
    assert model(torch.zeros(64, 1, 2500)).shape == (64, 1)
    assert model(torch.zeros(3, 1, 2500)).shape == (3, 1)


def test_forward_has_no_probability_activation() -> None:
    model = ModelV1()
    forbidden = (nn.Sigmoid, nn.Softmax, nn.LogSoftmax)
    assert not any(isinstance(module, forbidden) for module in model.modules())
    output = model.eval()(torch.zeros(2, 1, 2500))
    assert output.shape == (2, 1)
