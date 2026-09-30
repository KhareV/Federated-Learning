"""Deterministic MODEL_V1 adapter implementing FL_STATE_TRANSPORT_V1."""

from __future__ import annotations

import json
import struct
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import torch
from numpy.typing import NDArray

from federated.aggregation import FL_STATE_TRANSPORT_ID
from models.ecg_cnn import build_model_v1
from models.model_freeze import load_frozen_model_v1

_MAGIC = b"NHMFLST1"


@dataclass(frozen=True)
class StateEntrySpec:
    key: str
    shape: tuple[int, ...]
    dtype: str
    aggregatable: bool
    state_role: str


def model_v1_state_spec(model: torch.nn.Module) -> list[StateEntrySpec]:
    parameter_keys = set(dict(model.named_parameters()))
    entries: list[StateEntrySpec] = []
    for key, tensor in model.state_dict().items():
        floating = tensor.is_floating_point()
        role = "parameter" if key in parameter_keys else (
            "floating_buffer" if floating else "non_floating_buffer"
        )
        entries.append(
            StateEntrySpec(
                key=key,
                shape=tuple(tensor.shape),
                dtype=str(tensor.detach().cpu().numpy().dtype),
                aggregatable=floating,
                state_role=role,
            )
        )
    return entries


def extract_state(model: torch.nn.Module) -> OrderedDict[str, NDArray[np.generic]]:
    return OrderedDict(
        (key, np.array(tensor.detach().cpu().numpy(), copy=True, order="C"))
        for key, tensor in model.state_dict().items()
    )


def serialize_state(state: Mapping[str, NDArray[np.generic]]) -> bytes:
    """Serialize ordered arrays to canonical JSON metadata plus raw C-order bytes."""

    entries: list[dict[str, object]] = []
    payload = bytearray()
    for key, value in state.items():
        original = np.asarray(value)
        array = np.ascontiguousarray(original)
        raw = array.tobytes(order="C")
        entries.append(
            {
                "key": key,
                "shape": list(original.shape),
                "dtype": array.dtype.str,
                "nbytes": len(raw),
            }
        )
        payload.extend(raw)
    header = json.dumps(
        {"transport_id": FL_STATE_TRANSPORT_ID, "entries": entries},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _MAGIC + struct.pack(">Q", len(header)) + header + bytes(payload)


def deserialize_state(blob: bytes) -> OrderedDict[str, NDArray[np.generic]]:
    if not blob.startswith(_MAGIC) or len(blob) < len(_MAGIC) + 8:
        raise ValueError("invalid FL state payload")
    offset = len(_MAGIC)
    header_size = struct.unpack(">Q", blob[offset : offset + 8])[0]
    offset += 8
    header = json.loads(blob[offset : offset + header_size])
    offset += header_size
    if header.get("transport_id") != FL_STATE_TRANSPORT_ID:
        raise ValueError("transport-policy version mismatch")
    state: OrderedDict[str, NDArray[np.generic]] = OrderedDict()
    for entry in header["entries"]:
        nbytes = int(entry["nbytes"])
        raw = blob[offset : offset + nbytes]
        if len(raw) != nbytes:
            raise ValueError("truncated FL state payload")
        dtype = np.dtype(entry["dtype"])
        array = np.frombuffer(raw, dtype=dtype).reshape(tuple(entry["shape"])).copy()
        state[str(entry["key"])] = array
        offset += nbytes
    if offset != len(blob):
        raise ValueError("trailing FL state payload bytes")
    return state


def restore_state(model: torch.nn.Module, state: Mapping[str, NDArray[np.generic]]) -> None:
    expected = model_v1_state_spec(model)
    if list(state) != [entry.key for entry in expected]:
        raise ValueError("MODEL_V1 state key/order mismatch")
    tensors: OrderedDict[str, torch.Tensor] = OrderedDict()
    for entry in expected:
        array = np.asarray(state[entry.key])
        if array.shape != entry.shape or str(array.dtype) != entry.dtype:
            raise ValueError(f"MODEL_V1 state specification mismatch for {entry.key}")
        tensors[entry.key] = torch.from_numpy(np.array(array, copy=True))
    incompatible = model.load_state_dict(tensors, strict=True)
    if incompatible.missing_keys or incompatible.unexpected_keys:
        raise ValueError("MODEL_V1 state restoration mismatch")


def load_adapter_audit_model(root: Path) -> torch.nn.Module:
    model, _ = load_frozen_model_v1(root)
    return model


def fresh_model_v1() -> torch.nn.Module:
    return build_model_v1().eval()


def state_spec_as_dicts(model: torch.nn.Module) -> list[dict[str, object]]:
    return [asdict(entry) for entry in model_v1_state_spec(model)]
