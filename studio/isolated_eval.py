# ruff: noqa: E501
"""RNG-free checkpoint scoring that is safe to run while a federation run trains on another thread.

Why: the frozen local trainer seeds torch's single process-wide default generator and draws Dropout masks from it. ``final_showcase.evaluate.logits_for`` builds a
fresh model, and building a model draws random initial weights from that SAME generator, so scoring on another thread interleaves draws and silently changes the
training result (observed as PREFIX_PARITY_MISMATCH). This module builds ONE template model before any run exists and only deep-copies it (no random draws),
then restores the committed state and runs plain inference. Metric code is the unchanged FL10 metric engine; numbers equal ``fl10.evaluate.evaluate_states`` bit for bit
(proved by tests against the recorded FL10 evaluation)."""

from __future__ import annotations

import copy
import threading
from typing import Any

import numpy as np
import torch

from federated.model_adapter import restore_state
from federated.model_v2_fl import fresh_model_v2
from final_showcase import metrics as base_metrics
from fl10 import metrics

_LOCK = threading.Lock()
_TEMPLATE: torch.nn.Module | None = None


def prepare_template() -> None:
    """Idempotent. Call at process start (before any run); constructing the template is the ONLY place this module consumes the global RNG."""
    global _TEMPLATE
    with _LOCK:
        if _TEMPLATE is None:
            _TEMPLATE = fresh_model_v2().eval()


def isolated_logits(state: dict[str, Any], inputs: np.ndarray) -> np.ndarray:
    prepare_template()
    assert _TEMPLATE is not None
    model = copy.deepcopy(_TEMPLATE)
    restore_state(model, state)
    model.eval()
    out = []
    with torch.no_grad():
        for start in range(0, len(inputs), 64):
            out.append(model(torch.from_numpy(np.ascontiguousarray(inputs[start:start + 64], dtype=np.float32))).reshape(-1).numpy())
    return np.concatenate(out).astype(np.float64)


def evaluate_isolated(states: dict[str, dict[str, Any]], datasets: list[Any], *, replicates: int = 0, seed: int = 0, **_: Any) -> dict[str, Any]:
    """Same result structure as ``fl10.evaluate.evaluate_states`` (without the paired bootstrap, which the observer computes from stored predictions)."""
    inputs = np.concatenate([d.inputs for d in datasets])
    labels = np.concatenate([d.labels for d in datasets]).astype(int)
    owners = np.concatenate([[d.participant_id] * len(d.labels) for d in datasets])
    logits = {name: isolated_logits(state, inputs) for name, state in states.items()}
    result: dict[str, Any] = {"states": {}, "windows": int(labels.size)}
    for name, z in logits.items():
        if not np.isfinite(z).all():
            raise RuntimeError(f"NONFINITE_LOGITS:{name}")
        part = metrics.participant_metrics(owners, labels, z)
        result["states"][name] = {"pooled": metrics.full_metrics(labels, z), "participants": part["per_participant"], "participant_macro_F1": part["participant_macro_F1"],
                                  "participants_defined": part["participants_defined"], "participants_undefined": part["participants_undefined"], "curves": base_metrics.curves(labels, z)}
    result["_logits"], result["_labels"], result["_owners"] = logits, labels, owners
    return result
