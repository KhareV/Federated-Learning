# ruff: noqa: E501
"""Verified pretrained starting point for V2-initialised federated fine-tuning (``MODEL_V2_FINAL``).

The trained checkpoint is a READ-ONLY input: its bytes are checked against the digest in its own manifest, its state is mapped onto the exact FL state layout
(same keys, order, shapes, dtypes as ``fresh_initial_state_v2``), and a full compatibility audit is produced. Nothing here trains, calibrates or edits a checkpoint.
The ``FL_INIT_V2`` initialisation (an untrained model) is a different, separately identified mode and is never replaced by this one.

Process-wide RNG safety: no model is constructed here (a deep copy of the evaluation template is used), so a run that is training on another thread is not perturbed."""

from __future__ import annotations

import copy
import hashlib
import json
from collections import OrderedDict
from pathlib import Path
from typing import Any

import numpy as np
import torch

from federated.model_adapter import extract_state, restore_state
from federated.model_v2_fl import state_sha
from studio import isolated_eval

ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = Path("checkpoints/MODEL_V2_FINAL.pt")
MANIFEST = Path("checkpoints/MODEL_V2_FINAL.manifest.json")

INIT_FRESH = "FL_INIT_V2"
INIT_V2_FINAL = "MODEL_V2_FINAL"
INITS = (INIT_FRESH, INIT_V2_FINAL)
INIT_LABELS = {
    INIT_FRESH: "Untrained V2-architecture model (FL_INIT_V2) trained from scratch by federated rounds",
    INIT_V2_FINAL: "Pretrained MODEL_V2_FINAL fine-tuned by federated rounds on the synthetic engineering-event task",
}


class V2InitError(RuntimeError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}:{detail}" if detail else code)
        self.code, self.detail = code, detail


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_v2_final(root: Path = ROOT) -> tuple[OrderedDict[str, np.ndarray], dict[str, Any]]:
    """Return (state, audit). Fails closed on any digest, key, order, shape, dtype, buffer or finiteness difference from the FL model layout."""
    manifest = json.loads((root / MANIFEST).read_text())
    expected = manifest["checkpoint"]["sha256"]
    actual = _sha_file(root / CHECKPOINT)
    if actual != expected:
        raise V2InitError("CHECKPOINT_DIGEST_MISMATCH", f"{actual[:12]} != {expected[:12]}")
    payload = torch.load(root / CHECKPOINT, map_location="cpu", weights_only=False)
    raw = payload.get("state_dict") if isinstance(payload, dict) else None
    if not isinstance(raw, dict):      # identity is pinned by the manifest digest above; the embedded ``model_id`` names the lineage (MODEL_V1) and is only recorded
        raise V2InitError("CHECKPOINT_STRUCTURE_UNEXPECTED")
    isolated_eval.prepare_template()
    template = isolated_eval._TEMPLATE
    assert template is not None
    reference = extract_state(template)                         # layout only (keys / shapes / dtypes); the template's random weights are never used
    if list(raw) != list(reference):
        raise V2InitError("STATE_KEYS_OR_ORDER_DIFFER", f"{len(raw)} vs {len(reference)}")
    state: OrderedDict[str, np.ndarray] = OrderedDict()
    mismatches: list[str] = []
    for key, tensor in raw.items():
        array = np.array(tensor.detach().cpu().numpy(), copy=True, order="C")
        ref = reference[key]
        if array.shape != ref.shape or array.dtype != ref.dtype:
            mismatches.append(f"{key}:{array.shape}/{array.dtype} vs {ref.shape}/{ref.dtype}")
        if np.issubdtype(array.dtype, np.floating) and not np.isfinite(array).all():
            mismatches.append(f"{key}:NONFINITE")
        state[key] = array
    if mismatches:
        raise V2InitError("STATE_LAYOUT_MISMATCH", "; ".join(mismatches[:4]))
    model = copy.deepcopy(template)
    restore_state(model, state)                                  # strict load into the FL model class (raises on any key / shape / dtype difference)
    round_trip = extract_state(model)
    if state_sha(OrderedDict(round_trip)) != state_sha(state):
        raise V2InitError("STATE_ROUND_TRIP_DIGEST_MISMATCH")
    parameters = int(sum(int(np.prod(v.shape)) for k, v in state.items() if np.issubdtype(v.dtype, np.floating) and "running_" not in k and "num_batches" not in k))
    audit = {
        "model_id": manifest["model_id"], "architecture_id": manifest["architecture_id"], "checkpoint": str(CHECKPOINT), "checkpoint_sha256": actual,
        "manifest_checkpoint_sha256": expected, "embedded_model_id": payload.get("model_id"), "best_epoch": payload.get("best_epoch"), "best_validation_auprc": payload.get("best_validation_auprc"), "state_entries": len(state), "keys_and_order_equal": True, "shapes_dtypes_equal": True, "all_finite": True,
        "strict_load_round_trip_equal": True, "state_sha256": state_sha(state), "trainable_and_buffer_float_elements": parameters,
        "manifest_parameter_count": manifest.get("parameter_count"), "training_target_of_checkpoint": "AAMI_SVF_WINDOW_V1 (real research ECG)",
        "label": INIT_LABELS[INIT_V2_FINAL],
    }
    return state, audit


def initial_state(init: str) -> tuple[OrderedDict[str, np.ndarray], dict[str, Any]]:
    """The R0 state of a run for the requested initialisation."""
    if init == INIT_V2_FINAL:
        return load_v2_final()
    if init == INIT_FRESH:
        from federated.wearable_fl_runner_v1 import new_session

        state, _ = new_session()
        return OrderedDict(state), {"model_id": INIT_FRESH, "state_sha256": state_sha(state), "label": INIT_LABELS[INIT_FRESH]}
    raise V2InitError("UNKNOWN_INITIALISATION", init)


def logits_parity(state: OrderedDict[str, np.ndarray], probe: np.ndarray) -> dict[str, Any]:
    """The state evaluated through the isolated Studio path equals the checkpoint evaluated through an independent plain ``load_state_dict`` path."""
    isolated = isolated_eval.isolated_logits(state, probe)
    model = copy.deepcopy(isolated_eval._TEMPLATE)
    payload = torch.load(ROOT / CHECKPOINT, map_location="cpu", weights_only=False)
    model.load_state_dict(payload["state_dict"], strict=True)
    model.eval()
    with torch.no_grad():
        direct = model(torch.from_numpy(np.ascontiguousarray(probe, dtype=np.float32))).reshape(-1).numpy().astype(np.float64)
    return {"windows": len(probe), "max_abs_difference": float(np.max(np.abs(isolated - direct))), "equal": bool(np.array_equal(isolated, direct))}
