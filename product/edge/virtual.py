"""VIRTUAL_EDGE_NODE_V1 -- the simulated edge compute entity (EDGE_NODE_CONTRACT_V1).

Owns a DeviceSource, an edge identity, the LIVE record/event boundary, and a DISABLED local
training-buffer boundary. CAP-002 implements ONLY the live flow:

    DeviceSource -> ObservedRecord -> live_records()      (consumed by the existing stream runtime)

The training tee is a no-op boundary that cannot persist labels or accept records (CAP-006 owns the
buffer). Nothing here trains, touches FL state, imports FL/server modules, or reads SimulationTruth.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence

from product.contracts import load_contract
from product.devices.base import DeviceEvent, DeviceSource, DeviceState
from product.edge.base import EdgeNodeIdentity, EdgeNodeKind
from product.edge.buffer import LocalTrainingBuffer, TrainingBufferRecord
from simulation.types import ObservedRecord

MONITORING_EDGE_NODE_ID = "VIRTUAL_EDGE_NODE_00"


class TrainingBufferDisabledError(RuntimeError):
    """The local training buffer is a CAP-006 deliverable; CAP-002 edge nodes cannot buffer."""


class DisabledTrainingBuffer:
    """Frozen-interface placeholder: satisfies LocalTrainingBuffer, stores nothing."""

    def __init__(self, client_id: str) -> None:
        self._client_id = client_id

    @property
    def client_id(self) -> str:
        return self._client_id

    def append_batch(self, records: Sequence[TrainingBufferRecord]) -> str:
        raise TrainingBufferDisabledError("LOCAL_TRAINING_BUFFER_IS_IMPLEMENTED_IN_CAP_006")

    def batch_ids(self) -> Sequence[str]:
        return ()

    def eligible_count(self) -> int:
        return 0


def monitoring_edge_identity(device_id: str) -> EdgeNodeIdentity:
    """Primary product-monitoring node (not mapped to an FL cohort participant)."""
    return EdgeNodeIdentity(edge_node_id=MONITORING_EDGE_NODE_ID,
                            kind=EdgeNodeKind.VIRTUAL_EDGE_NODE, device_id=device_id,
                            simulation=True)


def edge_identity_for_site(index: int, device_id: str | None = None) -> EdgeNodeIdentity:
    """FL-compatible identity from the frozen CAP-001 cohort mapping (SIM_FL_SITE_NN <->
    SIM_P0001NN). Identity/mapping only; no second client universe is created."""
    mapping = load_contract("edge_node")["simulated_cohort_mapping"]["mapping"]
    if not 0 <= index < len(mapping):
        raise ValueError("SITE_INDEX_OUT_OF_RANGE")
    row = mapping[index]
    return EdgeNodeIdentity(edge_node_id=row["edge_node_id"], kind=EdgeNodeKind.VIRTUAL_EDGE_NODE,
                            device_id=device_id, fl_client_id=row["fl_client_id"],
                            participant_id=row["participant_id"], simulation=True)


class VirtualEdgeNode:
    def __init__(self, identity: EdgeNodeIdentity, device_source: DeviceSource) -> None:
        if identity.kind is not EdgeNodeKind.VIRTUAL_EDGE_NODE or not identity.simulation:
            raise ValueError("VIRTUAL_EDGE_NODE_REQUIRES_A_SIMULATED_IDENTITY")
        if not isinstance(device_source, DeviceSource):
            raise TypeError("DEVICE_SOURCE_PROTOCOL_NOT_SATISFIED")
        self._identity = identity
        self._source = device_source
        self._buffer = DisabledTrainingBuffer(identity.fl_client_id or identity.edge_node_id)

    @property
    def identity(self) -> EdgeNodeIdentity:
        return self._identity

    @property
    def device_source(self) -> DeviceSource:
        return self._source

    @property
    def training_buffer(self) -> LocalTrainingBuffer:
        return self._buffer

    async def attach(self, timeout_s: float = 0.0) -> None:
        """scan -> FOUND -> connect (PAIRING -> CONNECTED), from whichever legal start state."""
        state = self._source.connection_state
        if state is DeviceState.DETACHED:
            found = await self._source.scan(timeout_s)
            await self._source.connect(found[0].device_id)
        elif state in (DeviceState.FOUND, DeviceState.STOPPED):
            await self._source.connect(self._source.descriptor.device_id)

    async def start_live_monitoring(self, session_id: str) -> None:
        await self.attach()
        await self._source.start_stream(session_id)

    async def stop_live_monitoring(self) -> None:
        await self._source.stop_stream()

    def live_records(self) -> AsyncIterator[ObservedRecord]:
        return self._source.records()

    def live_events(self) -> AsyncIterator[DeviceEvent]:
        return self._source.events()
