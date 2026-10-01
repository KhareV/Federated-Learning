"""Matched FedProx local objective; all non-objective semantics reuse T025."""

from __future__ import annotations

import math

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from federated.aggregation import FL_STATE_TRANSPORT_ID, ClientUpdate
from federated.local_training import LocalTrainingResult, derive_shuffle_seed
from federated.model_adapter import extract_state, fresh_model_v1, restore_state, serialize_state


def proximal_penalty(model: nn.Module, global_parameters: dict[str, torch.Tensor]) -> torch.Tensor:
    """Return 1/2 * sum ||w-w_global||^2 over trainable parameters only."""
    terms = [
        torch.sum((parameter - global_parameters[name]) ** 2)
        for name, parameter in model.named_parameters()
        if parameter.requires_grad
    ]
    if not terms:
        raise RuntimeError("MODEL_V1 has no trainable parameters")
    return 0.5 * torch.stack(terms).sum()


def train_local_fedprox_epoch(
    *,
    global_state: dict[str, np.ndarray],
    inputs: np.ndarray,
    labels: np.ndarray,
    site_id: str,
    round_number: int,
    experiment_id: str,
    base_seed: int,
    batch_size: int,
    learning_rate: float,
    weight_decay: float,
    pos_weight: float,
    mu: float,
) -> LocalTrainingResult:
    if mu < 0 or not math.isfinite(mu):
        raise ValueError("mu must be finite and nonnegative")
    if inputs.ndim != 3 or inputs.shape[1:] != (1, 2500):
        raise ValueError("local input shape must be [N,1,2500]")
    if labels.shape != (inputs.shape[0],) or inputs.shape[0] == 0:
        raise ValueError("invalid local examples")
    seed = derive_shuffle_seed(base_seed, experiment_id, round_number, site_id)
    torch.manual_seed(seed % (2**63 - 1))
    model = fresh_model_v1()
    restore_state(model, global_state)
    model.train()
    global_parameters = {
        name: parameter.detach().clone()
        for name, parameter in model.named_parameters()
        if parameter.requires_grad
    }
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=weight_decay)
    criterion = nn.BCEWithLogitsLoss(pos_weight=torch.tensor([pos_weight], dtype=torch.float32))
    dataset = TensorDataset(
        torch.from_numpy(np.asarray(inputs, dtype=np.float32)),
        torch.from_numpy(np.asarray(labels, dtype=np.float32)).unsqueeze(1),
    )
    loader = DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=True,
        drop_last=False,
        num_workers=0,
        generator=torch.Generator().manual_seed(seed % (2**63 - 1)),
    )
    total_loss, examples_seen, batches = 0.0, 0, 0
    for signals, targets in loader:
        optimizer.zero_grad(set_to_none=True)
        base_loss = criterion(model(signals), targets)
        # Preserve bitwise FedAvg behavior for the mandatory mu=0 equivalence path.
        loss = (
            base_loss if mu == 0.0 else base_loss + mu * proximal_penalty(model, global_parameters)
        )
        if not torch.isfinite(loss):
            raise RuntimeError("nonfinite local FedProx loss")
        loss.backward()
        optimizer.step()
        count = signals.shape[0]
        total_loss += float(loss.item()) * count
        examples_seen += count
        batches += 1
    if examples_seen != inputs.shape[0] or batches != math.ceil(inputs.shape[0] / batch_size):
        raise RuntimeError("local epoch example accounting mismatch")
    local_state = extract_state(model)
    delta: dict[str, np.ndarray] = {}
    squared_norm = 0.0
    for key, global_value in global_state.items():
        if np.issubdtype(global_value.dtype, np.floating):
            value = np.asarray(local_state[key] - global_value, dtype=global_value.dtype)
            squared_norm += float(np.sum(np.asarray(value, dtype=np.float64) ** 2))
            delta[key] = value
        else:
            delta[key] = np.zeros_like(global_value)
    update = ClientUpdate(site_id, examples_seen, delta, FL_STATE_TRANSPORT_ID)
    return LocalTrainingResult(
        update=update,
        mean_loss=total_loss / examples_seen,
        examples_seen=examples_seen,
        batch_count=batches,
        shuffle_seed=seed,
        update_norm=math.sqrt(squared_norm),
        update_bytes=len(serialize_state(delta)),
    )
