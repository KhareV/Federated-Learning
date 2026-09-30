"""Deterministic one-epoch local MODEL_V1 training for plain FedAvg."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from federated.aggregation import FL_STATE_TRANSPORT_ID, ClientUpdate
from federated.model_adapter import extract_state, fresh_model_v1, restore_state, serialize_state

FL_OPTIMIZER_STATE_ID = "FL_OPTIMIZER_STATE_V1"
SEED_RULE_ID = "FL_CLIENT_ROUND_SHA256_V1"


@dataclass(frozen=True)
class LocalTrainingResult:
    update: ClientUpdate
    mean_loss: float
    examples_seen: int
    batch_count: int
    shuffle_seed: int
    update_norm: float
    update_bytes: int


def derive_shuffle_seed(base_seed: int, experiment_id: str, round_number: int, site_id: str) -> int:
    material = f"{base_seed}|{experiment_id}|{round_number}|{site_id}".encode()
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big")


def train_local_epoch(
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
) -> LocalTrainingResult:
    if inputs.ndim != 3 or inputs.shape[1:] != (1, 2500):
        raise ValueError("local input shape must be [N,1,2500]")
    if labels.shape != (inputs.shape[0],):
        raise ValueError("local labels do not align")
    if inputs.shape[0] == 0:
        raise ValueError("zero-example client is forbidden")
    seed = derive_shuffle_seed(base_seed, experiment_id, round_number, site_id)
    torch.manual_seed(seed % (2**63 - 1))
    model = fresh_model_v1()
    restore_state(model, global_state)
    model.train()
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=learning_rate, weight_decay=weight_decay
    )
    criterion = nn.BCEWithLogitsLoss(
        pos_weight=torch.tensor([pos_weight], dtype=torch.float32)
    )
    dataset = TensorDataset(
        torch.from_numpy(np.asarray(inputs, dtype=np.float32)),
        torch.from_numpy(np.asarray(labels, dtype=np.float32)).unsqueeze(1),
    )
    generator = torch.Generator().manual_seed(seed % (2**63 - 1))
    loader = DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=True,
        drop_last=False,
        num_workers=0,
        generator=generator,
    )
    total_loss = 0.0
    examples_seen = 0
    batches = 0
    for signals, targets in loader:
        optimizer.zero_grad(set_to_none=True)
        logits = model(signals)
        loss = criterion(logits, targets)
        if not torch.isfinite(loss):
            raise RuntimeError("nonfinite local loss")
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
    payload_bytes = len(serialize_state(delta))
    update = ClientUpdate(site_id, examples_seen, delta, FL_STATE_TRANSPORT_ID)
    return LocalTrainingResult(
        update=update,
        mean_loss=total_loss / examples_seen,
        examples_seen=examples_seen,
        batch_count=batches,
        shuffle_seed=seed,
        update_norm=math.sqrt(squared_norm),
        update_bytes=payload_bytes,
    )
