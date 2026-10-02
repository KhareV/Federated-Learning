"""V2-001 pre-registered MODEL_V2 architecture specifications (configs/model_v2/
research_protocol_v1.yaml architectures.*). PRE_REGISTERED status only -- none of these are
trained in V2-001; they exist so parameter counts, the raw-logit output contract, and the
TCN receptive field can be verified mechanically before any training occurs (V2-004)."""

from __future__ import annotations

import torch
from torch import nn

CAPCTRL_ID = "MODEL_V2_CAPCTRL"
TCN_MEAN_ID = "MODEL_V2_TCN_MEAN"
TCN_MEANMAX_ID = "MODEL_V2_TCN_MEANMAX"

TCN_CHANNELS = 24
TCN_KERNEL_SIZE = 7
TCN_DILATIONS = (1, 2, 4, 8, 16, 32, 64)
TCN_STEM_KERNEL_SIZE = 15
TCN_STEM_STRIDE = 2
TCN_STEM_PADDING = 7
TCN_PARAMETER_CAP = 120_000


class ModelV2CapCtrl(nn.Module):
    """ARCH-A: capacity-only control CNN. Raw logit output (no sigmoid)."""

    def __init__(self) -> None:
        super().__init__()
        self.conv1 = nn.Conv1d(1, 32, kernel_size=7)
        self.bn1 = nn.BatchNorm1d(32)
        self.relu1 = nn.ReLU()
        self.pool1 = nn.MaxPool1d(kernel_size=2)
        self.conv2 = nn.Conv1d(32, 64, kernel_size=5)
        self.bn2 = nn.BatchNorm1d(64)
        self.relu2 = nn.ReLU()
        self.pool2 = nn.MaxPool1d(kernel_size=2)
        self.conv3 = nn.Conv1d(64, 128, kernel_size=5)
        self.relu3 = nn.ReLU()
        self.global_pool = nn.AdaptiveAvgPool1d(1)
        self.flatten = nn.Flatten(start_dim=1)
        self.dropout = nn.Dropout(p=0.2)
        self.output = nn.Linear(128, 1)

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        values = self.pool1(self.relu1(self.bn1(self.conv1(inputs))))
        values = self.pool2(self.relu2(self.bn2(self.conv2(values))))
        values = self.relu3(self.conv3(values))
        values = self.global_pool(values)
        values = self.flatten(values)
        values = self.dropout(values)
        return self.output(values)


class _TCNResidualBlock(nn.Module):
    def __init__(self, channels: int, kernel_size: int, dilation: int) -> None:
        super().__init__()
        padding = ((kernel_size - 1) // 2) * dilation
        self.conv1 = nn.Conv1d(
            channels, channels, kernel_size, dilation=dilation, padding=padding, bias=False
        )
        self.bn1 = nn.BatchNorm1d(channels)
        self.relu1 = nn.ReLU()
        self.dropout = nn.Dropout(p=0.1)
        self.conv2 = nn.Conv1d(
            channels, channels, kernel_size, dilation=dilation, padding=padding, bias=False
        )
        self.bn2 = nn.BatchNorm1d(channels)
        self.relu2 = nn.ReLU()

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        values = self.dropout(self.relu1(self.bn1(self.conv1(inputs))))
        values = self.bn2(self.conv2(values))
        return self.relu2(values + inputs)


class _TCNBackbone(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.stem_conv = nn.Conv1d(
            1,
            TCN_CHANNELS,
            kernel_size=TCN_STEM_KERNEL_SIZE,
            stride=TCN_STEM_STRIDE,
            padding=TCN_STEM_PADDING,
            bias=False,
        )
        self.stem_bn = nn.BatchNorm1d(TCN_CHANNELS)
        self.stem_relu = nn.ReLU()
        self.blocks = nn.ModuleList(
            _TCNResidualBlock(TCN_CHANNELS, TCN_KERNEL_SIZE, dilation=d) for d in TCN_DILATIONS
        )

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        values = self.stem_relu(self.stem_bn(self.stem_conv(inputs)))
        for block in self.blocks:
            values = block(values)
        return values


class ModelV2TcnMean(nn.Module):
    """ARCH-B: dilated TCN, global temporal mean pooling head. Raw logit output."""

    def __init__(self) -> None:
        super().__init__()
        self.backbone = _TCNBackbone()
        self.dropout = nn.Dropout(p=0.2)
        self.output = nn.Linear(TCN_CHANNELS, 1)

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        features = self.backbone(inputs)
        pooled = features.mean(dim=2)
        return self.output(self.dropout(pooled))


class ModelV2TcnMeanMax(nn.Module):
    """ARCH-C: dilated TCN, mean+max pooling head. Raw logit output."""

    def __init__(self) -> None:
        super().__init__()
        self.backbone = _TCNBackbone()
        self.dropout = nn.Dropout(p=0.2)
        self.output = nn.Linear(TCN_CHANNELS * 2, 1)

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        features = self.backbone(inputs)
        mean_pool = features.mean(dim=2)
        max_pool = features.max(dim=2).values
        pooled = torch.cat([mean_pool, max_pool], dim=1)
        return self.output(self.dropout(pooled))


def analytic_tcn_receptive_field_samples() -> int:
    """Closed-form receptive field of the TCN backbone (ARCH-B/ARCH-C) in ORIGINAL input
    samples, accounting for the stride-2 stem. Not a simulation -- pure arithmetic."""
    output_resolution_rf = 1
    for dilation in TCN_DILATIONS:
        output_resolution_rf += 2 * (TCN_KERNEL_SIZE - 1) * dilation
    input_resolution_rf = (
        (output_resolution_rf - 1) * TCN_STEM_STRIDE + TCN_STEM_KERNEL_SIZE
    )
    return input_resolution_rf


def count_trainable_parameters(module: nn.Module) -> int:
    return sum(p.numel() for p in module.parameters() if p.requires_grad)
