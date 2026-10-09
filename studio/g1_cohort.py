# ruff: noqa: E501
"""G1: a fresh, never-used synthetic evaluation cohort for the Generalisation lane.

16 participants (two independent profiles for each of the eight established site conditions) produced by the EXISTING deterministic generator through the unmodified
dataset builder, with participant ids SIM_P000401-416, new seeds, new sessions and new event schedules. It is disjoint (participants, sessions, window inputs) from
the 8-client training cohort, the 8-participant showcase holdout and the 16-participant FL10 diagnostic holdout; that is proved at build time and recorded.

The cohort has never been used for training, round/threshold selection or any earlier diagnostic. Its per-dataset digests are pinned in
``configs/studio/g1_cohort_manifest_v1.json`` so generator drift is detected. Once displayed, repeated viewing is diagnostic, not independent confirmation."""

from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from typing import Any

import numpy as np

from federated.virtual_client_source_v1 import LocalDataset, build_local_dataset
from federated.wearable_sim_local_labels import SyntheticEventLabelProvider, SyntheticObservedSource
from fl10 import evaluate as ev
from simulation import fl_cohort_v1 as cohort
from simulation.fl_cohort_v1 import ClientProfile
from simulation.wearable import participant_id_for_index
from studio.holdout_cache import FrozenHoldout

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = Path("configs/studio/g1_cohort_manifest_v1.json")
COHORT_ID = "WEARABLE_SIM_STUDIO_G1_UNSEEN_V1"
BASE_SEED = 20270301                 # replicate r uses event-schedule base BASE_SEED + 100*r; participant seed = that base + site index
FIRST_PARTICIPANT_INDEX = 401
COUNT = 16
SITES = 8
COHORT_USE_LABEL = "UNSEEN SYNTHETIC COHORT — NOT USED FOR TRAINING, ROUND OR THRESHOLD SELECTION"
COHORT_USE_DETAIL = ("The G1 cohort (16 participants, ids SIM_P000401-416) is disjoint from the 8-client training cohort, the 8-participant showcase holdout and the 16-participant FL10 diagnostic "
                     "holdout (zero participant, session and window-input overlap, proved when it is built). It has never been used to select a round, threshold or candidate. Showing it live "
                     "makes repeated viewing diagnostic, not independent confirmation, and it measures the synthetic engineering-event task only.")
CLAIM_BOUNDARY = "SYNTHETIC_ENGINEERING_EVENT_GENERALISATION_ONLY_NOT_AAMI_SVF_OR_CLINICAL"


class G1Error(RuntimeError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}:{detail}" if detail else code)
        self.code, self.detail = code, detail


def g1_id(k: int) -> str:
    return f"SIM_G1_UNSEEN_{k:02d}"


def profile(k: int) -> ClientProfile:
    if not 0 <= k < COUNT:
        raise ValueError("G1_INDEX_OUT_OF_RANGE")
    site, replicate = k % SITES, k // SITES
    base = BASE_SEED + 100 * replicate
    index = FIRST_PARTICIPANT_INDEX + k
    return ClientProfile(client_id=g1_id(k), participant_index=index, participant_id=participant_id_for_index(index), session_id=f"SIM_S_G1_UNSEEN_{k:02d}_000001",
                         seed=base + site, base_hr_bpm=float(64 + 3 * site), faults=cohort._FAULTS[site], context=cohort._CONTEXT[site], events=cohort._schedule_events(site, base), coverage=cohort._COVERAGE[site])


def profiles() -> tuple[ClientProfile, ...]:
    return tuple(profile(k) for k in range(COUNT))


def build_dataset(p: ClientProfile) -> LocalDataset:
    return build_local_dataset(SyntheticObservedSource(p), SyntheticEventLabelProvider(p))


def manifest_entry(p: ClientProfile, d: LocalDataset, k: int) -> dict[str, Any]:
    return {"holdout_id": p.client_id, "participant_id": p.participant_id, "session_id": p.session_id, "seed": p.seed, "site_condition": cohort.client_id(k % SITES), "replicate": k // SITES,
            "coverage": list(p.coverage), "event_times_s": [e.time_s for e in p.events], "counts": d.counts, "dataset_sha256": d.dataset_sha256}


def build_manifest(datasets: list[LocalDataset]) -> dict[str, Any]:
    entries = [manifest_entry(p, d, k) for k, (p, d) in enumerate(zip(profiles(), datasets, strict=True))]
    return {"cohort_id": COHORT_ID, "base_seed": BASE_SEED, "first_participant_index": FIRST_PARTICIPANT_INDEX, "participants": entries,
            "label": COHORT_USE_LABEL, "claim_boundary": CLAIM_BOUNDARY}


def manifest_bytes(manifest: dict[str, Any]) -> bytes:
    return (json.dumps(manifest, indent=1, sort_keys=True) + "\n").encode()


def _separation(datasets: list[LocalDataset]) -> dict[str, Any]:
    from federated.wearable_fl_runner_v1 import build_cohort
    from final_showcase.holdout import build_holdout_dataset, holdout_profiles
    from fl10 import holdout as fl10_holdout

    return ev.separation(datasets, {"training_cohort_8_clients": build_cohort()[1],
                                    "showcase_holdout_8_participants": [build_holdout_dataset(p) for p in holdout_profiles()],
                                    "fl10_diagnostic_holdout_16_participants": [fl10_holdout.build_dataset(p) for p in fl10_holdout.profiles()]})


def _build(root: Path = ROOT) -> FrozenHoldout:
    datasets = [build_dataset(p) for p in profiles()]
    ev.require_both_classes(datasets)
    manifest = build_manifest(datasets)
    path = root / MANIFEST
    if not path.exists():
        raise G1Error("G1_MANIFEST_MISSING", str(MANIFEST))
    pinned = json.loads(path.read_text())
    if pinned != manifest:
        diffs = [e["holdout_id"] for e, f in zip(manifest["participants"], pinned.get("participants", []), strict=False) if e != f]
        raise G1Error("G1_COHORT_DIFFERS_FROM_PINNED_MANIFEST", ",".join(diffs[:4]) or "header")
    separation = _separation(datasets)
    protocol = json.loads((root / ev.PROTOCOL).read_text())
    labels = np.concatenate([d.labels for d in datasets]).astype(int)
    owners = np.concatenate([[d.participant_id] * len(d.labels) for d in datasets])
    inputs = np.concatenate([d.inputs for d in datasets])
    for array in (inputs, labels, owners):
        array.setflags(write=False)
    return FrozenHoldout(tuple(datasets), inputs, labels, owners, manifest["participants"], separation, protocol, hashlib.sha256((root / ev.PROTOCOL).read_bytes()).hexdigest(),
                         hashlib.sha256(path.read_bytes()).hexdigest(), COHORT_ID)


_LOCK = threading.Lock()
_CACHE: FrozenHoldout | None = None


def load() -> FrozenHoldout:
    global _CACHE
    with _LOCK:
        if _CACHE is None:
            _CACHE = _build()
        return _CACHE


def write_manifest(root: Path = ROOT) -> dict[str, Any]:
    """One-time generation of the pinned manifest (after the separation proof passes). Refuses to overwrite an existing pin."""
    path = root / MANIFEST
    if path.exists():
        raise G1Error("G1_MANIFEST_ALREADY_PINNED")
    datasets = [build_dataset(p) for p in profiles()]
    ev.require_both_classes(datasets)
    _separation(datasets)
    manifest = build_manifest(datasets)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(manifest_bytes(manifest))
    return manifest
