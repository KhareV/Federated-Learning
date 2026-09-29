"""Exact v2.2 MODEL_V1 single-lead ECG CNN returning raw logits."""

from __future__ import annotations

import torch
from torch import nn

MODEL_ID = "MODEL_V1"
EXPECTED_TRAINABLE_PARAMETERS = 13_185


class ModelV1(nn.Module):
    """Locked architecture for one 10-second, 250-Hz ECG window."""

    def __init__(self) -> None:
        super().__init__()
        self.conv1 = nn.Conv1d(1, 16, kernel_size=7, stride=1)
        self.bn1 = nn.BatchNorm1d(16)
        self.relu1 = nn.ReLU()
        self.pool1 = nn.MaxPool1d(kernel_size=2)
        self.conv2 = nn.Conv1d(16, 32, kernel_size=5, stride=1)
        self.bn2 = nn.BatchNorm1d(32)
        self.relu2 = nn.ReLU()
        self.pool2 = nn.MaxPool1d(kernel_size=2)
        self.conv3 = nn.Conv1d(32, 64, kernel_size=5, stride=1)
        self.relu3 = nn.ReLU()
        self.global_pool = nn.AdaptiveAvgPool1d(1)
        self.flatten = nn.Flatten(start_dim=1)
        self.dropout = nn.Dropout(p=0.2)
        self.output = nn.Linear(64, 1)

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        values = self.pool1(self.relu1(self.bn1(self.conv1(inputs))))
        values = self.pool2(self.relu2(self.bn2(self.conv2(values))))
        values = self.relu3(self.conv3(values))
        values = self.global_pool(values)
        values = self.flatten(values)
        values = self.dropout(values)
        return self.output(values)


def build_model_v1() -> ModelV1:
    model = ModelV1()
    parameter_count = sum(
        parameter.numel() for parameter in model.parameters() if parameter.requires_grad
    )
    if parameter_count != EXPECTED_TRAINABLE_PARAMETERS:
        raise RuntimeError(
            "MODEL_V1 parameter drift: "
            f"expected {EXPECTED_TRAINABLE_PARAMETERS}, got {parameter_count}"
        )
    return model


def intermediate_shapes(batch_size: int = 1) -> dict[str, tuple[int, ...]]:
    """Return audited intermediate shapes without changing the architecture."""
    model = build_model_v1().eval()
    values = torch.zeros(batch_size, 1, 2500)
    shapes: dict[str, tuple[int, ...]] = {"input": tuple(values.shape)}
    with torch.inference_mode():
        for name in (
            "conv1",
            "bn1",
            "relu1",
            "pool1",
            "conv2",
            "bn2",
            "relu2",
            "pool2",
            "conv3",
            "relu3",
            "global_pool",
            "flatten",
            "dropout",
            "output",
        ):
            values = getattr(model, name)(values)
            shapes[name] = tuple(values.shape)
    return shapes
