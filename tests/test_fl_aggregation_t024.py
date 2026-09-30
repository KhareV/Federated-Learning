from __future__ import annotations

from collections import OrderedDict

import numpy as np
import pytest

from federated.aggregation import (
    FL_STATE_TRANSPORT_ID,
    AggregationError,
    ClientUpdate,
    aggregate_weighted_deltas,
)


def _analytical_updates() -> tuple[dict[str, np.ndarray], list[ClientUpdate]]:
    global_state = {"vector": np.asarray([10.0, 20.0], dtype=np.float32)}
    updates = [
        ClientUpdate("TOY_CLIENT_0", 2, {"vector": np.asarray([1.0, 3.0], dtype=np.float32)}),
        ClientUpdate("TOY_CLIENT_1", 6, {"vector": np.asarray([5.0, 7.0], dtype=np.float32)}),
    ]
    return global_state, updates


def test_two_client_analytical_sample_weighted_delta() -> None:
    global_state, updates = _analytical_updates()
    new_state, weighted = aggregate_weighted_deltas(global_state, updates)
    np.testing.assert_array_equal(weighted["vector"], np.asarray([4.0, 6.0], np.float32))
    np.testing.assert_array_equal(new_state["vector"], np.asarray([14.0, 26.0], np.float32))


def test_multi_tensor_bn_transport_and_full_state_equivalence() -> None:
    global_state = OrderedDict(
        weight=np.asarray([[1.0, 2.0]], np.float32),
        bias=np.asarray([0.0], np.float32),
        running_mean=np.asarray([4.0], np.float32),
        running_var=np.asarray([2.0], np.float32),
        num_batches_tracked=np.asarray(9, np.int64),
    )
    delta_a = OrderedDict(
        weight=np.asarray([[1.0, 3.0]], np.float32),
        bias=np.asarray([2.0], np.float32),
        running_mean=np.asarray([1.0], np.float32),
        running_var=np.asarray([2.0], np.float32),
        num_batches_tracked=np.asarray(99, np.int64),
    )
    delta_b = OrderedDict(
        weight=np.asarray([[5.0, 7.0]], np.float32),
        bias=np.asarray([6.0], np.float32),
        running_mean=np.asarray([5.0], np.float32),
        running_var=np.asarray([6.0], np.float32),
        num_batches_tracked=np.asarray(101, np.int64),
    )
    updates = [ClientUpdate("a", 2, delta_a), ClientUpdate("b", 6, delta_b)]
    new_state, weighted = aggregate_weighted_deltas(global_state, updates)
    np.testing.assert_array_equal(weighted["weight"], [[4.0, 6.0]])
    np.testing.assert_array_equal(weighted["running_mean"], [4.0])
    np.testing.assert_array_equal(weighted["running_var"], [5.0])
    assert new_state["num_batches_tracked"].item() == 9
    assert weighted["num_batches_tracked"].item() == 0

    local_a = global_state["weight"] + delta_a["weight"]
    local_b = global_state["weight"] + delta_b["weight"]
    full_state_mean = (2 * local_a + 6 * local_b) / 8
    np.testing.assert_allclose(new_state["weight"], full_state_mean, rtol=0, atol=0)


@pytest.mark.parametrize("count", [0, -1, 1.5, True, float("nan")])
def test_bad_sample_count_rejected(count: object) -> None:
    global_state, updates = _analytical_updates()
    bad = ClientUpdate("bad", count, updates[0].delta)  # type: ignore[arg-type]
    with pytest.raises(AggregationError, match="num_examples"):
        aggregate_weighted_deltas(global_state, [bad])


def test_state_and_transport_failures() -> None:
    global_state, updates = _analytical_updates()
    fixtures = [
        ClientUpdate("missing", 1, {}),
        ClientUpdate("extra", 1, {"vector": updates[0].delta["vector"], "x": np.array(1.0)}),
        ClientUpdate("shape", 1, {"vector": np.asarray([1.0], np.float32)}),
        ClientUpdate("dtype", 1, {"vector": np.asarray([1.0, 3.0], np.float64)}),
        ClientUpdate("nan", 1, {"vector": np.asarray([np.nan, 3.0], np.float32)}),
        ClientUpdate("inf", 1, {"vector": np.asarray([np.inf, 3.0], np.float32)}),
        ClientUpdate("transport", 1, updates[0].delta, "FL_STATE_TRANSPORT_V0"),
    ]
    for fixture in fixtures:
        with pytest.raises(AggregationError):
            aggregate_weighted_deltas(global_state, [fixture])


def test_inputs_are_immutable_and_key_order_is_server_canonical() -> None:
    global_state = OrderedDict(
        first=np.asarray([1.0], np.float32), second=np.asarray([2.0], np.float32)
    )
    reversed_delta = OrderedDict(
        second=np.asarray([4.0], np.float32), first=np.asarray([3.0], np.float32)
    )
    before_global = {key: value.copy() for key, value in global_state.items()}
    before_delta = {key: value.copy() for key, value in reversed_delta.items()}
    new_state, _ = aggregate_weighted_deltas(
        global_state,
        [ClientUpdate("client", 1, reversed_delta, FL_STATE_TRANSPORT_ID)],
    )
    assert list(new_state) == ["first", "second"]
    for key in global_state:
        np.testing.assert_array_equal(global_state[key], before_global[key])
        np.testing.assert_array_equal(reversed_delta[key], before_delta[key])

