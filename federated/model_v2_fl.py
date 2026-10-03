"""MODEL_V2_TCN_MEAN federated building blocks for V2-FL-001 (additive; no V1 FL file is edited).

FL_STATE_TRANSPORT_V1 is reused UNCHANGED: its policy is dtype-generic (aggregate every floating
state_dict entry by sample count; keep every non-floating buffer at the server value) and
federated.aggregation / federated.model_adapter contain no MODEL_V1 key/count logic (only the
factory in local_training/fedavg_runner and error-message wording are V1-named). This module
supplies the MODEL_V2 factory/initialization and a local-training function that reproduces
federated.local_training.train_local_epoch EXACTLY except for the model factory (proved by a
differential test with the MODEL_V1 factory).
"""

from __future__ import annotations

import math
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from federated.aggregation import FL_STATE_TRANSPORT_ID, ClientUpdate
from federated.local_training import LocalTrainingResult, derive_shuffle_seed
from federated.model_adapter import extract_state, restore_state, serialize_state
from models.model_v2_architectures import ModelV2TcnMean, count_trainable_parameters
from nhm.hashing import hash_bytes

EXPERIMENT_ID = "FL_IID_MODEL_V2_V1"
INITIALIZATION_ID = "FL_INIT_V2"
ARCHITECTURE_ID = "MODEL_V2_TCN_MEAN"
PARAMETER_COUNT = 57_553


def fresh_model_v2() -> nn.Module:
    return ModelV2TcnMean().eval()


def set_determinism(seed: int) -> None:
    import os
    import random

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)
    torch.set_num_threads(max(1, min(4, os.cpu_count() or 1)))


def fresh_initial_state_v2(seed: int) -> OrderedDict[str, np.ndarray]:
    """FL_INIT_V2: untrained MODEL_V2_TCN_MEAN under the T025 seeding protocol. Never loads a
    trained checkpoint."""
    set_determinism(seed)
    return extract_state(fresh_model_v2())


def state_sha(state: dict[str, np.ndarray]) -> str:
    return hash_bytes(serialize_state(state))


def classify_state_entries(model: nn.Module) -> list[dict[str, Any]]:
    parameter_keys = set(dict(model.named_parameters()))
    rows = []
    for key, tensor in model.state_dict().items():
        if key in parameter_keys:
            role = "floating_trainable_parameter"
        elif tensor.is_floating_point():
            role = "floating_non_trainable_buffer"
        elif tensor.dtype in (torch.int64, torch.int32, torch.int16, torch.int8, torch.uint8):
            role = "integer_bookkeeping_buffer"
        else:
            role = "other"
        rows.append({"key": key, "shape": list(tensor.shape), "dtype": str(tensor.dtype),
                     "role": role, "aggregated_numerically": tensor.is_floating_point()})
    return rows


def train_local_epoch_v2(
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
    model_factory: Callable[[], nn.Module] = fresh_model_v2,
) -> LocalTrainingResult:
    """Line-for-line the T025 local epoch (federated.local_training.train_local_epoch) with an
    injectable model factory: shuffle seed rule FL_CLIENT_ROUND_SHA256_V1, torch.manual_seed and a
    seeded DataLoader generator, AdamW reset every call, BCEWithLogitsLoss(global pos_weight),
    one epoch, drop_last=False, no augmentation, no scheduler, no gradient clipping."""
    if inputs.ndim != 3 or inputs.shape[1:] != (1, 2500):
        raise ValueError("local input shape must be [N,1,2500]")
    if labels.shape != (inputs.shape[0],):
        raise ValueError("local labels do not align")
    if inputs.shape[0] == 0:
        raise ValueError("zero-example client is forbidden")
    seed = derive_shuffle_seed(base_seed, experiment_id, round_number, site_id)
    torch.manual_seed(seed % (2**63 - 1))
    model = model_factory()
    restore_state(model, global_state)
    model.train()
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate,
                                  weight_decay=weight_decay)
    criterion = nn.BCEWithLogitsLoss(pos_weight=torch.tensor([pos_weight], dtype=torch.float32))
    dataset = TensorDataset(
        torch.from_numpy(np.asarray(inputs, dtype=np.float32)),
        torch.from_numpy(np.asarray(labels, dtype=np.float32)).unsqueeze(1),
    )
    generator = torch.Generator().manual_seed(seed % (2**63 - 1))
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True, drop_last=False,
                        num_workers=0, generator=generator)
    total_loss, examples_seen, batches = 0.0, 0, 0
    for signals, targets in loader:
        optimizer.zero_grad(set_to_none=True)
        loss = criterion(model(signals), targets)
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
        update=update, mean_loss=total_loss / examples_seen, examples_seen=examples_seen,
        batch_count=batches, shuffle_seed=seed, update_norm=math.sqrt(squared_norm),
        update_bytes=payload_bytes)


__all__ = [
    "ARCHITECTURE_ID", "EXPERIMENT_ID", "INITIALIZATION_ID", "PARAMETER_COUNT",
    "classify_state_entries", "count_trainable_parameters", "fresh_initial_state_v2",
    "fresh_model_v2", "set_determinism", "state_sha", "train_local_epoch_v2",
]
