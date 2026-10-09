# ruff: noqa: E501
"""The frozen FL10 diagnostic holdout, built once per process through the unchanged FL10 modules and checked before any use.

Checks (all fail closed): protocol and manifest bytes equal the method-freeze digests recorded in the immutable FL10 lock (and, when git is
available, the bytes committed at the method-freeze commit); every dataset equals its manifest entry; both classes exist; zero participant /
session / window-input overlap with the canonical training cohort and the previously exposed 8-participant holdout."""

from __future__ import annotations

import hashlib
import json
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from fl10 import evaluate as ev
from fl10 import holdout
from fl10.constants import METHOD_COMMIT
from studio.constants import FL10_LOCK

ROOT = Path(__file__).resolve().parents[1]


class HoldoutError(RuntimeError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}:{detail}")
        self.code, self.detail = code, detail


@dataclass(frozen=True)
class FrozenHoldout:
    datasets: tuple[Any, ...]
    inputs: np.ndarray
    labels: np.ndarray
    owners: np.ndarray
    entries: list[dict[str, Any]]
    separation: dict[str, Any]
    protocol: dict[str, Any]
    protocol_sha256: str
    manifest_sha256: str
    cohort_id: str

    @property
    def windows(self) -> int:
        return int(self.labels.size)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_protocol_identity(root: Path = ROOT) -> dict[str, str]:
    lock = json.loads((root / FL10_LOCK).read_text())
    out: dict[str, str] = {}
    for relative, expected in lock["method_hashes"].items():
        current = _sha(root / relative)
        if current != expected:
            raise HoldoutError("PROTOCOL_CHANGED_AFTER_METHOD_FREEZE", relative)
        committed = subprocess.run(["git", "show", f"{METHOD_COMMIT}:{relative}"], cwd=root, capture_output=True)
        if committed.returncode == 0 and hashlib.sha256(committed.stdout).hexdigest() != current:
            raise HoldoutError("PROTOCOL_DIFFERS_FROM_METHOD_FREEZE_COMMIT", relative)
        out[relative] = current
    return out


def _build() -> FrozenHoldout:
    from federated.wearable_fl_runner_v1 import build_cohort
    from final_showcase.holdout import build_holdout_dataset, holdout_profiles

    verify_protocol_identity()
    protocol = json.loads((ROOT / ev.PROTOCOL).read_text())
    datasets = [holdout.build_dataset(p) for p in holdout.profiles()]
    entries = ev.check_manifest(protocol, datasets)
    ev.require_both_classes(datasets)
    training = build_cohort()[1]
    separation = ev.separation(datasets, {"training_cohort_8_clients": training, "previous_exposed_holdout_8_participants": [build_holdout_dataset(p) for p in holdout_profiles()]})
    labels = np.concatenate([d.labels for d in datasets]).astype(int)
    owners = np.concatenate([[d.participant_id] * len(d.labels) for d in datasets])
    inputs = np.concatenate([d.inputs for d in datasets])
    for array in (inputs, labels, owners):
        array.setflags(write=False)
    return FrozenHoldout(tuple(datasets), inputs, labels, owners, entries, separation, protocol, _sha(ROOT / ev.PROTOCOL), _sha(ROOT / ev.MANIFEST), holdout.COHORT_ID)


_LOCK = threading.Lock()
_CACHE: FrozenHoldout | None = None


def load() -> FrozenHoldout:
    global _CACHE
    with _LOCK:
        if _CACHE is None:
            _CACHE = _build()
        return _CACHE
