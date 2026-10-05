# ruff: noqa: E501
"""CAPSTONE_FL_CLIENT_COHORT_V1 -- the eight frozen V2-FL-005 clients as capstone FL clients.

Reuses simulation.fl_cohort_v1 (profiles), federated.wearable_sim_local_labels (observed source) and
federated.virtual_client_source_v1.build_local_dataset (the authoritative local dataset builder). No client,
participant, seed or distribution is invented. Datasets exist only inside the owning client buffer (process
memory); reference evidence is READ from the frozen V2-FL-005 files and never copied into new truth.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from federated.virtual_client_source_v1 import build_local_dataset
from federated.wearable_fl_runner_v1 import new_session
from federated.wearable_sim_local_labels import SyntheticObservedSource
from product.edge.label_adapter import SimulationLabelAdapterV1
from product.edge.local_training_buffer import LocalTrainingBufferV1
from product.edge.virtual import edge_identity_for_site
from product.federation.base import Algorithm
from product.federation.client import CapstoneFlClientAdapterV1
from simulation.fl_cohort_v1 import COHORT_ID, cohort_profiles

COHORT_BINDING_ID = "CAPSTONE_FL_CLIENT_COHORT_V1"
ROOT = Path(__file__).resolve().parents[2]
REFERENCE_DIR = ROOT / "reports/model_v2/v2_fl_005"


def reference_evidence() -> dict[str, Any]:
    cohort = json.loads((REFERENCE_DIR / "cohort_manifest_run.json").read_text())
    run = json.loads((REFERENCE_DIR / "federation_run.json").read_text())
    return {"cohort": cohort, "run": run, "round1": run["round_reports"]["1"],
            "fl_init_sha256": run["state_progression"]["0"]["sha256"]}


class _CountingSource(SyntheticObservedSource):
    count = 0

    def records(self):
        for record in super().records():
            self.count += 1
            yield record


def build_client(index: int, base_state, *, algorithm: Algorithm = Algorithm.FEDAVG
                 ) -> tuple[CapstoneFlClientAdapterV1, LocalTrainingBufferV1]:
    profile = cohort_profiles()[index]
    source = _CountingSource(profile)
    dataset = build_local_dataset(source, SimulationLabelAdapterV1(profile))
    dataset.counts["source_records"] = source.count
    buffer = LocalTrainingBufferV1(profile.client_id, profile.participant_id)
    buffer.ingest_dataset(dataset)
    identity = edge_identity_for_site(index)
    if identity.fl_client_id != profile.client_id or identity.participant_id != profile.participant_id:
        raise RuntimeError("EDGE_IDENTITY_MAPPING_MISMATCH")
    client = CapstoneFlClientAdapterV1(
        buffer, edge_node_id=identity.edge_node_id, participant_id=profile.participant_id,
        session_id=profile.session_id, base_state=base_state, base_model_id="FL_INIT_V2",
        algorithm=algorithm)
    return client, buffer


def build_cohort(base_state=None, *, algorithm: Algorithm = Algorithm.FEDAVG,
                 indices: range | tuple[int, ...] = range(8)):
    state = base_state if base_state is not None else new_session()[0]
    return state, [build_client(i, state, algorithm=algorithm) for i in indices]


__all__ = ["COHORT_BINDING_ID", "COHORT_ID", "build_client", "build_cohort", "reference_evidence"]
