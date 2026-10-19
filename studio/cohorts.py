# ruff: noqa: E501
"""The synthetic-cohort option of a Studio run: ORIGINAL (the frozen NHM_FL10_001 cohort, the default and unchanged) or REALISTIC (``simulation/fl_cohort_realistic_v2.py``).

A cohort fixes three things for a run: the eight training clients, the evaluation holdout every committed state is scored on, and the wording that goes with them. Nothing frozen is edited:
the ORIGINAL branch calls exactly the modules it always called. The REALISTIC evaluation cohort is checked against ``configs/realistic/realistic_cohort_manifest_v2.json`` before any use
(per-participant dataset digests, both classes present, zero overlap with both training cohorts and zero participant/session overlap with every earlier evaluation cohort)."""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from fl10 import evaluate as ev
from studio import holdout_cache
from studio.constants import CLAIM_BOUNDARY, COHORT_USE_DETAIL, COHORT_USE_LABEL
from studio.holdout_cache import FrozenHoldout, HoldoutError

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "configs/realistic/realistic_cohort_manifest_v2.json"
ORIGINAL, REALISTIC, REALISTIC_NSTDB = "ORIGINAL", "REALISTIC", "REALISTIC_NSTDB"
SITES = 8                                   # site conditions; the evaluation participants are two replicates of each
COHORTS = (ORIGINAL, REALISTIC, REALISTIC_NSTDB)
REALISTIC_FAMILY = (REALISTIC, REALISTIC_NSTDB)            # the cohorts built on the realistic generators: same structure, pinned by a committed manifest, scored on their own holdout
DEFAULT = ORIGINAL
MANIFEST_V3 = ROOT / "configs/realistic/realistic_cohort_manifest_v3.json"
MANIFESTS = {REALISTIC: MANIFEST, REALISTIC_NSTDB: MANIFEST_V3}


def is_realistic(cohort: str) -> bool:
    """True for every cohort of the realistic family (the invented-noise V2 cohort and the recorded-noise NSTDB cohort)."""
    return cohort in REALISTIC_FAMILY


def module(cohort: str) -> Any:
    """The simulation module of a realistic-family cohort (profiles, dataset builder, label provider, manifest builder)."""
    if cohort == REALISTIC:
        from simulation import fl_cohort_realistic_v2 as c
    elif cohort == REALISTIC_NSTDB:
        from simulation import fl_cohort_realistic_v3 as c
    else:
        raise ValueError("not a realistic-family cohort")
    return c

REALISTIC_USE_LABEL = "REALISTIC SYNTHETIC EVALUATION COHORT — DIAGNOSTIC, ANNOTATION-NOISY, NOT CLINICAL"
REALISTIC_USE_DETAIL = ("The 16 evaluation participants (SIM_P000601-616) come from the realistic ECG generator: variable rhythm, ectopic beats that are premature with a pause, motion artifacts, "
                        "and labels that are annotations with a few misses and false marks. They are disjoint from both training cohorts and every earlier evaluation cohort, and their digests are pinned in "
                        "the committed manifest. The cohort was inspected once before a timing fix to the generator (see docs/realistic/REALISTIC_COHORT_V2.md), so it is fresh, not untouched. "
                        "No round, threshold or candidate is selected from these scores. Same simulator family as the training clients: evidence about the pipeline, not about patients.")
REALISTIC_CLAIM_BOUNDARY = "SYNTHETIC_REALISTIC_ECTOPY_ANNOTATION_EVALUATION_ONLY_NOT_AAMI_SVF_OR_CLINICAL"
REALISTIC_NO_FREEZE = "NONE (realistic cohort pinned by committed manifest, not by a method freeze)"
NSTDB_USE_LABEL = "REALISTIC SYNTHETIC EVALUATION COHORT WITH RECORDED NSTDB NOISE — DIAGNOSTIC, ANNOTATION-NOISY, NOT CLINICAL"
NSTDB_USE_DETAIL = ("The 16 evaluation participants (SIM_P000801-816) come from the realistic ECG generator with RECORDED noise: the same variable rhythm, premature ectopic beats and annotation-noisy labels as the realistic cohort, "
                    "but the baseline wander, electrode motion and muscle artifact are the recorded MIT-BIH Noise Stress Test noise (NSTDB bw, em, ma) scaled to NSTDB's documented SNR levels, from a region of the recordings that no "
                    "training participant uses. Disjoint from every earlier cohort, with digests pinned in the committed manifest. The cohort was looked at once before it was pinned (see docs/realistic/REALISTIC_COHORT_V3.md), "
                    "so it is fresh, not untouched. No round, threshold or candidate is selected from these scores. Same simulator family as the training clients: evidence about the pipeline, not about patients.")
NSTDB_CLAIM_BOUNDARY = "SYNTHETIC_REALISTIC_ECTOPY_RECORDED_NOISE_EVALUATION_ONLY_NOT_AAMI_SVF_OR_CLINICAL"


@dataclass(frozen=True)
class CohortSpec:
    id: str
    label: str
    description: str
    client_ids: tuple[str, ...]
    evaluation_cohort_id: str
    use_label: str
    use_detail: str
    claim_boundary: str
    method_freeze: str


def _original() -> CohortSpec:
    from fl10 import holdout

    return CohortSpec(ORIGINAL, "Original synthetic cohort (frozen)", "The frozen NHM_FL10_001 cohort: scheduled synthetic events added to a regular rhythm. Reproduces every recorded result.",
                      tuple(f"SIM_FL_SITE_{i:02d}" for i in range(8)), holdout.COHORT_ID, COHORT_USE_LABEL, COHORT_USE_DETAIL, CLAIM_BOUNDARY, "f91a96a6c5a38432e4fc84f7e760c21874ce2d40")


def _realistic() -> CohortSpec:
    from simulation import fl_cohort_realistic_v2 as c

    return CohortSpec(REALISTIC, "Realistic synthetic cohort", "Variable rhythm, premature ectopic beats with pauses, motion artifacts and annotation-noisy labels. Harder and closer to real ECG; still synthetic.",
                      tuple(p.client_id for p in c.train_profiles()), c.EVAL_COHORT_ID, REALISTIC_USE_LABEL, REALISTIC_USE_DETAIL, REALISTIC_CLAIM_BOUNDARY, REALISTIC_NO_FREEZE)


def _realistic_nstdb() -> CohortSpec:
    from simulation import fl_cohort_realistic_v3 as c

    return CohortSpec(REALISTIC_NSTDB, "Realistic cohort with recorded noise (NSTDB)", "The realistic cohort's rhythm, premature ectopic beats and annotation-noisy labels, with recorded MIT-BIH Noise Stress Test noise (baseline wander, electrode motion, muscle artifact) at NSTDB's SNR levels instead of invented artifacts.",
                      tuple(p.client_id for p in c.train_profiles()), c.EVAL_COHORT_ID, NSTDB_USE_LABEL, NSTDB_USE_DETAIL, NSTDB_CLAIM_BOUNDARY, REALISTIC_NO_FREEZE)


def spec(cohort: str) -> CohortSpec:
    if cohort == ORIGINAL:
        return _original()
    if cohort == REALISTIC:
        return _realistic()
    if cohort == REALISTIC_NSTDB:
        return _realistic_nstdb()
    raise ValueError("cohort must be ORIGINAL, REALISTIC or REALISTIC_NSTDB")


def describe(cohort: str) -> dict[str, Any]:
    s = spec(cohort)
    return {"id": s.id, "label": s.label, "description": s.description, "client_ids": list(s.client_ids), "evaluation_cohort_id": s.evaluation_cohort_id, "cohort_use": s.use_label, "claim_boundary": s.claim_boundary}


def training(cohort: str) -> tuple[list[Any], dict[str, dict[str, str]]]:
    """(datasets, manifest) of the eight training clients, built fresh (the trainer owns what it is given)."""
    if is_realistic(cohort):
        from scripts.run_fl10 import manifest_for

        c = module(cohort)
        datasets = [c.build_dataset(p) for p in c.train_profiles()]
        return datasets, manifest_for(datasets)
    from federated.wearable_fl_runner_v1 import build_cohort

    _, datasets, manifest = build_cohort()
    return datasets, manifest


# ---- the realistic evaluation cohort ------------------------------------------------------------------------------------------------------------------------------------------

_LOCK = threading.Lock()
_CACHES: dict[str, FrozenHoldout] = {}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def holdout_entries(pinned: dict[str, Any]) -> list[dict[str, Any]]:
    """Per-participant manifest entries in the shape the Live page lists for a holdout (``holdout_id`` is the evaluation client id)."""
    return [{**e, "holdout_id": e["client_id"], "replicate": k // SITES} for k, e in enumerate(pinned["eval"]["participants"])]


def static_info(cohort: str = REALISTIC) -> dict[str, Any]:
    """What can be said about a realistic-family evaluation cohort before this process has built it: the pinned manifest (labelled as such)."""
    pinned = json.loads(MANIFESTS[cohort].read_text())
    entries = holdout_entries(pinned)
    return {"entries": entries, "separation": {}, "windows": int(sum(e["counts"]["trainable"] for e in entries)), "separation_source": "PINNED_MANIFEST_SEPARATION_RECOMPUTED_WHEN_OBSERVER_LOADS",
            "protocol_sha256": _sha(ROOT / ev.PROTOCOL), "manifest_sha256": _sha(MANIFESTS[cohort])}


def _build_realistic_holdout(cohort: str = REALISTIC) -> FrozenHoldout:
    from federated.wearable_fl_runner_v1 import build_cohort
    from final_showcase.holdout import build_holdout_dataset, holdout_profiles
    from simulation import fl_cohort_realistic_v2 as v2
    from studio import g1_cohort

    c = module(cohort)
    manifest = MANIFESTS[cohort]
    pinned = json.loads(manifest.read_text())
    datasets = [c.build_dataset(p) for p in c.eval_profiles()]
    entries = holdout_entries(pinned)
    if len(entries) != len(datasets) or any(e["dataset_sha256"] != d.dataset_sha256 or e["participant_id"] != d.participant_id for e, d in zip(entries, datasets, strict=True)):
        raise HoldoutError("REALISTIC_HOLDOUT_DIFFERS_FROM_PINNED_MANIFEST")
    ev.require_both_classes(datasets)
    # window-level proof against every earlier population (the FL10 and G1 holdouts are cached in the process: the observer and the generalisation lane build them anyway)
    excluded = {
        "realistic_training_cohort_8_clients": [c.build_dataset(p) for p in c.train_profiles()],
        "original_training_cohort_8_clients": build_cohort()[1],
        "previous_exposed_holdout_8_participants": [build_holdout_dataset(p) for p in holdout_profiles()],
        "fl10_diagnostic_holdout_16_participants": list(holdout_cache.load().datasets),
        "g1_unseen_cohort_16_participants": list(g1_cohort.load().datasets)}
    if cohort == REALISTIC_NSTDB:           # the recorded-noise cohort must also be disjoint from the invented-noise realistic cohort (training and evaluation)
        excluded["realistic_v2_training_cohort_8_clients"] = [v2.build_dataset(p) for p in v2.train_profiles()]
        excluded["realistic_v2_evaluation_cohort_16_participants"] = [v2.build_dataset(p) for p in v2.eval_profiles()]
    separation = ev.separation(datasets, excluded)
    protocol = json.loads((ROOT / ev.PROTOCOL).read_text())          # the method (metrics, threshold, uncertainty settings) is the unchanged FL10 protocol
    labels = np.concatenate([d.labels for d in datasets]).astype(int)
    owners = np.concatenate([[d.participant_id for _ in range(len(d.labels))] for d in datasets])
    inputs = np.concatenate([d.inputs for d in datasets])
    for array in (inputs, labels, owners):
        array.setflags(write=False)
    return FrozenHoldout(tuple(datasets), inputs, labels, owners, entries, separation, protocol, _sha(ROOT / ev.PROTOCOL), _sha(manifest), c.EVAL_COHORT_ID)


def load_realistic(cohort: str = REALISTIC) -> FrozenHoldout:
    with _LOCK:
        if cohort not in _CACHES:
            _CACHES[cohort] = _build_realistic_holdout(cohort)
        return _CACHES[cohort]


def holdout_provider(cohort: str) -> Callable[[], FrozenHoldout]:
    if is_realistic(cohort):
        return lambda: load_realistic(cohort)
    if cohort == ORIGINAL:
        return holdout_cache.load
    raise ValueError("cohort must be ORIGINAL, REALISTIC or REALISTIC_NSTDB")


def loaded_holdout(cohort: str) -> FrozenHoldout | None:
    """The holdout if this process has already built it (never builds)."""
    return _CACHES.get(cohort) if is_realistic(cohort) else holdout_cache._CACHE
