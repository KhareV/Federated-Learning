"""V2-FL-003: MODEL_V2_TCN_MEAN FedProx local objective and deterministic mu selection (additive).

Local loss = BCEWithLogitsLoss + mu/2 * ||w - w_global||^2, where w are the CURRENT local TRAINABLE
parameters and w_global the round-start global trainable parameters. BatchNorm running_mean /
running_var / num_batches_tracked and any other buffer are NOT penalized. Every other semantic is
the V2-FL-001/002 local epoch (federated.model_v2_fl.train_local_epoch_v2): same shuffle-seed rule,
AdamW reset per client per round, drop_last=False, no scheduler/clipping/augmentation. At mu == 0
the penalty term is not added at all, so the update is bit-identical to FedAvg (proved by tests and
the preflight). The historical MODEL_V1 FedProx modules are untouched.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from federated.aggregation import FL_STATE_TRANSPORT_ID, ClientUpdate
from federated.local_training import LocalTrainingResult, derive_shuffle_seed
from federated.model_adapter import extract_state, restore_state, serialize_state
from federated.model_v2_fl import fresh_model_v2

CANDIDATES = (0.001, 0.01, 0.1)
GUARDRAIL_DEGRADATION = 0.05
MACRO_ID = "VALIDATION_PATIENT_MACRO_AUPRC_V2"
WORST_ID = "VALIDATION_PATIENT_WORST_AUPRC_V2"


def proximal_penalty(model: nn.Module, global_parameters: dict[str, torch.Tensor]) -> torch.Tensor:
    """1/2 * sum over TRAINABLE parameters of ||w - w_global||^2 (buffers excluded)."""
    terms = [torch.sum((parameter - global_parameters[name]) ** 2)
             for name, parameter in model.named_parameters() if parameter.requires_grad]
    if not terms:
        raise RuntimeError("model has no trainable parameters")
    return 0.5 * torch.stack(terms).sum()


def local_objective(base_loss: torch.Tensor, model: nn.Module,
                    global_parameters: dict[str, torch.Tensor], mu: float) -> torch.Tensor:
    if mu < 0 or not math.isfinite(mu):
        raise ValueError("mu must be finite and nonnegative")
    return base_loss if mu == 0.0 else base_loss + mu * proximal_penalty(model, global_parameters)


def train_local_fedprox_epoch_v2(
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
    model_factory: Callable[[], nn.Module] = fresh_model_v2,
) -> LocalTrainingResult:
    if mu < 0 or not math.isfinite(mu):
        raise ValueError("mu must be finite and nonnegative")
    if inputs.ndim != 3 or inputs.shape[1:] != (1, 2500):
        raise ValueError("local input shape must be [N,1,2500]")
    if labels.shape != (inputs.shape[0],) or inputs.shape[0] == 0:
        raise ValueError("invalid local examples")
    seed = derive_shuffle_seed(base_seed, experiment_id, round_number, site_id)
    torch.manual_seed(seed % (2**63 - 1))
    model = model_factory()
    restore_state(model, global_state)
    model.train()
    global_parameters = {name: parameter.detach().clone()
                         for name, parameter in model.named_parameters()
                         if parameter.requires_grad}
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate,
                                  weight_decay=weight_decay)
    criterion = nn.BCEWithLogitsLoss(pos_weight=torch.tensor([pos_weight], dtype=torch.float32))
    dataset = TensorDataset(
        torch.from_numpy(np.asarray(inputs, dtype=np.float32)),
        torch.from_numpy(np.asarray(labels, dtype=np.float32)).unsqueeze(1))
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True, drop_last=False,
                        num_workers=0, generator=torch.Generator().manual_seed(seed % (2**63 - 1)))
    total_loss, examples_seen, batches = 0.0, 0, 0
    for signals, targets in loader:
        optimizer.zero_grad(set_to_none=True)
        loss = local_objective(criterion(model(signals), targets), model, global_parameters, mu)
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
    return LocalTrainingResult(
        update=ClientUpdate(site_id, examples_seen, delta, FL_STATE_TRANSPORT_ID),
        mean_loss=total_loss / examples_seen, examples_seen=examples_seen, batch_count=batches,
        shuffle_seed=seed, update_norm=math.sqrt(squared_norm),
        update_bytes=len(serialize_state(delta)))


def select_mu(rows: list[dict[str, Any]], baseline_worst: float) -> dict[str, Any]:
    """Predeclared deterministic selector (same rule/conventions as FEDPROX_SELECTION_SEMANTICS_V1).

    The absolute-0.05 worst-patient guardrail threshold is baseline_worst - 0.05; with the LABEL
    FedAvg worst-patient AUPRC 0.0381 it is NEGATIVE, so it can never bind (AUPRC >= 0)."""
    if tuple(float(r["mu"]) for r in rows) != CANDIDATES:
        raise ValueError("FedProx candidate set/order mismatch")
    threshold = baseline_worst - GUARDRAIL_DEGRADATION
    evaluated = []
    for row in rows:
        item = dict(row)
        item["worst_guardrail_threshold"] = threshold
        worst = float(row[WORST_ID])
        item["guardrail_pass"] = worst > threshold or abs(worst - threshold) <= 1e-12
        evaluated.append(item)
    eligible = [r for r in evaluated if r["guardrail_pass"]]
    if not eligible:
        raise RuntimeError("FEDPROX_NO_ACCEPTABLE_MU")
    ranked = sorted(eligible, key=lambda r: (
        -round(float(r[MACRO_ID]), 12), -float(r[WORST_ID]),
        -float(r["best_global_validation_AUPRC"]), float(r["mu"])))
    return {"guardrail_absolute_degradation": GUARDRAIL_DEGRADATION,
            "guardrail_threshold": threshold,
            "guardrail_nonbinding_because": "threshold < 0 and finite AUPRC >= 0",
            "eligible_candidates": [float(r["mu"]) for r in ranked],
            "ranking": [float(r["mu"]) for r in ranked],
            "selected_mu": float(ranked[0]["mu"]), "evaluated_candidates": evaluated,
            "primary_metric": MACRO_ID,
            "tie_policy": ["higher_worst", "higher_global", "smaller_mu"]}
