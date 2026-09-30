"""Current Flower ServerApp scaffold and deterministic local toy round."""

from __future__ import annotations

from typing import Any

import numpy as np
from flwr.app import ConfigRecord, Context, Message, Metadata, RecordDict
from flwr.common.serde import recorddict_from_proto, recorddict_to_proto
from flwr.serverapp import Grid, ServerApp

from federated.aggregation import ClientUpdate, aggregate_weighted_deltas
from federated.client_app import TOY_CLIENTS
from federated.client_app import app as client_app

app = ServerApp()


@app.main()
def main(grid: Grid, context: Context) -> None:
    """Future simulation entry point; T024 intentionally runs no real FL job."""

    del grid, context


def _flower_roundtrip(content: RecordDict) -> RecordDict:
    proto = recorddict_to_proto(content)
    return recorddict_from_proto(proto)


def run_toy_flower_round(client_ids: tuple[str, ...] = tuple(TOY_CLIENTS)) -> dict[str, Any]:
    """Exercise Flower Message/RecordDict transport and the canonical aggregator."""

    required = tuple(TOY_CLIENTS)
    if client_ids != required:
        raise RuntimeError("required two-client toy round is incomplete")
    updates: list[ClientUpdate] = []
    semantic_log: list[dict[str, object]] = []
    for node_id, client_id in enumerate(client_ids, start=1):
        request_content = _flower_roundtrip(
            RecordDict({"config": ConfigRecord({"client_id": client_id})})
        )
        metadata = Metadata(
            run_id=1,
            message_id=f"toy-request-{node_id}",
            src_node_id=0,
            dst_node_id=node_id,
            reply_to_message_id="",
            group_id="toy-round-1",
            created_at=0.0,
            ttl=3600.0,
            message_type="train.toy_delta",
        )
        request = Message(content=request_content, metadata=metadata)
        context = Context(
            run_id=1,
            node_id=node_id,
            node_config={"client_id": client_id},
            state=RecordDict(),
            run_config={"round": 1},
        )
        reply = client_app(request, context)
        response = _flower_roundtrip(reply.content)
        metadata = response["metadata"]
        arrays = response["delta"]
        delta = {key: value.numpy() for key, value in arrays.items()}
        update = ClientUpdate(
            client_id=str(metadata["client_id"]),
            num_examples=int(metadata["num_examples"]),
            delta=delta,
            transport_id=str(metadata["transport_id"]),
        )
        updates.append(update)
        semantic_log.append(
            {
                "client_id": update.client_id,
                "num_examples": update.num_examples,
                "delta": update.delta["vector"].tolist(),
            }
        )
    global_state = {"vector": np.asarray([10.0, 20.0], dtype=np.float32)}
    new_state, weighted_delta = aggregate_weighted_deltas(global_state, updates)
    return {
        "round": 1,
        "clients": semantic_log,
        "weighted_delta": weighted_delta["vector"].tolist(),
        "new_global": new_state["vector"].tolist(),
    }
