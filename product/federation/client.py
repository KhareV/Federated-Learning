# ruff: noqa: E501
"""CAPSTONE_FL_CLIENT_ADAPTER_V1 -- product adapter over the EXISTING V2 FL local-training path.

Reuse, not reimplementation: local FedAvg is ``federated.model_v2_fl.train_local_epoch_v2`` and local
FedProx is ``federated.model_v2_fedprox.train_local_fedprox_epoch_v2`` with the frozen V2-FL-005
hyperparameters, and the update wire format is the existing V2 envelope
(``federated.wearable_fl_system_v1.make_envelope``).

Scope (CAP-006): LOCAL TRAINING ONLY. This class never submits to a coordinator, never aggregates, never
touches SecAgg, creates no federation run and no candidate model. It trains from FL_INIT_V2 (NOT
MODEL_V2_FINAL): a client update is a model DELTA, not a global/candidate/released model. The clients are the
synthetic SIM_FL_SITE_00..07 research partitions - not the logged-in user, not a patient, not personalised.
"""

from __future__ import annotations

import json
from collections import OrderedDict
from pathlib import Path
from typing import Any

import numpy as np

from federated.model_v2_fedprox import train_local_fedprox_epoch_v2
from federated.model_v2_fl import state_sha, train_local_epoch_v2
from federated.wearable_fl_runner_v1 import (
    BASE_SEED,
    BATCH_SIZE,
    LEARNING_RATE,
    POS_WEIGHT,
    WEIGHT_DECAY,
)
from federated.wearable_fl_system_v1 import (
    EXPERIMENT_ID,
    delta_sha,
    make_envelope,
    scan_forbidden,
    state_spec_sha,
)
from product.edge.buffer import LocalTrainingBuffer
from product.edge.local_training_buffer import BufferError, LocalTrainingBufferV1
from product.federation.base import (
    Algorithm,
    ClientState,
    FLClientIdentity,
    UpdateSubmission,
    validate_client_transition,
)

ADAPTER_ID = "CAPSTONE_FL_CLIENT_ADAPTER_V1"
ALLOWED_BASE_MODEL_IDS = ("FL_INIT_V2",)   # until a CAPSTONE_FL_CANDIDATE exists (later phases)
ROOT = Path(__file__).resolve().parents[2]
MU_LOCK = ROOT / "artifacts/FEDPROX_MU_V2.lock.json"
INELIGIBLE_NO_EXAMPLES = "NONPOSITIVE_EXAMPLES"   # existing REJECTION_ORDER vocabulary


class ClientError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def frozen_fl_init_sha() -> str:
    """FL_INIT_V2 round-0 state sha256 from the frozen lock (also asserted equal to V2-FL-005 evidence)."""
    return str(json.loads(MU_LOCK.read_text())["FL_INIT_V2_round_0_state_sha256"])


def frozen_fedprox_mu() -> float:
    """FEDPROX_MU_V2 selected_mu from the frozen lock (never searched, never edited)."""
    return float(json.loads(MU_LOCK.read_text())["selected_mu"])


class CapstoneFlClientAdapterV1:
    def __init__(self, buffer: LocalTrainingBuffer, *, edge_node_id: str, participant_id: str,
                 session_id: str, base_state: OrderedDict[str, np.ndarray],
                 base_model_id: str = "FL_INIT_V2", algorithm: Algorithm = Algorithm.FEDAVG) -> None:
        if base_model_id not in ALLOWED_BASE_MODEL_IDS:
            raise ClientError("BASE_MODEL_NOT_ALLOWED")
        if not isinstance(buffer, LocalTrainingBufferV1):
            raise ClientError("UNSUPPORTED_BUFFER_IMPLEMENTATION")
        self._buffer = buffer
        self._edge_node_id, self._participant_id, self._session_id = (
            edge_node_id, participant_id, session_id)
        self._base_model_id, self._algorithm = base_model_id, algorithm
        self._mu = frozen_fedprox_mu() if algorithm is Algorithm.FEDPROX else None
        self._state = ClientState.IDLE
        self._round = 0
        self._base_state = base_state
        self._base_sha = state_sha(base_state)
        if self._base_sha != frozen_fl_init_sha():
            raise ClientError("BASE_STATE_NOT_FL_INIT_V2")
        self._spec_sha = state_spec_sha(base_state)
        self._result: Any = None
        self._envelope: dict[str, Any] | None = None
        self._ineligible: str | None = None

    # ---- FLClient protocol ----------------------------------------------------------------
    @property
    def identity(self) -> FLClientIdentity:
        eligible = self._ineligible is None and self._buffer.eligible_count() > 0
        reason = None if eligible else (self._ineligible or INELIGIBLE_NO_EXAMPLES)
        digest = self._envelope["update_sha256"] if self._envelope else None
        return FLClientIdentity(
            client_id=self._buffer.client_id, edge_node_id=self._edge_node_id,
            base_model_id=self._base_model_id, global_round=self._round,
            local_example_count=self._buffer.eligible_count(), client_state=self._state,
            update_digest=digest, eligible=eligible, ineligible_reason=reason)

    @property
    def base_state_sha(self) -> str:
        return self._base_sha

    def _move(self, new: ClientState) -> None:
        validate_client_transition(self._state, new)
        self._state = new

    def prepare(self) -> None:
        """IDLE -> DATA_READY (buffer exists, eligible > 0, owner matches, provenance valid, base bound)."""
        if self._buffer.eligible_count() <= 0:
            self._ineligible = INELIGIBLE_NO_EXAMPLES
            raise ClientError("NO_ELIGIBLE_EXAMPLES")
        records = self._buffer.records()
        if any(r.client_id != self._buffer.client_id or not r.simulation for r in records):
            raise ClientError("BUFFER_PROVENANCE_INVALID")
        if not self._buffer.dataset_sha256:
            raise ClientError("BUFFER_PROVENANCE_INVALID")
        self._move(ClientState.DATA_READY)

    async def local_train(self, round_id: int, base_state_digest: str) -> None:
        if self._state is not ClientState.DATA_READY:
            raise ClientError("CLIENT_NOT_DATA_READY")
        if not isinstance(round_id, int) or isinstance(round_id, bool) or round_id < 1:
            raise ClientError("ROUND_INVALID")
        if base_state_digest != self._base_sha:
            raise ClientError("BASE_STATE_MISMATCH")
        try:
            inputs, labels = self._buffer.training_arrays(requester_client_id=self._buffer.client_id)
            if inputs.ndim != 3 or inputs.shape[1:] != (1, 2500) or inputs.shape[0] == 0:
                raise ClientError("DATASET_SHAPE_INVALID")
            if labels.shape != (inputs.shape[0],):
                raise ClientError("LABELS_MISALIGNED")
            if not np.isfinite(inputs).all():
                raise ClientError("NONFINITE_LOCAL_INPUT")
        except (BufferError, ClientError):
            raise
        self._move(ClientState.TRAINING)
        try:
            common = {"global_state": self._base_state, "inputs": inputs, "labels": labels,
                      "site_id": self._buffer.client_id, "round_number": round_id,
                      "experiment_id": EXPERIMENT_ID, "base_seed": BASE_SEED, "batch_size": BATCH_SIZE,
                      "learning_rate": LEARNING_RATE, "weight_decay": WEIGHT_DECAY,
                      "pos_weight": POS_WEIGHT}
            if self._algorithm is Algorithm.FEDAVG:
                result = train_local_epoch_v2(**common)
            else:
                result = train_local_fedprox_epoch_v2(**common, mu=self._mu)
            if result.examples_seen != self._buffer.eligible_count():
                raise ClientError("EXAMPLE_ACCOUNTING_MISMATCH")
            envelope = make_envelope(
                round_id=round_id, client_id=self._buffer.client_id,
                participant_id=self._participant_id, session_id=self._session_id,
                base_sha=self._base_sha, dataset_sha=str(self._buffer.dataset_sha256),
                spec_sha=self._spec_sha, examples=result.examples_seen,
                delta=dict(result.update.delta))
            if scan_forbidden(envelope):
                raise ClientError("FORBIDDEN_FIELD_IN_ENVELOPE")
            if delta_sha(envelope["payload"]["delta"]) != envelope["update_sha256"]:
                raise ClientError("UPDATE_DIGEST_MISMATCH")
        except Exception:
            self._move(ClientState.FAILED)
            raise
        self._result, self._envelope, self._round = result, envelope, round_id
        self._move(ClientState.UPDATE_READY)

    async def produce_update(self) -> UpdateSubmission:
        if self._state is not ClientState.UPDATE_READY or self._envelope is None:
            raise ClientError("NO_UPDATE_READY")
        env = self._envelope
        return UpdateSubmission(
            client_id=env["client_id"], round_id=env["round_id"],
            base_state_digest=env["base_global_state_sha256"], update_digest=env["update_sha256"],
            examples_seen=env["examples_seen"])

    # ---- internal (bridge-only) -----------------------------------------------------------------
    def mark_submitted(self) -> None:
        """Reserved for the CAP-007 coordinator integration; CAP-006 never submits."""
        self._move(ClientState.SUBMITTED)

    def _envelope_for_bridge(self) -> dict[str, Any]:
        if self._envelope is None:
            raise ClientError("NO_UPDATE_READY")
        return self._envelope

    def _training_diagnostics(self) -> dict[str, Any]:
        r = self._result
        return {"examples_seen": r.examples_seen, "batch_count": r.batch_count,
                "shuffle_seed": str(r.shuffle_seed), "update_bytes": r.update_bytes,
                "mean_loss_diagnostic_only": r.mean_loss, "update_norm_diagnostic_only": r.update_norm}
