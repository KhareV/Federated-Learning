# ruff: noqa: E501
"""A completed simulated monitoring session from History as the local data of one federation client.

The session's persisted evidence does not store raw ECG, but a simulated session is fully determined by its frozen scenario and seed (the Observatory relies on the same
determinism). The windows the monitoring runtime emitted are therefore regenerated with the UNCHANGED canonical operators (``stream_windows`` = ``WearableStreamRuntime``) and the
VALID, complete ones become the client's local dataset through the unchanged helpers (``is_trainable``, ``normalize_windows``, ``dataset_semantic_sha``).

LABELS: a scenario session has no scheduled engineering events, and labels never come from model predictions, monitoring state or thresholds. The cohort's event-window contract
(``WEARABLE_SIM_EVENT_WINDOW_V1``) therefore cannot be applied. Labels here are deterministic, balanced and SYNTHETIC-ASSIGNED for the demonstration (as in the recorded-hardware demo)
and are named that way everywhere; federated metrics on them measure agreement with those assigned labels only and are not comparable to the cohort's event task."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from typing import Any

import numpy as np

from federated.virtual_client_source_v1 import LocalDataset, dataset_semantic_sha, is_trainable, normalize_windows, stream_windows
from product.devices.scenarios import load_scenarios
from simulation.profile_v2013 import iter_observed_records

LABEL_ID = "SYNTHETIC_ASSIGNED_FOR_DEMO_FROM_HISTORY_SESSION_V1"
MIN_TRAINABLE = 16


class SessionSourceError(RuntimeError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}:{detail}" if detail else code)
        self.code, self.detail = code, detail


class _ScenarioRecords:
    def __init__(self, scenario: Any, session_id: str) -> None:
        self._scenario, self.session_id = scenario, session_id

    def records(self) -> Iterator[Any]:
        return iter(iter_observed_records(self._scenario.profile()))


def resolve(store: Any, owner: str, session_id: str) -> dict[str, Any]:
    """Validate a History session for use as a signal source; returns the small, persistable descriptor."""
    session = store.get_session(session_id)
    if session is None:
        raise SessionSourceError("NOT_FOUND", "unknown monitoring session")
    if session.user_id != owner:
        raise SessionSourceError("FORBIDDEN", "session belongs to another user")
    if session.state.value != "COMPLETED":
        raise SessionSourceError("INVALID_STATE", f"only a COMPLETED monitoring session can be a signal source (this one is {session.state.value})")
    provenance = session.simulation_provenance
    scenario = load_scenarios().get(provenance.scenario_id) if provenance else None
    if scenario is None or provenance.seed != scenario.seed:
        raise SessionSourceError("INVALID_STATE", "only sessions of a frozen synthetic scenario can be regenerated")
    return {"session_id": session_id, "scenario_id": scenario.scenario_id, "seed": int(scenario.seed)}


def dataset_for_session(descriptor: dict[str, Any], profile: Any) -> tuple[LocalDataset, dict[str, Any]]:
    """The session's trainable windows as the local dataset of the client described by ``profile`` (client / participant ids), plus a descriptor of what was used."""
    scenario = load_scenarios()[descriptor["scenario_id"]]
    windows = stream_windows(_ScenarioRecords(scenario, f"HISTORY-SRC-{descriptor['session_id']}"))
    quality = {"VALID": 0, "DEGRADED": 0, "UNUSABLE": 0}
    for w in windows:
        quality[w["ecg_quality"]] += 1
    trainable = [w for w in windows if is_trainable(w)]
    if len(trainable) < MIN_TRAINABLE:
        raise SessionSourceError("INSUFFICIENT_TRAINABLE_WINDOWS", f"{len(trainable)} of {len(windows)} windows are VALID and complete (need {MIN_TRAINABLE}); choose a session of a cleaner scenario")
    ranked = sorted(range(len(trainable)), key=lambda i: hashlib.sha256(f"{descriptor['session_id']}:{trainable[i]['timestamp_us']}".encode()).hexdigest())
    labels = np.zeros(len(trainable), dtype=np.float32)
    for rank, index in enumerate(ranked):
        labels[index] = rank % 2
    edges = [int(w["timestamp_us"]) for w in trainable]
    inputs = normalize_windows(np.asarray([w["ecg"]["samples"] for w in trainable]))
    positives = int(labels.sum())
    counts = {"source_records": None, "windows_emitted": len(windows), **quality, "trainable": len(trainable), "synthetic_positive": positives, "synthetic_negative": len(trainable) - positives,
              "excluded_not_valid": len(windows) - quality["VALID"], "excluded_valid_but_incomplete": quality["VALID"] - len(trainable)}
    dataset = LocalDataset(profile.client_id, profile.participant_id, descriptor["session_id"], inputs, labels, tuple(edges), counts, dataset_semantic_sha(inputs, labels, edges))
    return dataset, {"source": "HISTORY_SESSION", "label_contract": LABEL_ID, "labels": "SYNTHETIC_ASSIGNED_FOR_DEMO (not the cohort's event-window truth)", **descriptor, "counts": counts,
                     "dataset_sha256": dataset.dataset_sha256}
