from __future__ import annotations

import numpy as np
import pytest
import torch

from federated.fedprox_selection import CANDIDATES, select_mu
from federated.fedprox_training import proximal_penalty
from federated.model_adapter import fresh_model_v1


def test_proximal_penalty_trainable_parameters_only() -> None:
    model = fresh_model_v1()
    snapshot = {name: parameter.detach().clone() for name, parameter in model.named_parameters()}
    assert proximal_penalty(model, snapshot).item() == 0.0
    first = next(model.parameters())
    with torch.no_grad():
        first.add_(1.0)
    assert proximal_penalty(model, snapshot).item() == pytest.approx(first.numel() / 2)
    assert all("running_" not in name and "num_batches_tracked" not in name for name in snapshot)


def test_snapshot_is_immutable() -> None:
    model = fresh_model_v1()
    snapshot = {name: parameter.detach().clone() for name, parameter in model.named_parameters()}
    before = {name: value.clone() for name, value in snapshot.items()}
    with torch.no_grad():
        next(model.parameters()).add_(0.5)
    assert all(torch.equal(snapshot[name], before[name]) for name in snapshot)


def test_candidate_set_and_guardrail_boundary() -> None:
    rows = [
        {
            "mu": mu,
            "validation_patient_macro_AUPRC": 0.5 - i * 0.01,
            "validation_patient_worst_AUPRC": 0.35 if i == 0 else 0.36,
            "best_global_validation_AUPRC": 0.5,
        }
        for i, mu in enumerate(CANDIDATES)
    ]
    selected = select_mu(rows, 0.4)
    assert selected["evaluated_candidates"][0]["guardrail_pass"] is True
    assert selected["selected_mu"] == 0.001


def test_selection_rejects_candidate_drift() -> None:
    with pytest.raises(ValueError):
        select_mu([{"mu": 0.2}], 0.4)


def test_selection_tie_prefers_worst_then_global_then_smaller() -> None:
    rows = [
        {
            "mu": 0.001,
            "validation_patient_macro_AUPRC": 0.5,
            "validation_patient_worst_AUPRC": 0.31,
            "best_global_validation_AUPRC": 0.7,
        },
        {
            "mu": 0.01,
            "validation_patient_macro_AUPRC": 0.5,
            "validation_patient_worst_AUPRC": 0.32,
            "best_global_validation_AUPRC": 0.6,
        },
        {
            "mu": 0.1,
            "validation_patient_macro_AUPRC": 0.49,
            "validation_patient_worst_AUPRC": 0.4,
            "best_global_validation_AUPRC": 0.8,
        },
    ]
    assert select_mu(rows, 0.3)["selected_mu"] == 0.01


def test_no_nonfinite_mu() -> None:
    assert not np.isfinite(float("nan"))
