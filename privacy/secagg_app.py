"""Actual Flower 1.39 SecAgg+ workflow harness for controlled simulation."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import numpy as np
from flwr.app import ConfigRecord, Context, Message, RecordDict
from flwr.client.mod import secaggplus_mod
from flwr.common import (
    Code,
    FitIns,
    FitRes,
    Status,
    ndarrays_to_parameters,
    parameters_to_ndarrays,
)
from flwr.common.serde import recorddict_from_proto, recorddict_to_proto
from flwr.compat.common import recorddict_compat as compat
from flwr.server.client_manager import SimpleClientManager
from flwr.server.client_proxy import ClientProxy
from flwr.server.compat.legacy_context import LegacyContext
from flwr.server.strategy import FedAvg
from flwr.server.workflow import SecAggPlusWorkflow
from flwr.server.workflow.constant import MAIN_CONFIGS_RECORD, MAIN_PARAMS_RECORD
from flwr.server.workflow.constant import Key as WorkflowKey
from flwr.serverapp.grid import Grid
from flwr.supercore.task_identity import TaskIdentity

from privacy.accounting import PayloadCounter
from privacy.server_visibility import ServerVisibilityProbe

PROTECTED_PATH_ID = "FLOWER_SECAGGPLUS_V1"
PLAIN_PATH_ID = "PLAIN_REFERENCE_V1"


class _Proxy(ClientProxy):
    def __init__(self, node_id: int) -> None:
        super().__init__(str(node_id))
        self.node_id = node_id

    def get_properties(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    def get_parameters(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    def fit(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    def evaluate(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    def reconnect(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError


class _AggregateStrategy(FedAvg):
    """All FitRes parameters are the one SecAgg+ aggregate; return it once."""

    def aggregate_fit(self, server_round: int, results: list[Any], failures: list[Any]) -> Any:
        del server_round
        if failures or len(results) != 8:
            raise RuntimeError("protected round requires all eight clients")
        arrays = [parameters_to_ndarrays(result.parameters) for _, result in results]
        first = arrays[0]
        for candidate in arrays[1:]:
            if len(candidate) != len(first) or any(
                not np.array_equal(left, right)
                for left, right in zip(first, candidate, strict=True)
            ):
                raise RuntimeError("Flower aggregate compatibility payload mismatch")
        return results[0][1].parameters, {}


@dataclass(frozen=True)
class ClientPayload:
    client_id: str
    node_id: int
    arrays: tuple[np.ndarray, ...]
    num_examples: int


class InMemorySecAggGrid(Grid):
    """Flower Grid dispatching messages through the actual secaggplus_mod."""

    def __init__(self, payloads: list[ClientPayload], probe: ServerVisibilityProbe) -> None:
        self.payloads = {payload.node_id: payload for payload in payloads}
        self.contexts = {
            payload.node_id: Context(
                run_id=28,
                node_id=payload.node_id,
                node_config={"client_id": payload.client_id},
                state=RecordDict(),
                run_config={},
            )
            for payload in payloads
        }
        self.probe = probe
        self.counter = PayloadCounter()
        self.stage_calls = 0

    def set_run(self, run: Any) -> None:
        del run

    @property
    def run(self) -> Any:
        return None

    def create_message(self, *args: Any, **kwargs: Any) -> Message:
        raise NotImplementedError

    def get_node_ids(self) -> Iterable[int]:
        return self.payloads

    def push_messages(self, messages: Iterable[Message]) -> Iterable[str]:
        raise NotImplementedError

    def pull_messages(self, message_ids: Iterable[str]) -> Iterable[Message]:
        raise NotImplementedError

    def send_and_receive(
        self, messages: Iterable[Message], *, timeout: float | None = None
    ) -> Iterable[Message]:
        del timeout
        replies: list[Message] = []
        self.stage_calls += 1
        for original in messages:
            self.counter.observe_server_to_client(original)
            node_id = original.metadata.dst_node_id
            payload = self.payloads[node_id]
            # A transport round trip isolates mutable records between clients.
            content = recorddict_from_proto(recorddict_to_proto(original.content))
            request = Message(
                content=content,
                dst_node_id=node_id,
                message_type=original.metadata.message_type,
                group_id=original.metadata.group_id,
            )

            def train(
                message: Message, context: Context, client_payload: ClientPayload = payload
            ) -> Message:
                del context
                fitres = FitRes(
                    status=Status(Code.OK, ""),
                    parameters=ndarrays_to_parameters(list(client_payload.arrays)),
                    num_examples=client_payload.num_examples,
                    metrics={},
                )
                return Message(content=compat.fitres_to_recorddict(fitres, True), reply_to=message)

            reply = secaggplus_mod(request, self.contexts[node_id], train)
            self.probe.observe_protected_reply(reply)
            self.counter.observe_client_to_server(reply)
            replies.append(reply)
        return replies


def run_flower_secaggplus(
    payloads: list[ClientPayload],
    initial_arrays: list[np.ndarray],
    *,
    num_shares: int = 5,
    reconstruction_threshold: int = 4,
    max_weight: float = 4096.0,
    clipping_range: float = 8.0,
    quantization_range: int = 2**22,
    modulus_range: int = 2**32,
    timeout: float | None = None,
) -> tuple[list[np.ndarray], ServerVisibilityProbe, dict[str, int | str], int]:
    if len(payloads) != 8:
        raise ValueError("T028 requires exactly eight clients")
    TaskIdentity.run_id = 28
    TaskIdentity.node_id = 0
    TaskIdentity.task_id = 28
    manager = SimpleClientManager()
    for payload in payloads:
        manager.register(_Proxy(payload.node_id))
    strategy = _AggregateStrategy(
        fraction_fit=1.0,
        min_fit_clients=8,
        min_available_clients=8,
        accept_failures=False,
    )
    base = Context(run_id=28, node_id=0, node_config={}, state=RecordDict(), run_config={})
    base.state.array_records[MAIN_PARAMS_RECORD] = compat.parameters_to_arrayrecord(
        ndarrays_to_parameters(initial_arrays), True
    )
    base.state.config_records[MAIN_CONFIGS_RECORD] = ConfigRecord({WorkflowKey.CURRENT_ROUND: 1})
    context = LegacyContext(base, strategy=strategy, client_manager=manager)
    probe = ServerVisibilityProbe(PROTECTED_PATH_ID)
    grid = InMemorySecAggGrid(payloads, probe)
    workflow = SecAggPlusWorkflow(
        num_shares,
        reconstruction_threshold,
        max_weight=max_weight,
        clipping_range=clipping_range,
        quantization_range=quantization_range,
        modulus_range=modulus_range,
        timeout=timeout,
    )
    workflow(grid, context)
    aggregate = context.state.array_records[MAIN_PARAMS_RECORD].to_numpy_ndarrays()
    probe.observe_aggregate()
    return aggregate, probe, grid.counter.as_dict(), grid.stage_calls


def run_plain_reference(
    payloads: list[ClientPayload], initial_arrays: list[np.ndarray] | None = None
) -> tuple[list[np.ndarray], ServerVisibilityProbe, dict[str, int | str]]:
    if len(payloads) != 8:
        raise ValueError("plain negative control requires eight clients")
    probe = ServerVisibilityProbe(PLAIN_PATH_ID)
    counter = PayloadCounter()
    TaskIdentity.run_id = 28
    TaskIdentity.node_id = 0
    TaskIdentity.task_id = 28
    if initial_arrays is None:
        initial_arrays = [np.zeros_like(array) for array in payloads[0].arrays]
    parameters = ndarrays_to_parameters(initial_arrays)
    for payload in payloads:
        request = Message(
            content=compat.fitins_to_recorddict(FitIns(parameters, {}), False),
            dst_node_id=payload.node_id,
            message_type="train",
            group_id="1",
        )
        counter.observe_server_to_client(request)
        fitres = FitRes(
            status=Status(Code.OK, ""),
            parameters=ndarrays_to_parameters(list(payload.arrays)),
            num_examples=payload.num_examples,
            metrics={},
        )
        reply = Message(content=compat.fitres_to_recorddict(fitres, False), reply_to=request)
        counter.observe_client_to_server(reply)
    total = sum(payload.num_examples for payload in payloads)
    aggregate = [
        sum(
            np.asarray(payload.arrays[index], dtype=np.float64) * payload.num_examples
            for payload in payloads
        )
        / total
        for index in range(len(payloads[0].arrays))
    ]
    for payload in payloads:
        probe.observe_plain_update(payload.node_id, has_arrays=True, has_weight=True)
    probe.observe_aggregate()
    return aggregate, probe, counter.as_dict()
