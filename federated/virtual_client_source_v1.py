"""VIRTUAL_FL_CLIENT_SOURCE_V1 -- hardware-independent local source contract + client-local
dataset builder.

Two SEPARATE interfaces:
  A. ObservedRecordSource: canonical ObservedRecord samples only.
  B. LocalTrainingLabelProvider: optional client-local engineering labels (truth side).
The federated server/router/aggregator depends on neither: it receives only update envelopes. Any
future source implementing the same ObservedRecord contract can replace the synthetic generator
without changing routing, aggregation, secure aggregation or the round coordinator. No hardware
implementation or claim is made here.

The builder drives the REAL production-like stream path (GAP_POLICY_V1 behaviour -> causal
360->250 Hz resampling -> causal band-pass -> 10 s windows @ 5 s cadence -> QUALITY_V1) through
simulation.stream_runtime_v2013 (imported, unmodified).
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np

from nhm.hashing import hash_bytes
from simulation.stream_runtime_v2013 import WearableStreamRuntime, deliver_chunks
from simulation.types import ObservedRecord

CONTRACT_ID = "VIRTUAL_FL_CLIENT_SOURCE_V1"
EPSILON = 1e-8
WINDOW_SAMPLES = 2500
WINDOW_US = 10_000_000


class ObservedRecordSource(Protocol):
    client_id: str
    participant_id: str
    session_id: str

    def records(self) -> Iterable[ObservedRecord]: ...


class LocalTrainingLabelProvider(Protocol):
    def labels_for_windows(self, right_edges_us: list[int]) -> np.ndarray: ...


@dataclass(frozen=True)
class LocalDataset:
    client_id: str
    participant_id: str
    session_id: str
    inputs: np.ndarray        # float32 [N,1,2500], per-window z-scored
    labels: np.ndarray        # float32 [N]
    right_edges_us: tuple[int, ...]
    counts: dict[str, Any]
    dataset_sha256: str


def normalize_windows(windows: np.ndarray) -> np.ndarray:
    values = np.asarray(windows, dtype=np.float64)
    means = np.mean(values, axis=1, keepdims=True)
    scales = np.std(values, axis=1, ddof=0, keepdims=True)
    normalized = (values - means) / (scales + EPSILON)
    if not np.isfinite(normalized).all():
        raise RuntimeError("nonfinite normalized synthetic input")
    return normalized.astype(np.float32)[:, np.newaxis, :]


def dataset_semantic_sha(inputs: np.ndarray, labels: np.ndarray, edges: Iterable[int]) -> str:
    material = (np.ascontiguousarray(inputs, dtype=np.float32).tobytes()
                + np.ascontiguousarray(labels, dtype=np.float32).tobytes()
                + json.dumps(list(edges)).encode())
    return hash_bytes(material)


def stream_windows(source: ObservedRecordSource, *, model_id: str = "NONE",
                   replay_id: str = "FL_SYSTEM") -> list[dict[str, Any]]:
    runtime = WearableStreamRuntime(session_id=source.session_id, model_id=model_id,
                                    replay_id=replay_id)
    events: list[dict[str, Any]] = []
    for chunk in deliver_chunks(source.records(), mode="ACCELERATED_REPLAY"):
        events.extend(runtime.ingest(chunk))
    events.extend(runtime.finish())
    return events


def is_trainable(event: dict[str, Any]) -> bool:
    samples = event["ecg"]["samples"]
    return (event["ecg_quality"] == "VALID" and len(samples) == WINDOW_SAMPLES
            and event["diagnostics"]["missing_slots"] == 0
            and bool(np.isfinite(np.asarray(samples, dtype=np.float64)).all()))


def build_local_dataset(source: ObservedRecordSource, labels: LocalTrainingLabelProvider,
                        *, source_records: int | None = None) -> LocalDataset:
    events = stream_windows(source)
    quality = {"VALID": 0, "DEGRADED": 0, "UNUSABLE": 0}
    for event in events:
        quality[event["ecg_quality"]] += 1
    trainable = [e for e in events if is_trainable(e)]
    if not trainable:
        raise RuntimeError("no trainable synthetic windows")
    edges = [int(e["timestamp_us"]) for e in trainable]
    window_labels = np.asarray(labels.labels_for_windows(edges), dtype=np.float32)
    inputs = normalize_windows(np.asarray([e["ecg"]["samples"] for e in trainable]))
    positives = int(window_labels.sum())
    counts = {
        "source_records": source_records, "windows_emitted": len(events),
        "VALID": quality["VALID"], "DEGRADED": quality["DEGRADED"],
        "UNUSABLE": quality["UNUSABLE"], "trainable": len(trainable),
        "synthetic_positive": positives, "synthetic_negative": len(trainable) - positives,
        "excluded_not_valid": len(events) - quality["VALID"],
        "excluded_valid_but_incomplete": quality["VALID"] - len(trainable)}
    return LocalDataset(source.client_id, source.participant_id, source.session_id, inputs,
                        window_labels, tuple(edges), counts,
                        dataset_semantic_sha(inputs, window_labels, edges))
