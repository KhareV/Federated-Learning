# ruff: noqa: E501
"""CAPSTONE_FEDERATION_ARTIFACT_STORE_V1 -- local files of the federation plane (never committed).

``<root>/runs/<run_id>/run.json``            small run metadata (incl. replay source, scenario)
``<root>/runs/<run_id>/events.jsonl``        the run's federation events, one JSON object per line
``<root>/runs/<run_id>/checkpoints/round_<r>/{state.bin,checkpoint.json}``   round-boundary checkpoints
Writes of state/metadata files are serialise -> temp -> verify -> atomic rename. The root is injectable
(tests use temporary roots); the default lives under ``data/capstone/federation``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from federated.model_adapter import deserialize_state, serialize_state
from federated.model_v2_fl import state_sha
from nhm.hashing import hash_bytes
from product.events import FEDERATION_ADAPTER, FederationLiveEvent

STORE_ID = "CAPSTONE_FEDERATION_ARTIFACT_STORE_V1"
DEFAULT_ROOT = Path("data/capstone/federation")
ENV_ROOT = "NHM_FEDERATION_ARTIFACT_ROOT"


class ArtifactError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    with temp.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    if temp.read_bytes() != data:
        temp.unlink()
        raise ArtifactError("ARTIFACT_VERIFY_AFTER_WRITE_FAILED")
    os.replace(temp, path)


class FederationArtifactStore:
    def __init__(self, root: str | Path = DEFAULT_ROOT) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # ---- run directory ---------------------------------------------------------------------------
    def run_dir(self, run_id: str) -> Path:
        if not run_id or "/" in run_id or run_id.startswith("."):
            raise ArtifactError("INVALID_RUN_ID")
        return self.root / "runs" / run_id

    def write_run_meta(self, run_id: str, meta: dict[str, Any]) -> None:
        atomic_write(self.run_dir(run_id) / "run.json",
                     (json.dumps(meta, indent=1, sort_keys=True) + "\n").encode())

    def read_run_meta(self, run_id: str) -> dict[str, Any] | None:
        path = self.run_dir(run_id) / "run.json"
        return json.loads(path.read_text()) if path.exists() else None

    # ---- events ----------------------------------------------------------------------------------
    def append_event(self, run_id: str, event: FederationLiveEvent) -> None:
        path = self.run_dir(run_id) / "events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as handle:
            handle.write(json.dumps(event.model_dump(mode="json"), sort_keys=True) + "\n")
            handle.flush()

    def read_events(self, run_id: str) -> list[FederationLiveEvent]:
        path = self.run_dir(run_id) / "events.jsonl"
        if not path.exists():
            return []
        return [FEDERATION_ADAPTER.validate_python(json.loads(line))
                for line in path.read_text().splitlines() if line.strip()]

    def truncate_events(self, run_id: str, count: int) -> None:
        path = self.run_dir(run_id) / "events.jsonl"
        lines = path.read_text().splitlines() if path.exists() else []
        if count > len(lines):
            raise ArtifactError("EVENT_LOG_SHORTER_THAN_CHECKPOINT")
        atomic_write(path, ("".join(line + "\n" for line in lines[:count])).encode())

    # ---- checkpoints -----------------------------------------------------------------------------
    def checkpoint_dir(self, run_id: str, round_id: int) -> Path:
        return self.run_dir(run_id) / "checkpoints" / f"round_{round_id}"

    def write_checkpoint(self, run_id: str, round_id: int, state: dict[str, Any],
                         record: dict[str, Any]) -> dict[str, str]:
        blob = serialize_state(state)
        directory = self.checkpoint_dir(run_id, round_id)
        atomic_write(directory / "state.bin", blob)
        full = {**record, "run_id": run_id, "last_committed_round": round_id,
                "global_state_sha256": state_sha(state), "state_file_sha256": hash_bytes(blob)}
        atomic_write(directory / "checkpoint.json",
                     (json.dumps(full, indent=1, sort_keys=True) + "\n").encode())
        return {"global_state_sha256": full["global_state_sha256"],
                "state_file_sha256": full["state_file_sha256"]}

    def latest_checkpoint_round(self, run_id: str) -> int | None:
        base = self.run_dir(run_id) / "checkpoints"
        if not base.exists():
            return None
        rounds = [int(p.name.split("_")[1]) for p in base.iterdir() if p.name.startswith("round_")]
        return max(rounds) if rounds else None

    def read_checkpoint(self, run_id: str, round_id: int) -> tuple[dict[str, Any], dict[str, Any]]:
        directory = self.checkpoint_dir(run_id, round_id)
        try:
            record = json.loads((directory / "checkpoint.json").read_text())
            blob = (directory / "state.bin").read_bytes()
        except (OSError, ValueError) as error:
            raise ArtifactError("CHECKPOINT_UNREADABLE") from error
        if hash_bytes(blob) != record.get("state_file_sha256"):
            raise ArtifactError("CHECKPOINT_STATE_FILE_HASH_MISMATCH")
        state = deserialize_state(blob)
        if state_sha(state) != record.get("global_state_sha256"):
            raise ArtifactError("CHECKPOINT_STATE_HASH_MISMATCH")
        return record, state
