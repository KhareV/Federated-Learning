from __future__ import annotations

import numpy as np
import pytest
from flwr.clientapp import ClientApp
from flwr.serverapp import ServerApp

from federated.aggregation import ClientUpdate, aggregate_weighted_deltas
from federated.client_app import app as client_app
from federated.server_app import app as server_app
from federated.server_app import run_toy_flower_round


def test_current_flower_app_objects_and_reference_equality() -> None:
    assert isinstance(client_app, ClientApp)
    assert isinstance(server_app, ServerApp)
    smoke = run_toy_flower_round()
    global_state = {"vector": np.asarray([10.0, 20.0], np.float32)}
    updates = [
        ClientUpdate("TOY_CLIENT_0", 2, {"vector": np.asarray([1.0, 3.0], np.float32)}),
        ClientUpdate("TOY_CLIENT_1", 6, {"vector": np.asarray([5.0, 7.0], np.float32)}),
    ]
    reference, _ = aggregate_weighted_deltas(global_state, updates)
    np.testing.assert_array_equal(smoke["new_global"], reference["vector"])


def test_flower_smoke_repeatability_and_required_clients() -> None:
    assert run_toy_flower_round() == run_toy_flower_round()
    with pytest.raises(RuntimeError, match="incomplete"):
        run_toy_flower_round(("TOY_CLIENT_0",))

