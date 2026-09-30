"""Current Flower ClientApp scaffold for deterministic T024 toy clients."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from flwr.app import Array, ArrayRecord, ConfigRecord, Context, Message, Metadata, RecordDict
from flwr.clientapp import ClientApp

from federated.aggregation import FL_STATE_TRANSPORT_ID

app = ClientApp()


@dataclass(frozen=True)
class ToyClient:
    client_id: str
    num_examples: int
    vector_delta: tuple[float, float]


TOY_CLIENTS = {
    "TOY_CLIENT_0": ToyClient("TOY_CLIENT_0", 2, (1.0, 3.0)),
    "TOY_CLIENT_1": ToyClient("TOY_CLIENT_1", 6, (5.0, 7.0)),
}


@app.train("toy_delta")
def toy_delta(message: Message, context: Context) -> Message:
    """Return a deterministic model delta; no data loading or training occurs."""

    del context
    request = message.content["config"]
    if not isinstance(request, ConfigRecord):
        raise TypeError("toy request config missing")
    client_id = str(request["client_id"])
    client = TOY_CLIENTS.get(client_id)
    if client is None:
        raise ValueError("unknown toy client")
    delta = np.asarray(client.vector_delta, dtype=np.float32)
    content = RecordDict(
        {
            "delta": ArrayRecord(array_dict={"vector": Array(ndarray=delta)}),
            "metadata": ConfigRecord(
                {
                    "client_id": client.client_id,
                    "num_examples": client.num_examples,
                    "transport_id": FL_STATE_TRANSPORT_ID,
                }
            ),
        }
    )
    reply_metadata = Metadata(
        run_id=message.metadata.run_id,
        message_id="toy-reply",
        src_node_id=message.metadata.dst_node_id,
        dst_node_id=message.metadata.src_node_id,
        reply_to_message_id=message.metadata.message_id,
        group_id=message.metadata.group_id,
        created_at=1.0,
        ttl=3600.0,
        message_type=message.metadata.message_type,
    )
    return Message(content=content, metadata=reply_metadata)
