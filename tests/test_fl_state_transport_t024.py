from __future__ import annotations

import numpy as np
import pytest

from federated.model_adapter import (
    deserialize_state,
    extract_state,
    fresh_model_v1,
    model_v1_state_spec,
    restore_state,
    serialize_state,
)


def test_model_v1_state_roles_and_order() -> None:
    model = fresh_model_v1()
    specs = model_v1_state_spec(model)
    assert [entry.key for entry in specs] == list(model.state_dict())
    assert len(specs) == 18
    assert sum(entry.aggregatable for entry in specs) == 16
    tracked = [entry for entry in specs if entry.key.endswith("num_batches_tracked")]
    assert len(tracked) == 2
    assert all(entry.state_role == "non_floating_buffer" for entry in tracked)
    assert all(not entry.aggregatable for entry in tracked)
    for name in ("bn1.running_mean", "bn1.running_var", "bn2.running_mean", "bn2.running_var"):
        entry = next(item for item in specs if item.key == name)
        assert entry.aggregatable and entry.state_role == "floating_buffer"


def test_serialization_is_deterministic_and_round_trips() -> None:
    state = extract_state(fresh_model_v1())
    blob1 = serialize_state(state)
    blob2 = serialize_state(state)
    assert blob1 == blob2
    restored = deserialize_state(blob1)
    assert list(restored) == list(state)
    for key in state:
        np.testing.assert_array_equal(restored[key], state[key])


def test_restore_rejects_specification_mutation() -> None:
    model = fresh_model_v1()
    state = extract_state(model)
    state["conv1.weight"] = state["conv1.weight"].astype(np.float64)
    with pytest.raises(ValueError, match="specification mismatch"):
        restore_state(model, state)

