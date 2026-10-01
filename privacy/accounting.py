"""Deterministic Flower application-record byte accounting for T028."""

from __future__ import annotations

from dataclasses import dataclass

from flwr.app import Message
from flwr.common.serde import message_to_proto

ACCOUNTING_ID = "FLOWER_APPLICATION_PAYLOAD_BYTES_V1"


def message_payload_bytes(message: Message) -> int:
    """Return exact serialized Flower Message protobuf bytes at the App boundary."""

    return len(message_to_proto(message).SerializeToString(deterministic=True))


@dataclass
class PayloadCounter:
    client_to_server: int = 0
    server_to_client: int = 0

    def observe_server_to_client(self, message: Message) -> None:
        self.server_to_client += message_payload_bytes(message)

    def observe_client_to_server(self, message: Message) -> None:
        self.client_to_server += message_payload_bytes(message)

    def as_dict(self) -> dict[str, int | str]:
        return {
            "accounting_id": ACCOUNTING_ID,
            "client_to_server": self.client_to_server,
            "server_to_client": self.server_to_client,
            "total": self.client_to_server + self.server_to_client,
        }
