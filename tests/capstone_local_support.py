# ruff: noqa: E501
"""Shared CAP-006 test support. Buffers are built ONCE per process (deterministic regeneration of the frozen
V2-FL-005 clients); clients are cheap and fresh per test. Tiny synthetic buffers exercise failure paths."""

from __future__ import annotations

import functools

import numpy as np

from federated.virtual_client_source_v1 import LocalDataset, dataset_semantic_sha
from federated.wearable_fl_runner_v1 import new_session
from product.edge.local_training_buffer import LocalTrainingBufferV1
from product.edge.virtual import edge_identity_for_site
from product.federation.base import Algorithm
from product.federation.client import CapstoneFlClientAdapterV1
from product.federation.local_cohort import build_client


@functools.cache
def base_state():
    return new_session()[0]


@functools.cache
def cohort_buffers() -> tuple[LocalTrainingBufferV1, ...]:
    state = base_state()
    return tuple(build_client(i, state)[1] for i in range(8))


def fresh_client(index: int, buffer: LocalTrainingBufferV1 | None = None,
                 algorithm: Algorithm = Algorithm.FEDAVG) -> CapstoneFlClientAdapterV1:
    buf = buffer or cohort_buffers()[index]
    identity = edge_identity_for_site(index)
    return CapstoneFlClientAdapterV1(
        buf, edge_node_id=identity.edge_node_id, participant_id=buf.participant_id,
        session_id=f"SIM_S_FL_{index:02d}_000001", base_state=base_state(), algorithm=algorithm)


def tiny_dataset(client_id: str = "SIM_FL_SITE_00", participant_id: str = "SIM_P000101", n: int = 40,
                 seed: int = 7) -> LocalDataset:
    rng = np.random.default_rng(seed)
    inputs = rng.standard_normal((n, 1, 2500)).astype(np.float32)
    labels = (np.arange(n) % 3 == 0).astype(np.float32)
    edges = tuple(10_000_000 + 5_000_000 * i for i in range(n))
    return LocalDataset(client_id, participant_id, "SIM_S_TEST", inputs, labels, edges,
                        {"trainable": n}, dataset_semantic_sha(inputs, labels, edges))


def tiny_buffer(n: int = 40, client_id: str = "SIM_FL_SITE_00",
                participant_id: str = "SIM_P000101") -> LocalTrainingBufferV1:
    buffer = LocalTrainingBufferV1(client_id, participant_id)
    buffer.ingest_dataset(tiny_dataset(client_id, participant_id, n))
    return buffer
