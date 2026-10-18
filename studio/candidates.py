# ruff: noqa: E501
"""The Studio candidate library: durable engineering candidates of completed federated runs, usable as a starting model of a later run.

A completed run of the V2-family engines (the extended synthetic engine in either source mode, and the pretrained-V2 recorded-hardware engine) ends in ONE final engineering candidate. Until now it
lived only inside its run directory, which belongs to a per-launch temporary workspace, so it vanished with the next restart and could not be reused. The library stores each final state beside its
metadata in a stable directory (default ``data/studio_candidates``, override with ``NHM_CANDIDATE_LIBRARY_DIR``), one directory per owner and candidate:

    <root>/<owner tag>/<candidate id>/candidate.json      identity, cohort, source, settings, base model, evaluation snapshot, digest
    <root>/<owner tag>/<candidate id>/state.bin           the serialized final global state

What a candidate is NOT (unchanged): not promoted, not deployed, not registered in the product model registry, never used for monitoring, never a scientific result. It is an engineering artefact.
Starting a run from one is an explicit, labelled choice: the state is verified against its recorded digest and against the exact FL model layout before any training, and fails closed otherwise.
A candidate trained on one synthetic cohort may start a run on another; the run records both cohorts so the page can say so. A candidate belongs to the owner who ran it."""

from __future__ import annotations

import hashlib
import json
import os
from collections import OrderedDict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from federated.model_adapter import deserialize_state, extract_state, restore_state, serialize_state
from federated.model_v2_fl import state_sha
from fl10.runner import atomic_write
from studio import isolated_eval

ROOT = Path(__file__).resolve().parents[1]
ENV_ROOT = "NHM_CANDIDATE_LIBRARY_DIR"
SCHEMA = "STUDIO_ENGINEERING_CANDIDATE_V1"
LABEL = "ENGINEERING CANDIDATE - NOT PROMOTED - NOT CLINICAL"
SOURCE_KINDS = ("SYNTHETIC_COHORT", "LIVE_MONITORED_SITE", "RECORDED_HARDWARE")
METRIC_KEYS = ("AUPRC", "AUROC", "F1", "accuracy", "precision", "recall", "specificity", "BCE", "Brier", "windows")


class CandidateError(RuntimeError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}:{detail}" if detail else code)
        self.code, self.detail = code, detail


def default_root(env: dict[str, str] | None = None) -> Path:
    configured = (env if env is not None else os.environ).get(ENV_ROOT)
    return Path(configured) if configured else ROOT / "data/studio_candidates"


def _owner_tag(owner: str) -> str:
    return hashlib.sha256(owner.encode()).hexdigest()[:16]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def verify_layout(state: dict[str, np.ndarray]) -> None:
    """Fails closed unless the state has exactly the FL model's keys, order, shapes, dtypes and finite values and survives a strict load round trip unchanged."""
    isolated_eval.prepare_template()
    template = isolated_eval._TEMPLATE
    assert template is not None
    reference = extract_state(template)
    if list(state) != list(reference):
        raise CandidateError("STATE_KEYS_OR_ORDER_DIFFER", f"{len(state)} vs {len(reference)}")
    for key, array in state.items():
        ref = reference[key]
        if array.shape != ref.shape or array.dtype != ref.dtype:
            raise CandidateError("STATE_LAYOUT_MISMATCH", f"{key}:{array.shape}/{array.dtype} vs {ref.shape}/{ref.dtype}")
        if np.issubdtype(array.dtype, np.floating) and not np.isfinite(array).all():
            raise CandidateError("STATE_NONFINITE", key)
    import copy

    model = copy.deepcopy(template)
    restore_state(model, state)
    if state_sha(OrderedDict(extract_state(model))) != state_sha(OrderedDict(state)):
        raise CandidateError("STATE_ROUND_TRIP_DIGEST_MISMATCH")


def audit_of(entry: dict[str, Any]) -> dict[str, Any]:
    """The base-model description of a run that starts from this candidate (also usable before the state is loaded)."""
    return {"model_id": entry["candidate_id"], "kind": "CANDIDATE", "family": "V2", "architecture_id": "V2_FL_MODEL_LAYOUT", "state_sha256": entry["state_sha256"],
            "label": f"Engineering candidate {entry['candidate_id']} (federated, {entry['cohort']} synthetic cohort)", "training_target_of_checkpoint": "SYNTHETIC ENGINEERING EVENTS (federated engineering candidate)",
            "parent_model_id": (entry.get("base_model") or {}).get("model_id"), "source_run_id": entry["source_run_id"], "source_kind": entry["source_kind"], "candidate_cohort": entry["cohort"], "candidate_run_length": entry["run_length"]}


class CandidateLibrary:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    # ---- paths -------------------------------------------------------------------------------------------------------
    def _dir(self, owner: str, candidate_id: str) -> Path:
        if not candidate_id or "/" in candidate_id or "\\" in candidate_id or candidate_id.startswith("."):
            raise CandidateError("INVALID_CANDIDATE_ID")
        return self.root / _owner_tag(owner) / candidate_id

    # ---- write -------------------------------------------------------------------------------------------------------
    def register(self, *, owner: str, candidate_id: str, source_run_id: str, source_kind: str, source_detail: dict[str, Any], cohort: str, evaluation_cohort_id: str | None, run_length: int, algorithm: str,
                 secagg_mode: str, base_model: dict[str, Any], state: dict[str, np.ndarray], metrics: dict[str, Any] | None, round_id: int | None = None) -> dict[str, Any]:
        """Store the final state of a completed run. Idempotent: registering the same candidate again returns the stored entry, and a different state under the same id is refused."""
        if source_kind not in SOURCE_KINDS:
            raise CandidateError("UNKNOWN_SOURCE_KIND", source_kind)
        verify_layout(state)
        digest = state_sha(OrderedDict(state))
        directory = self._dir(owner, candidate_id)
        existing = directory / "candidate.json"
        if existing.exists():
            entry = json.loads(existing.read_text())
            if entry["state_sha256"] != digest:
                raise CandidateError("CANDIDATE_ID_REUSED_WITH_DIFFERENT_STATE", candidate_id)
            return entry
        entry = {
            "schema_version": SCHEMA, "candidate_id": candidate_id, "owner": owner, "created_at": _now(), "label": LABEL, "source_run_id": source_run_id, "source_kind": source_kind, "source_detail": source_detail,
            "cohort": cohort, "evaluation_cohort_id": evaluation_cohort_id, "run_length": int(run_length), "round_id": int(round_id if round_id is not None else run_length), "algorithm": algorithm, "secagg_mode": secagg_mode,
            "base_model": base_model, "state_sha256": digest, "metrics": {k: metrics[k] for k in METRIC_KEYS if metrics and k in metrics} or None,
            "promoted": False, "deployed": False, "registered_in_product_registry": False, "used_for_monitoring": False,
        }
        atomic_write(directory / "state.bin", serialize_state(state))
        atomic_write(directory / "candidate.json", (json.dumps(entry, indent=1, sort_keys=True) + "\n").encode())      # written last: an entry without it is incomplete and never listed
        return entry

    # ---- read --------------------------------------------------------------------------------------------------------
    def list(self, owner: str) -> list[dict[str, Any]]:
        base = self.root / _owner_tag(owner)
        entries = []
        for path in sorted(base.glob("*/candidate.json")) if base.is_dir() else []:
            try:
                entry = json.loads(path.read_text())
            except (OSError, ValueError):
                continue
            if entry.get("owner") == owner and (path.parent / "state.bin").is_file():
                entries.append(entry)
        return sorted(entries, key=lambda e: e["created_at"], reverse=True)

    def get(self, owner: str, candidate_id: str) -> dict[str, Any]:
        path = self._dir(owner, candidate_id) / "candidate.json"
        if not path.exists():
            raise LookupError("candidate not found")
        entry = json.loads(path.read_text())
        if entry.get("owner") != owner:
            raise PermissionError("not the owner of this candidate")
        return entry

    def load_for_start(self, owner: str, candidate_id: str) -> tuple[OrderedDict[str, np.ndarray], dict[str, Any]]:
        """(state, audit) of a candidate to be used as the R0 state of a new run. Fails closed on any digest, layout or finiteness difference."""
        entry = self.get(owner, candidate_id)
        state = OrderedDict(deserialize_state((self._dir(owner, candidate_id) / "state.bin").read_bytes()))
        digest = state_sha(state)
        if digest != entry["state_sha256"]:
            raise CandidateError("CANDIDATE_STATE_DIGEST_MISMATCH", f"{digest[:12]} != {entry['state_sha256'][:12]}")
        verify_layout(state)
        return state, audit_of(entry) | {"strict_load_round_trip_equal": True}
