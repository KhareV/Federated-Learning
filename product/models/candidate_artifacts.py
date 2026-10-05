# ruff: noqa: E501
"""CAPSTONE_FL_CANDIDATE artifact files: ``<root>/<candidate_id>/state.bin`` (+ small ``metadata.json``).

Candidate weights live ONLY here (never in SQL). A candidate directory is written serialise -> verify
round trip -> temp directory -> atomic rename; the rename also makes ID allocation atomic across
processes (an existing directory forces the next number). Never committed; the root is injectable."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from federated.model_adapter import deserialize_state, serialize_state
from federated.model_v2_fl import state_sha
from nhm.hashing import hash_bytes
from product.models.registry_contract import CANDIDATE_ID_PATTERN

DEFAULT_ROOT = Path("data/capstone/fl_candidates")
ENV_ROOT = "NHM_FL_CANDIDATE_ROOT"
PREFIX = "CAPSTONE_FL_CANDIDATE_"


class CandidateArtifactError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def candidate_id_for(number: int) -> str:
    return f"{PREFIX}{number:04d}"


class CandidateArtifactStore:
    def __init__(self, root: str | Path = DEFAULT_ROOT) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def directory(self, candidate_id: str) -> Path:
        if not CANDIDATE_ID_PATTERN.match(candidate_id):
            raise CandidateArtifactError("INVALID_CANDIDATE_ID")
        return self.root / candidate_id

    def max_number(self) -> int:
        numbers = [int(p.name[len(PREFIX):]) for p in self.root.iterdir()
                   if p.is_dir() and CANDIDATE_ID_PATTERN.match(p.name)]
        return max(numbers, default=0)

    def write(self, candidate_id: str, state: dict[str, Any], metadata: dict[str, Any]) -> dict[str, str]:
        blob = serialize_state(state)
        if state_sha(deserialize_state(blob)) != state_sha(state):
            raise CandidateArtifactError("STATE_ROUND_TRIP_MISMATCH")
        final = self.directory(candidate_id)
        temp = Path(tempfile.mkdtemp(prefix=f".{candidate_id}.", dir=self.root))
        try:
            record = {**metadata, "candidate_id": candidate_id, "state_digest": state_sha(state),
                      "state_file_sha256": hash_bytes(blob), "state_file": "state.bin"}
            (temp / "state.bin").write_bytes(blob)
            (temp / "metadata.json").write_text(json.dumps(record, indent=1, sort_keys=True) + "\n")
            if hash_bytes((temp / "state.bin").read_bytes()) != record["state_file_sha256"]:
                raise CandidateArtifactError("VERIFY_AFTER_WRITE_FAILED")
            os.rename(temp, final)  # atomic; fails if the directory already exists and is non-empty
        except BaseException:
            shutil.rmtree(temp, ignore_errors=True)
            raise
        return {"state_digest": record["state_digest"],
                "state_file_sha256": record["state_file_sha256"]}

    def read_metadata(self, candidate_id: str) -> dict[str, Any]:
        path = self.directory(candidate_id) / "metadata.json"
        if not path.exists():
            raise CandidateArtifactError("CANDIDATE_ARTIFACT_MISSING")
        return json.loads(path.read_text())

    def load_verified(self, candidate_id: str, expected_digest: str) -> dict[str, Any]:
        """Load the stored state and prove it is the candidate the registry row names."""
        directory = self.directory(candidate_id)
        metadata = self.read_metadata(candidate_id)
        blob = (directory / "state.bin").read_bytes()
        if hash_bytes(blob) != metadata["state_file_sha256"]:
            raise CandidateArtifactError("CANDIDATE_FILE_HASH_MISMATCH")
        state = deserialize_state(blob)
        if state_sha(state) != expected_digest or metadata["state_digest"] != expected_digest:
            raise CandidateArtifactError("CANDIDATE_STATE_DIGEST_MISMATCH")
        return state

    def directories(self) -> list[str]:
        return sorted(p.name for p in self.root.iterdir()
                      if p.is_dir() and CANDIDATE_ID_PATTERN.match(p.name))

    def remove(self, candidate_id: str) -> None:
        shutil.rmtree(self.directory(candidate_id), ignore_errors=True)
