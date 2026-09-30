"""Validation-only and site-local diagnostic evaluation for T025."""

from __future__ import annotations

from typing import Any

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from models.baselines import descriptive_metrics

FL_METRIC_THRESHOLD_ID = "FL_METRIC_THRESHOLD_V1"
FL_METRIC_THRESHOLD = 0.5


def evaluate_model(
    model: nn.Module,
    inputs: np.ndarray,
    labels: np.ndarray,
    groups: np.ndarray,
    *,
    pos_weight: float,
    partition: str,
) -> tuple[dict[str, Any], np.ndarray, np.ndarray]:
    if partition not in {"VALIDATION", "SITE_LOCAL_TRAIN_DIAGNOSTIC"}:
        raise ValueError(f"T025 evaluation partition forbidden: {partition}")
    dataset = TensorDataset(
        torch.from_numpy(np.asarray(inputs, dtype=np.float32)),
        torch.from_numpy(np.asarray(labels, dtype=np.float32)).unsqueeze(1),
    )
    loader = DataLoader(dataset, batch_size=256, shuffle=False, drop_last=False, num_workers=0)
    criterion = nn.BCEWithLogitsLoss(
        pos_weight=torch.tensor([pos_weight], dtype=torch.float32), reduction="sum"
    )
    model.eval()
    losses = 0.0
    logits: list[np.ndarray] = []
    with torch.inference_mode():
        for signals, targets in loader:
            output = model(signals)
            if not torch.isfinite(output).all():
                raise RuntimeError("nonfinite evaluation logits")
            losses += float(criterion(output, targets).item())
            logits.append(output.numpy().reshape(-1))
    raw_logits = np.concatenate(logits)
    probabilities = torch.sigmoid(torch.from_numpy(raw_logits)).numpy().astype(np.float64)
    metrics = descriptive_metrics(labels, probabilities, groups, threshold=FL_METRIC_THRESHOLD)
    metrics["BCE"] = losses / labels.size
    metrics["partition"] = partition
    metrics["probability"] = "sigmoid(raw_logit)"
    metrics["threshold_id"] = FL_METRIC_THRESHOLD_ID
    metrics["threshold"] = FL_METRIC_THRESHOLD
    metrics["calibration"] = "NONE"
    return metrics, raw_logits, probabilities

