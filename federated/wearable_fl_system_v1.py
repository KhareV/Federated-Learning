"""V2_FL_WEARABLE_SYSTEM_PROTOCOL_V1: update envelope, router/coordinator state machine, canonical
aggregation ordering, restart serialization, semantic event log and replay digest for the
WEARABLE_SIM_FL_SYSTEM_V1 ENGINEERING exercise.

The server side (this module) never imports ObservedRecord sources, SimulationTruth or any label
code: it receives only model-update envelopes. Decisions are a PURE function of envelope metadata
plus coordinator state (`decide`), so the control plane can be replayed from the event log alone.
"""

from __future__ import annotations

import json
from collections import OrderedDict
from typing import Any

import numpy as np

from federated.aggregation import FL_STATE_TRANSPORT_ID, ClientUpdate, aggregate_weighted_deltas
from federated.model_adapter import serialize_state
from nhm.hashing import hash_bytes

PROTOCOL_ID = "V2_FL_WEARABLE_SYSTEM_PROTOCOL_V1"
EXPERIMENT_ID = "WEARABLE_SIM_FL_SYSTEM_V1"
REPLAY_ID = "WEARABLE_SIM_FL_SYSTEM_REPLAY_V1"
SOURCE_DATASET = "WEARABLE_SIM_V1"
ROUNDS = 3
CLIENT_COUNT = 8

ENVELOPE_FIELDS = (
    "protocol_version", "experiment_id", "round_id", "client_id", "participant_id", "session_id",
    "base_global_state_sha256", "client_dataset_sha256", "state_transport_id",
    "state_spec_sha256", "examples_seen", "update_sha256", "engineering_only", "source_dataset")
PAYLOAD_FIELD = "payload"
RAW_FIELDS = frozenset({"raw_ecg", "ecg", "ecg_samples", "samples", "waveform", "ppg", "spo2",
                        "observed_records", "records", "minibatch", "inputs", "windows"})
LABEL_FIELDS = frozenset({"labels", "label", "targets", "y"})
TRUTH_FIELDS = frozenset({"truth", "simulation_truth", "SimulationTruth", "event_schedule",
                          "scheduled_events"})

# deterministic rejection codes, evaluated in this exact order
REJECTION_ORDER = (
    "RAW_DATA_FIELD_PRESENT", "LABEL_FIELD_PRESENT", "TRUTH_FIELD_PRESENT", "SCHEMA_MISMATCH",
    "PROTOCOL_MISMATCH", "PROVENANCE_MISMATCH", "UNKNOWN_CLIENT", "PARTICIPANT_MISMATCH",
    "SESSION_MISMATCH", "ROUND_NOT_OPEN", "STALE_ROUND", "FUTURE_ROUND",
    "BASE_STATE_MISMATCH", "DUPLICATE_UPDATE", "DATASET_SHA_MISMATCH",
    "NONPOSITIVE_EXAMPLES", "TRANSPORT_MISMATCH", "STATE_SPEC_MISMATCH", "DTYPE_POLICY_MISMATCH",
    "NONFINITE_UPDATE", "UPDATE_SHA_MISMATCH")


class CoordinatorError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def state_spec_sha(state: dict[str, np.ndarray]) -> str:
    spec = [[k, list(np.asarray(v).shape), np.asarray(v).dtype.str] for k, v in state.items()]
    return hash_bytes(json.dumps(spec, separators=(",", ":")).encode())


def delta_sha(delta: dict[str, np.ndarray]) -> str:
    return hash_bytes(serialize_state(delta))


def make_envelope(*, round_id: int, client_id: str, participant_id: str, session_id: str,
                  base_sha: str, dataset_sha: str, spec_sha: str, examples: int,
                  delta: dict[str, np.ndarray]) -> dict[str, Any]:
    return {
        "protocol_version": PROTOCOL_ID, "experiment_id": EXPERIMENT_ID, "round_id": round_id,
        "client_id": client_id, "participant_id": participant_id, "session_id": session_id,
        "base_global_state_sha256": base_sha, "client_dataset_sha256": dataset_sha,
        "state_transport_id": FL_STATE_TRANSPORT_ID, "state_spec_sha256": spec_sha,
        "examples_seen": examples, "update_sha256": delta_sha(delta), "engineering_only": True,
        "source_dataset": SOURCE_DATASET, PAYLOAD_FIELD: {"delta": delta}}


def scan_forbidden(obj: Any, path: str = "") -> list[str]:
    """Server-boundary data-locality scan: forbidden field names, observed/truth objects, and
    window-shaped raw arrays anywhere in a received object."""
    hits: list[str] = []
    name = type(obj).__name__
    if name in ("ObservedRecord", "SimulationTruth", "LocalDataset"):
        hits.append(f"{path}:{name}")
    if isinstance(obj, np.ndarray) and obj.ndim >= 2 and obj.shape[-1] == 2500:
        hits.append(f"{path}:window_shaped_array")
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in RAW_FIELDS | LABEL_FIELDS | TRUTH_FIELDS:
                hits.append(f"{path}/{key}")
            hits.extend(scan_forbidden(value, f"{path}/{key}"))
    elif isinstance(obj, list | tuple):
        for i, value in enumerate(obj):
            hits.extend(scan_forbidden(value, f"{path}[{i}]"))
    return hits


def extract_meta(envelope: dict[str, Any], expected_state: dict[str, np.ndarray]) -> dict[str, Any]:
    """All tensor-dependent facts are reduced to JSON scalars so decide()/replay need no tensors."""
    fields = sorted(k for k in envelope if k != PAYLOAD_FIELD)
    meta: dict[str, Any] = {"fields": fields,
                            "raw_field": bool(set(envelope) & RAW_FIELDS)
                            or bool(set(envelope.get(PAYLOAD_FIELD, {})) & RAW_FIELDS),
                            "label_field": bool(set(envelope) & LABEL_FIELDS),
                            "truth_field": bool(set(envelope) & TRUTH_FIELDS)}
    for name in ENVELOPE_FIELDS:
        meta[name] = envelope.get(name)
    delta = envelope.get(PAYLOAD_FIELD, {}).get("delta")
    meta["payload_present"] = isinstance(delta, dict)
    spec_ok = dtype_ok = finite = True
    if isinstance(delta, dict):
        spec_ok = list(delta) == list(expected_state) and all(
            np.asarray(delta[k]).shape == np.asarray(expected_state[k]).shape
            for k in expected_state if k in delta)
        dtype_ok = all(np.asarray(delta[k]).dtype == np.asarray(expected_state[k]).dtype
                       for k in expected_state if k in delta)
        finite = all(np.isfinite(np.asarray(v)).all() for v in delta.values()
                     if np.issubdtype(np.asarray(v).dtype, np.floating))
        meta["tensor_count"] = len(delta)
        meta["update_sha_matches_payload"] = (
            delta_sha(delta) == envelope.get("update_sha256")) if spec_ok and dtype_ok else False
    else:
        meta["tensor_count"] = 0
        meta["update_sha_matches_payload"] = False
    meta["spec_ok"], meta["dtype_ok"], meta["finite"] = spec_ok, dtype_ok, finite
    meta["update_id"] = hash_bytes(
        f"{meta['client_id']}|{meta['round_id']}|{meta['update_sha256']}".encode())[:16]
    return meta


class Coordinator:
    """Exactly-once round coordinator. States: round n OPEN -> 8 accepted -> COMMITTED."""

    def __init__(self, manifest: dict[str, dict[str, str]], spec_sha: str) -> None:
        self.manifest = manifest          # client_id -> {participant_id, session_id, dataset_sha}
        self.spec_sha = spec_sha
        self.committed: OrderedDict[int, str] = OrderedDict()   # round -> new global sha
        self.open_round: int | None = None
        self.base_sha: str | None = None
        self.accepted: dict[str, dict[str, Any]] = {}
        self.deltas: dict[str, dict[str, np.ndarray]] = {}
        self.decisions: list[dict[str, Any]] = []

    def open(self, round_id: int, base_sha: str) -> None:
        if self.open_round is not None:
            raise CoordinatorError("ROUND_ALREADY_OPEN")
        if round_id != len(self.committed) + 1:
            raise CoordinatorError("ROUND_OUT_OF_SEQUENCE")
        self.open_round, self.base_sha, self.accepted, self.deltas = round_id, base_sha, {}, {}

    def decide(self, meta: dict[str, Any]) -> str | None:
        client = meta["client_id"]
        entry = self.manifest.get(client)
        checks = (
            ("RAW_DATA_FIELD_PRESENT", meta["raw_field"]),
            ("LABEL_FIELD_PRESENT", meta["label_field"]),
            ("TRUTH_FIELD_PRESENT", meta["truth_field"]),
            ("SCHEMA_MISMATCH", meta["fields"] != sorted(ENVELOPE_FIELDS)
             or not meta["payload_present"]),
            ("PROTOCOL_MISMATCH", meta["protocol_version"] != PROTOCOL_ID
             or meta["experiment_id"] != EXPERIMENT_ID),
            ("PROVENANCE_MISMATCH", meta["engineering_only"] is not True
             or meta["source_dataset"] != SOURCE_DATASET),
            ("UNKNOWN_CLIENT", entry is None),
            ("PARTICIPANT_MISMATCH", entry is not None
             and meta["participant_id"] != entry["participant_id"]),
            ("SESSION_MISMATCH", entry is not None and meta["session_id"] != entry["session_id"]),
            ("ROUND_NOT_OPEN", self.open_round is None),
            ("STALE_ROUND", self.open_round is not None and meta["round_id"] < self.open_round),
            ("FUTURE_ROUND", self.open_round is not None and meta["round_id"] > self.open_round),
            ("BASE_STATE_MISMATCH", meta["base_global_state_sha256"] != self.base_sha),
            ("DUPLICATE_UPDATE", client in self.accepted),
            ("DATASET_SHA_MISMATCH", entry is not None
             and meta["client_dataset_sha256"] != entry["dataset_sha"]),
            ("NONPOSITIVE_EXAMPLES", isinstance(meta["examples_seen"], bool)
             or not isinstance(meta["examples_seen"], int) or meta["examples_seen"] <= 0),
            ("TRANSPORT_MISMATCH", meta["state_transport_id"] != FL_STATE_TRANSPORT_ID),
            ("STATE_SPEC_MISMATCH", not meta["spec_ok"]
             or meta["state_spec_sha256"] != self.spec_sha),
            ("DTYPE_POLICY_MISMATCH", not meta["dtype_ok"]),
            ("NONFINITE_UPDATE", not meta["finite"]),
            ("UPDATE_SHA_MISMATCH", not meta["update_sha_matches_payload"]))
        for code, failed in checks:
            if failed:
                return code
        return None

    def record(self, meta: dict[str, Any], code: str | None) -> dict[str, Any]:
        decision = {"update_id": meta["update_id"], "client_id": meta["client_id"],
                    "round_id": meta["round_id"], "update_sha256": meta["update_sha256"],
                    "decision": "ACCEPTED" if code is None else "REJECTED", "code": code}
        if code is None:
            self.accepted[meta["client_id"]] = meta
        self.decisions.append(decision)
        return decision

    def submit_meta(self, meta: dict[str, Any]) -> dict[str, Any]:
        return self.record(meta, self.decide(meta))

    def submit(self, envelope: dict[str, Any], expected_state: dict[str, np.ndarray]
               ) -> dict[str, Any]:
        meta = extract_meta(envelope, expected_state)
        decision = self.submit_meta(meta)
        if decision["decision"] == "ACCEPTED":
            self.deltas[meta["client_id"]] = envelope[PAYLOAD_FIELD]["delta"]
        return decision

    def ready(self) -> bool:
        return self.open_round is not None and set(self.accepted) == set(self.manifest)

    def aggregate(self, global_state: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        if not self.ready():
            raise CoordinatorError("INCOMPLETE_ROUND")
        ordered = sorted(self.accepted)       # canonical sort by client ID before aggregation
        updates = [ClientUpdate(c, int(self.accepted[c]["examples_seen"]), self.deltas[c])
                   for c in ordered]
        new_state, _ = aggregate_weighted_deltas(global_state, updates)
        return new_state

    def commit(self, round_id: int, new_state_sha: str) -> None:
        if round_id in self.committed:
            raise CoordinatorError("ROUND_ALREADY_COMMITTED")
        if self.open_round != round_id or not self.ready():
            raise CoordinatorError("INCOMPLETE_ROUND")
        self.committed[round_id] = new_state_sha
        self.open_round = None

    def identity(self) -> str:
        return hash_bytes(json.dumps({
            "committed": list(self.committed.items()),
            "decisions": [(d["update_id"], d["decision"], d["code"]) for d in self.decisions]},
            sort_keys=True).encode())


def canonical_order(client_ids: list[str]) -> list[str]:
    return sorted(client_ids)


def semantic_digest(fields: dict[str, Any]) -> str:
    return hash_bytes(json.dumps(fields, sort_keys=True, separators=(",", ":")).encode())


def replay_control_plane(events: list[dict[str, Any]], manifest: dict[str, dict[str, str]],
                         spec_sha: str) -> dict[str, Any]:
    """Replay the frozen federation event stream through the coordinator state machine WITHOUT
    waveforms, training or tensors."""
    coordinator = Coordinator(manifest, spec_sha)
    mismatches: list[str] = []
    for event in events:
        kind = event["type"]
        if kind == "ROUND_OPENED":
            coordinator.open(event["round_id"], event["base_global_state_sha256"])
        elif kind in ("CLIENT_UPDATE_ACCEPTED", "CLIENT_UPDATE_REJECTED"):
            decision = coordinator.submit_meta(event["meta"])
            if (decision["decision"], decision["code"]) != (event["decision"], event["code"]):
                mismatches.append(event["update_id"])
        elif kind == "ROUND_COMMITTED":
            coordinator.commit(event["round_id"], event["global_state_sha256"])
    return {"identity": coordinator.identity(), "mismatches": mismatches,
            "accepted": sum(d["decision"] == "ACCEPTED" for d in coordinator.decisions),
            "rejected": sum(d["decision"] == "REJECTED" for d in coordinator.decisions),
            "committed_rounds": list(coordinator.committed.items())}
