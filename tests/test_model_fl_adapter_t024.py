from __future__ import annotations

from pathlib import Path

import numpy as np
import torch

from federated.model_adapter import (
    deserialize_state,
    extract_state,
    fresh_model_v1,
    load_adapter_audit_model,
    restore_state,
    serialize_state,
)

ROOT = Path(__file__).resolve().parents[1]


def test_model_v1_test_vector_survives_adapter_round_trip() -> None:
    original = load_adapter_audit_model(ROOT)
    with np.load(ROOT / "tests/fixtures/model_v1_test_vector.npz", allow_pickle=False) as fixture:
        inputs = torch.from_numpy(fixture["normalized_inputs_float32"])
    with torch.inference_mode():
        before = original(inputs).numpy()
    payload = serialize_state(extract_state(original))
    restored = fresh_model_v1()
    restore_state(restored, deserialize_state(payload))
    restored.eval()
    with torch.inference_mode():
        after = restored(inputs).numpy()
    np.testing.assert_array_equal(after, before)

