# ruff: noqa: E501
"""CAPSTONE_FL_CLIENT_ADAPTER_V2 -- additive successor of CAPSTONE_FL_CLIENT_ADAPTER_V1.

V1 is unchanged: it can only start from FL_INIT_V2. V2 is orchestration glue that accepts a ROUND base
state only after lineage verification (round 1 = FL_INIT_V2; round N>1 = the digest of the immediately
preceding committed round state; see ``execution_binding.verify_round_base``). Everything else is
inherited from V1 and therefore reused, not re-implemented: the local training buffer, the existing
``train_local_epoch_v2`` / ``train_local_fedprox_epoch_v2`` calls with the frozen hyperparameters, the
existing V2 update envelope and the forbidden-field scan. MODEL_V2_FINAL is never a legal base.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

import numpy as np

from federated.model_v2_fl import state_sha
from federated.wearable_fl_system_v1 import state_spec_sha
from product.edge.local_training_buffer import LocalTrainingBufferV1
from product.federation.base import Algorithm, ClientState
from product.federation.client import CapstoneFlClientAdapterV1, ClientError, frozen_fedprox_mu
from product.federation.execution_binding import BindingViolation, verify_round_base

ADAPTER_ID = "CAPSTONE_FL_CLIENT_ADAPTER_V2"


class CapstoneFlClientAdapterV2(CapstoneFlClientAdapterV1):
    """One adapter per client per round (the buffer persists, the base state is per round)."""

    def __init__(self, buffer: LocalTrainingBufferV1, *, edge_node_id: str, participant_id: str,
                 session_id: str, round_id: int, base_state: OrderedDict[str, np.ndarray],
                 committed: dict[int, str], base_model_id: str = "FL_INIT_V2",
                 algorithm: Algorithm = Algorithm.FEDAVG) -> None:
        if not isinstance(buffer, LocalTrainingBufferV1):
            raise ClientError("UNSUPPORTED_BUFFER_IMPLEMENTATION")
        try:
            verified = verify_round_base(round_id=round_id, state=base_state, committed=committed,
                                         base_model_id=base_model_id)
        except BindingViolation as error:
            raise ClientError(error.code) from error
        self._buffer = buffer
        self._edge_node_id, self._participant_id, self._session_id = (
            edge_node_id, participant_id, session_id)
        self._base_model_id, self._algorithm = base_model_id, algorithm
        self._mu = frozen_fedprox_mu() if algorithm is Algorithm.FEDPROX else None
        self._state = ClientState.IDLE
        self._round = 0
        self._base_state = base_state
        self._base_sha = verified
        assert state_sha(base_state) == verified
        self._spec_sha = state_spec_sha(base_state)
        self._result: Any = None
        self._envelope: dict[str, Any] | None = None
        self._ineligible: str | None = None
        self.round_id = round_id

    @property
    def state(self) -> ClientState:
        return self._state

    @property
    def examples_seen(self) -> int:
        return int(self._result.examples_seen)

    @property
    def update_result(self) -> Any:
        return self._result

    def envelope(self) -> dict[str, Any]:
        return self._envelope_for_bridge()

    def diagnostics(self) -> dict[str, Any]:
        return self._training_diagnostics()

    def reject(self) -> None:
        self._move(ClientState.REJECTED)

    def to_idle(self) -> None:
        self._move(ClientState.IDLE)
