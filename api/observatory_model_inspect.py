# ruff: noqa: E501
"""Zero-input shape trace of the real MODEL_V2_TCN_MEAN module (read-only; lives outside the pure-interface `product/` package because it needs torch)."""

from __future__ import annotations

from typing import Any

from product.observatory.evidence import SCHEMA


def architecture() -> dict[str, Any]:
    import torch

    from models.model_v2_architectures import (
        TCN_CHANNELS,
        TCN_DILATIONS,
        TCN_KERNEL_SIZE,
        ModelV2TcnMean,
        analytic_tcn_receptive_field_samples,
        count_trainable_parameters,
    )

    model = ModelV2TcnMean().eval()
    shapes: dict[str, list[int]] = {}
    handles = []
    for name, module in model.named_modules():
        if name and name.count(".") <= 3 and not list(module.children()):
            handles.append(module.register_forward_hook(
                lambda _m, _i, out, key=name: shapes.__setitem__(key, list(out.shape))))
    with torch.no_grad():
        output = model(torch.zeros(1, 1, 2500))
    for handle in handles:
        handle.remove()
    layers = []
    for name, module in model.named_modules():
        if name in shapes:
            params = sum(p.numel() for p in module.parameters(recurse=False))
            layers.append({"name": name, "type": type(module).__name__, "parameters": params,
                           "output_shape": shapes[name]})
    return {
        "schema_version": SCHEMA, "classification": "DERIVED_FROM_ACTUAL_IMPLEMENTATION_ZERO_INPUT_SHAPE_TRACE",
        "architecture_id": "MODEL_V2_TCN_MEAN", "parameter_count": count_trainable_parameters(model),
        "input_shape": [1, 1, 2500], "output_shape": list(output.shape), "channels": TCN_CHANNELS,
        "kernel_size": TCN_KERNEL_SIZE, "dilations": list(TCN_DILATIONS), "pooling": "global temporal mean",
        "receptive_field_samples": analytic_tcn_receptive_field_samples(), "layers": layers,
        "notes": ["Shapes come from running an all-zero tensor through the real module; no weights are loaded and no inference is performed on data.",
                  "Layer outputs are not clinical explanations."],
        "source": {"path": "models/model_v2_architectures.py"},
    }
