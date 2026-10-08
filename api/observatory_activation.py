# ruff: noqa: E501
"""Opt-in, read-only forward-hook inspection of the released MODEL_V2_FINAL checkpoint on ONE explicitly selected SYNTHETIC scenario window (OBS-DIAG-001).

Isolation: a fresh eager ModelV2TcnMean instance is built per call from the checksum-verified checkpoint (never the served gateway, never any FL state);
forward hooks only read detached outputs and return None; they are removed before returning; execution is bounded (one window, <=24 channels x <=64 time bins
per selected layer). Numerical parity: logits with and without hooks must be bit-identical. Never applied to research recordings, held-out data or FL candidates.
Layer outputs are not clinical explanations."""

from __future__ import annotations

import hashlib
import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import torch

from models.model_v2_architectures import ModelV2TcnMean, count_trainable_parameters
from preprocessing.windowing import NORMALIZATION_EPSILON, normalize_window_zscore
from product.devices.scenarios import ScenarioSpec
from product.observatory.evidence import SCHEMA
from product.observatory.pipeline import canonical_emitted_window

ROOT = Path(__file__).resolve().parents[1]
MAX_CHANNELS, MAX_BINS = 24, 64


@lru_cache(maxsize=1)
def _verified_state_dict() -> dict[str, torch.Tensor]:
    cal = json.loads((ROOT / "artifacts/CAL_V2.json").read_text())
    path = ROOT / "checkpoints/MODEL_V2_FINAL.pt"
    if hashlib.sha256(path.read_bytes()).hexdigest() != cal["model_checkpoint_sha256"]:
        raise ValueError("ACTIVATION_CHECKPOINT_HASH_MISMATCH")
    payload = torch.load(path, map_location="cpu", weights_only=False)
    return {k: v.clone() for k, v in payload["state_dict"].items()}


def _fresh_model() -> ModelV2TcnMean:
    model = ModelV2TcnMean()
    model.load_state_dict(_verified_state_dict())
    return model.eval()


def _stats(tensor: torch.Tensor) -> dict[str, float]:
    t = tensor.detach().double()
    return {"mean": float(t.mean()), "std": float(t.std(unbiased=False)), "min": float(t.min()), "max": float(t.max()),
            "l2_norm": float(t.norm()), "fraction_exactly_zero": float((t == 0).double().mean())}


def _heatmap(tensor: torch.Tensor) -> dict[str, Any]:
    t = tensor.detach().double()[0]                               # [channels, time]
    channels = min(t.shape[0], MAX_CHANNELS)
    bins = min(t.shape[1], MAX_BINS)
    edges = np.linspace(0, t.shape[1], bins + 1).astype(int)
    grid = [[float(t[c, edges[b]:edges[b + 1]].mean()) for b in range(bins)] for c in range(channels)]
    return {"channels": channels, "time_bins": bins, "source_time_steps": int(t.shape[1]), "mean_pooled_values": grid}


def inspect_activations(scenario: ScenarioSpec, window_index: int, layer: str | None = None) -> dict[str, Any]:
    window = canonical_emitted_window(scenario, window_index)
    if window["ecg_quality"] == "UNUSABLE":
        raise ValueError("WINDOW_UNUSABLE_NO_MODEL_INPUT")
    samples = np.asarray(window["ecg"]["samples"], dtype=np.float64)
    tensor = torch.from_numpy(normalize_window_zscore(samples, epsilon=NORMALIZATION_EPSILON).astype(np.float32).reshape(1, 1, -1))
    model = _fresh_model()
    with torch.no_grad():
        baseline = model(tensor)
    collected: dict[str, torch.Tensor] = {}
    handles = []
    leaves = [name for name, module in model.named_modules() if name and not list(module.children())]
    for name, module in model.named_modules():
        if name in leaves:
            handles.append(module.register_forward_hook(lambda _m, _i, out, key=name: collected.__setitem__(key, out.detach().clone())))
    try:
        with torch.no_grad():
            observed = model(tensor)
    finally:
        for handle in handles:
            handle.remove()
    hooks_left = sum(len(m._forward_hooks) for m in model.modules())
    selected = layer if layer in collected else "backbone.blocks.6.relu2"
    if selected not in collected:
        selected = leaves[-2] if len(leaves) > 1 else leaves[-1]
    layers = [{"name": name, "type": type(dict(model.named_modules())[name]).__name__, "output_shape": list(out.shape), **_stats(out)} for name, out in collected.items()]
    bit_identical = bool(torch.equal(baseline, observed))
    logit = float(observed.reshape(-1)[0])
    chosen = collected[selected]
    return {
        "schema_version": SCHEMA, "classification": "ON_DEMAND_FORWARD_HOOK_OBSERVATION_RELEASED_CHECKPOINT_ON_SYNTHETIC_WINDOW",
        "scenario_id": scenario.scenario_id, "window_index": window_index, "window_quality": window["ecg_quality"], "model_id": "MODEL_V2_FINAL",
        "architecture_id": "MODEL_V2_TCN_MEAN", "parameter_count": count_trainable_parameters(model),
        "input_tensor": {"shape": [1, 1, 2500], "dtype": "float32", "identity": "PER_WINDOW_ZSCORE_V1"},
        "raw_logit": logit, "raw_probability": 1 / (1 + math.exp(-logit)),
        "parity": {"logit_bit_identical_with_and_without_hooks": bit_identical, "hooks_remaining_after_inspection": hooks_left},
        "layers": layers, "selected_layer": selected, "selected_layer_heatmap": _heatmap(chosen) if chosen.dim() == 3 else None,
        "limits": {"max_channels": MAX_CHANNELS, "max_time_bins": MAX_BINS, "windows_per_call": 1},
        "caveats": ["Layer activations of the released model on a synthetic window; they are not clinical explanations and not an attribution method.",
                    "Computed on a fresh eager copy of the checksum-verified checkpoint, isolated from the monitoring runtime. Never applied to research recordings or FL candidates."],
    }
