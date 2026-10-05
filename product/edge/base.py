"""EDGE_NODE_CONTRACT_V1 -- the edge/client plane.

A wearable is an ACQUISITION SOURCE; a federated client is an EDGE COMPUTE ENTITY. Today:
Virtual Wearable -> Virtual Edge Node -> FL Client. Future: Physical Wearable -> phone/laptop/
edge gateway -> FL client. An ESP32-class sensor is never assumed to run PyTorch training.

The live-inference data flow and the local-training data flow are separate: training can never
alter a live monitoring session's state.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from product.devices.base import DeviceSource
from product.edge.buffer import LocalTrainingBuffer


class EdgeNodeKind(StrEnum):
    VIRTUAL_EDGE_NODE = "VIRTUAL_EDGE_NODE"
    REAL_EDGE_GATEWAY = "REAL_EDGE_GATEWAY"


class EdgeNodeIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    edge_node_id: str = Field(min_length=1)
    kind: EdgeNodeKind
    device_id: str | None = None
    fl_client_id: str | None = None
    participant_id: str | None = None
    simulation: bool

    @model_validator(mode="after")
    def _kind_matches_simulation_flag(self) -> EdgeNodeIdentity:
        if (self.kind is EdgeNodeKind.VIRTUAL_EDGE_NODE) != self.simulation:
            raise ValueError("EDGE_NODE_KIND_MUST_MATCH_SIMULATION_FLAG")
        return self


@runtime_checkable
class EdgeNode(Protocol):
    @property
    def identity(self) -> EdgeNodeIdentity: ...

    @property
    def device_source(self) -> DeviceSource: ...

    @property
    def training_buffer(self) -> LocalTrainingBuffer: ...

    async def start_live_monitoring(self, session_id: str) -> None: ...

    async def stop_live_monitoring(self) -> None: ...
