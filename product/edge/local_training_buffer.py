# ruff: noqa: E501
"""LOCAL_TRAINING_BUFFER_V1 / CAPSTONE_LOCAL_BUFFER_BINDING_V1 -- client-local training buffer.

Canonical simulated storage mode: DETERMINISTIC LOCAL IN-MEMORY REGENERATION. Nothing here touches
central storage; no tensor, label or truth is ever written to the product database. Binding of the frozen
contract (the contract itself is unchanged):

* only TRAINABLE windows become records, so ``quality_eligible`` is always true; excluded windows are
  counted in the dataset manifest, never padded or relabelled into the buffer;
* ``model_input_ref`` is an opaque local reference (dataset sha + position + input digest); the float32
  [1, 2500] tensor stays in the buffer's PRIVATE store and is resolvable only by the owning client;
* ``window_id`` is deterministic (client + right-edge timestamp); no random UUIDs;
* one deterministic engineering batch per client: ``WEARABLE_SIM_FL_BATCH_0001__<client>__<sha12>``.

Locality is LOGICAL isolation on one machine (eight separate buffers, owner-checked reads); it is not
process, VM or hardware isolation.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from federated.virtual_client_source_v1 import LocalDataset, dataset_semantic_sha
from nhm.hashing import hash_bytes
from product.edge.buffer import (
    LabelSource,
    TrainingBufferRecord,
    forbidden_label_sources,
)

BUFFER_ID = "LOCAL_TRAINING_BUFFER_V1"
BINDING_ID = "CAPSTONE_LOCAL_BUFFER_BINDING_V1"
COHORT_SOURCE = "WEARABLE_SIM_FL_COHORT_V1"
SIM_VERSION = "WEARABLE_SIM_V1"
BATCH_PREFIX = "WEARABLE_SIM_FL_BATCH_0001"
REF_PREFIX = "LOCALREF"
INPUT_SHAPE = (1, 2500)


class BufferError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def window_id_for(client_id: str, right_edge_us: int) -> str:
    return f"{client_id}-W{int(right_edge_us):012d}"


def input_digest(window: np.ndarray) -> str:
    return hash_bytes(np.ascontiguousarray(window, dtype=np.float32).tobytes())


def batch_id_for(client_id: str, dataset_sha256: str) -> str:
    return f"{BATCH_PREFIX}__{client_id}__{dataset_sha256[:12]}"


def provenance_id_for(client_id: str, participant_id: str, dataset_sha256: str) -> str:
    return f"{COHORT_SOURCE}/{SIM_VERSION}/{client_id}/{participant_id}/{dataset_sha256[:16]}"


def input_ref_for(dataset_sha256: str, position: int, digest: str) -> str:
    return f"{REF_PREFIX}:{dataset_sha256[:16]}:{position:04d}:{digest[:16]}"


class LocalTrainingBufferV1:
    """Implements the frozen LocalTrainingBuffer protocol for ONE client."""

    def __init__(self, client_id: str, participant_id: str) -> None:
        self._client_id, self._participant_id = client_id, participant_id
        self._records: list[TrainingBufferRecord] = []
        self._batches: list[str] = []
        self._private: dict[str, np.ndarray] = {}        # model_input_ref -> float32 [1,2500]
        self._staged: dict[str, np.ndarray] = {}
        self.dataset_sha256: str | None = None
        self.counts: dict[str, Any] = {}

    @property
    def client_id(self) -> str:
        return self._client_id

    @property
    def participant_id(self) -> str:
        return self._participant_id

    def batch_ids(self) -> Sequence[str]:
        return tuple(self._batches)

    def eligible_count(self) -> int:
        return sum(1 for r in self._records if r.quality_eligible)

    def records(self) -> tuple[TrainingBufferRecord, ...]:
        return tuple(self._records)

    # ---- ingestion ------------------------------------------------------------------------
    def stage_private_inputs(self, tensors: Mapping[str, np.ndarray]) -> None:
        for ref, tensor in tensors.items():
            array = np.asarray(tensor, dtype=np.float32)
            if array.shape != INPUT_SHAPE:
                raise BufferError("MODEL_INPUT_SHAPE_INVALID")
            if not np.isfinite(array).all():
                raise BufferError("MODEL_INPUT_NONFINITE")
            self._staged[ref] = array

    def append_batch(self, records: Sequence[TrainingBufferRecord]) -> str:
        if not records:
            raise BufferError("EMPTY_BATCH")
        batch_ids = {r.buffer_batch_id for r in records}
        if len(batch_ids) != 1:
            raise BufferError("MIXED_BATCH_IDS")
        batch_id = next(iter(batch_ids))
        if batch_id in self._batches:
            raise BufferError("DUPLICATE_BATCH_ID")
        forbidden = set(forbidden_label_sources())
        for record in records:
            if record.client_id != self._client_id or record.participant_id != self._participant_id:
                raise BufferError("CROSS_CLIENT_RECORD")
            source = getattr(record.label_source, "value", record.label_source)
            if source in forbidden:
                raise BufferError("FORBIDDEN_LABEL_SOURCE")
            if record.simulation and source != LabelSource.SIMULATION_TRUTH_ENGINEERING.value:
                raise BufferError("SIMULATED_RECORD_REQUIRES_SIMULATION_TRUTH_ENGINEERING_LABEL")
            if not record.simulation and source == LabelSource.SIMULATION_TRUTH_ENGINEERING.value:
                raise BufferError("SIMULATION_LABEL_ON_REAL_DATA")
            if not record.quality_eligible:
                raise BufferError("NON_ELIGIBLE_RECORD_NOT_STORED")
            if record.model_input_ref not in self._staged:
                raise BufferError("MODEL_INPUT_REF_WITHOUT_PRIVATE_TENSOR")
        self._records.extend(records)
        self._batches.append(batch_id)
        for record in records:
            self._private[record.model_input_ref] = self._staged.pop(record.model_input_ref)
        self._staged.clear()
        return batch_id

    def ingest_dataset(self, dataset: LocalDataset) -> str:
        """Wrap the EXISTING client-local dataset (resampling/windowing/normalization/trainability and
        labels were all produced by the frozen federated code; nothing is recomputed here)."""
        if dataset.client_id != self._client_id or dataset.participant_id != self._participant_id:
            raise BufferError("CROSS_CLIENT_DATASET")
        sha = dataset.dataset_sha256
        if dataset_semantic_sha(dataset.inputs, dataset.labels, dataset.right_edges_us) != sha:
            raise BufferError("DATASET_SHA_MISMATCH")
        batch, provenance = batch_id_for(self._client_id, sha), provenance_id_for(
            self._client_id, self._participant_id, sha)
        records, tensors = [], {}
        for position, edge in enumerate(dataset.right_edges_us):
            window = dataset.inputs[position]
            ref = input_ref_for(sha, position, input_digest(window))
            tensors[ref] = np.array(window, dtype=np.float32, copy=True)
            records.append(TrainingBufferRecord(
                client_id=self._client_id, participant_id=self._participant_id, source=COHORT_SOURCE,
                window_id=window_id_for(self._client_id, edge), model_input_ref=ref,
                label=int(dataset.labels[position]),
                label_source=LabelSource.SIMULATION_TRUTH_ENGINEERING, quality_eligible=True,
                timestamp_us=int(edge), simulation=True, provenance_id=provenance,
                buffer_batch_id=batch))
        self.stage_private_inputs(tensors)
        self.append_batch(records)
        self.dataset_sha256 = sha
        self.counts = dict(dataset.counts)
        return batch

    # ---- private local reads (owner only) ----------------------------------------------------
    def resolve_input(self, ref: str, *, requester_client_id: str) -> np.ndarray:
        if requester_client_id != self._client_id:
            raise BufferError("CROSS_CLIENT_INPUT_ACCESS")
        if ref not in self._private:
            raise BufferError("UNKNOWN_MODEL_INPUT_REF")
        return self._private[ref]

    def training_arrays(self, *, requester_client_id: str) -> tuple[np.ndarray, np.ndarray]:
        if requester_client_id != self._client_id:
            raise BufferError("CROSS_CLIENT_INPUT_ACCESS")
        if not self._records:
            raise BufferError("EMPTY_BUFFER")
        inputs = np.stack([self._private[r.model_input_ref] for r in self._records]).astype(
            np.float32)
        labels = np.asarray([r.label for r in self._records], dtype=np.float32)
        return inputs, labels

    # ---- deterministic semantic digest (metadata only) -------------------------------------
    def semantic_digest(self) -> str:
        payload = [r.model_dump(mode="json") for r in self._records]
        return hash_bytes(json.dumps({"buffer": BUFFER_ID, "client_id": self._client_id,
                                      "batches": self._batches, "records": payload},
                                     sort_keys=True, separators=(",", ":")).encode())

    def manifest(self) -> dict[str, Any]:
        labels = [r.label for r in self._records]
        return {"client_id": self._client_id, "participant_id": self._participant_id,
                "buffer_batch_ids": list(self._batches), "dataset_sha256": self.dataset_sha256,
                "buffer_semantic_sha256": self.semantic_digest(), "record_count": len(self._records),
                "eligible_count": self.eligible_count(),
                "synthetic_positive": int(sum(labels)),
                "synthetic_negative": len(labels) - int(sum(labels)),
                "all_quality_eligible": all(r.quality_eligible for r in self._records),
                "label_sources": sorted({r.label_source.value for r in self._records}),
                "simulation_only": all(r.simulation for r in self._records),
                "provenance_ids": sorted({r.provenance_id for r in self._records}),
                "refs_are_opaque": all(r.model_input_ref.startswith(REF_PREFIX + ":")
                                       for r in self._records),
                "storage_mode": "DETERMINISTIC_LOCAL_IN_MEMORY_REGENERATION",
                "storage_location": "process memory only (never central SQLite)"}
