# ruff: noqa: E501
"""Independent synthetic-task evaluation of genuine federated global states (NHM_SYNTH_FL_EVAL_PROTOCOL_V1). Evaluation only: no gradient step."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import torch

from federated.model_adapter import restore_state
from federated.model_v2_fl import fresh_model_v2, state_sha
from federated.virtual_client_source_v1 import LocalDataset, dataset_semantic_sha
from final_showcase import LANE_LABEL, metrics

PROTOCOL = Path("configs/final_showcase/synth_fl_eval_protocol_v1.json")
MANIFEST = Path("configs/final_showcase/synth_fl_eval_holdout_manifest_v1.json")
STATE_KEYS = ("round_0", "round_1", "round_2", "round_3_candidate")


class EvaluationError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_method_freeze(method_commit: str) -> dict[str, str]:
    """The protocol/manifest in the working tree must be byte-identical to the method-freeze commit, which must be an ancestor of HEAD."""
    out = {}
    for path in (PROTOCOL, MANIFEST):
        committed = subprocess.run(["git", "show", f"{method_commit}:{path}"], capture_output=True, check=True).stdout
        if hashlib.sha256(committed).hexdigest() != sha256_file(path):
            raise EvaluationError("PROTOCOL_CHANGED_AFTER_METHOD_FREEZE")
        out[str(path)] = sha256_file(path)
    if subprocess.run(["git", "merge-base", "--is-ancestor", method_commit, "HEAD"]).returncode != 0:
        raise EvaluationError("METHOD_COMMIT_NOT_ANCESTOR")
    return out


def check_manifest(protocol: dict[str, Any], datasets: list[LocalDataset], training: list[LocalDataset]) -> dict[str, Any]:
    if sha256_file(MANIFEST) != protocol["holdout"]["manifest_sha256"]:
        raise EvaluationError("HOLDOUT_MANIFEST_HASH_MISMATCH")
    manifest = json.loads(MANIFEST.read_text())
    for entry, dataset in zip(manifest["participants"], datasets, strict=True):
        recomputed = dataset_semantic_sha(dataset.inputs, dataset.labels, dataset.right_edges_us)
        if recomputed != entry["dataset_sha256"] or entry["counts"] != dataset.counts:
            raise EvaluationError("HOLDOUT_DATASET_DIFFERS_FROM_MANIFEST")
    return separation(datasets, training)


def separation(holdout: list[LocalDataset], training: list[LocalDataset]) -> dict[str, Any]:
    """Participant/session/seed/window-level disjointness. Raises on any overlap."""
    train_parts, train_sessions = {d.participant_id for d in training}, {d.session_id for d in training}
    if train_parts & {d.participant_id for d in holdout}:
        raise EvaluationError("PARTICIPANT_OVERLAP")
    if train_sessions & {d.session_id for d in holdout}:
        raise EvaluationError("SESSION_OVERLAP")
    train_windows = {hashlib.sha256(np.ascontiguousarray(w).tobytes()).hexdigest() for d in training for w in d.inputs}
    held_windows = {hashlib.sha256(np.ascontiguousarray(w).tobytes()).hexdigest() for d in holdout for w in d.inputs}
    if train_windows & held_windows:
        raise EvaluationError("WINDOW_INPUT_OVERLAP")
    return {"participant_overlap": 0, "session_overlap": 0, "window_input_overlap": 0, "training_windows": len(train_windows), "holdout_windows": len(held_windows)}


def require_both_classes(datasets: list[LocalDataset]) -> None:
    labels = np.concatenate([d.labels for d in datasets])
    if len(set(labels.astype(int).tolist())) < 2:
        raise EvaluationError("MISSING_CLASS_IN_HOLDOUT")


def logits_for(state: dict[str, Any], inputs: np.ndarray) -> np.ndarray:
    model = fresh_model_v2()
    restore_state(model, state)
    model.eval()
    out = []
    with torch.no_grad():
        for start in range(0, len(inputs), 64):
            out.append(model(torch.from_numpy(np.ascontiguousarray(inputs[start:start + 64], dtype=np.float32))).reshape(-1).numpy())
    return np.concatenate(out).astype(np.float64)


def evaluate_state(state: dict[str, Any], datasets: list[LocalDataset], *, bootstrap: dict[str, Any] | None = None) -> dict[str, Any]:
    inputs = np.concatenate([d.inputs for d in datasets])
    labels = np.concatenate([d.labels for d in datasets]).astype(int)
    owners = np.concatenate([[d.participant_id] * len(d.labels) for d in datasets])
    logits = logits_for(state, inputs)
    if not np.isfinite(logits).all():
        raise EvaluationError("NONFINITE_LOGITS")
    result = {"pooled": metrics.classification_metrics(labels, logits), "participant_macro_F1": metrics.participant_macro_f1(owners, labels, logits), "curves": metrics.curves(labels, logits),
              "per_participant": {d.client_id: metrics.classification_metrics(d.labels.astype(int), logits[owners == d.participant_id]) for d in datasets}}
    if bootstrap:
        result["uncertainty"] = metrics.cluster_bootstrap(owners, labels, logits, replicates=bootstrap["replicates"], seed=bootstrap["seed"])
    result["_logits"] = logits
    return result


def digest_check(label: str, state: dict[str, Any], expected: str) -> str:
    actual = state_sha(state)
    if actual != expected:
        raise EvaluationError(f"STATE_DIGEST_MISMATCH:{label}")
    return actual


def label_banner() -> str:
    return LANE_LABEL
