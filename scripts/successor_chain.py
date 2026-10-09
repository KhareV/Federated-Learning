"""Successor-aware resolution of the frontend binding tip after NHM_FINAL_SHOWCASE_001.

The accepted UI verifiers (CAPSTONE_UI_V1 .. V1_9) accept a changed file only if the tip of the lock chain binds exactly its current bytes.
``capstone_ui_v1_8_successor.v18_bound`` resolves the chain up to NHM_FINAL_SHOWCASE_001; the additive successors listed in ``LINKS`` continue it.

A link is honoured only when ALL of the following hold (any failure raises ``RuntimeError("<LOCK_ID>_SUCCESSOR_CHAIN_BROKEN:<why>")``):
  * the successor lock has the expected ``lock_id`` and a PASS status;
  * its recorded predecessor digest equals the sha256 of the predecessor lock bytes currently on disk;
  * those predecessor bytes equal the bytes committed at the recorded immutable predecessor commit (when that commit is reachable);
  * it declares that no historical lock was edited, nothing was pushed, and no model/hardware/promotion scope changed.
There is no blanket allowance: every frontend file must still equal the digest the tip lock binds, and the file set must match exactly.
Historical lock bytes are only ever read."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FINAL_SHOWCASE = "artifacts/final_showcase/NHM_FINAL_SHOWCASE_001.lock.json"
BASELINE_COMMIT = "274323730d1c7355f688ad4c9ff01ecbfb746501"
FL10_COMMIT = "e129a76e1f29d574d733ecf18d3fd686da28d47d"      # the commit that introduced the NHM_FL10_001 lock bytes


@dataclass(frozen=True)
class Link:
    lock_id: str
    path: str
    predecessor_path: str
    predecessor_digest_key: str
    predecessor_commit_key: str | None
    expected_predecessor_commit: str | None
    frontend_map_key: str
    required_false: tuple[str, ...]


# Ordered, append-only. The tip is the last link whose lock file exists.
LINKS: tuple[Link, ...] = (
    Link("NHM_FL10_001", "artifacts/fl10/NHM_FL10_001.lock.json", FINAL_SHOWCASE, "predecessor_lock_sha256", "predecessor_commit", BASELINE_COMMIT,
         "frontend_files", ("released_model_changed", "calibration_applied_to_candidate", "candidate_promoted_or_deployed", "hardware_work_performed",
                            "historical_locks_edited", "automatically_pushed")),
    Link("NHM_UNIFIED_LIVE_FEDERATION_STUDIO_001", "artifacts/unified_studio/NHM_UNIFIED_LIVE_FEDERATION_STUDIO_001.lock.json", "artifacts/fl10/NHM_FL10_001.lock.json", "predecessor_lock_sha256",
         "predecessor_commit", FL10_COMMIT, "frontend_files", ("released_model_changed", "calibration_applied_to_candidate", "candidate_promoted_or_deployed", "hardware_work_performed",
                                                                "historical_locks_edited", "automatically_pushed", "frozen_scientific_evidence_edited")),
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git_bytes(git_root: Path, commit: str, path: str) -> bytes | None:
    result = subprocess.run(["git", "show", f"{commit}:{path}"], cwd=git_root, capture_output=True)
    return result.stdout if result.returncode == 0 else None


def _git_root(root: Path) -> Path:
    return Path(os.environ.get("NHM_GOVERNANCE_GIT_ROOT", str(root)))


def _broken(link: Link, why: str) -> RuntimeError:
    return RuntimeError(f"{link.lock_id}_SUCCESSOR_CHAIN_BROKEN:{why}")


def validate_link(link: Link, root: Path, links: tuple[Link, ...] = LINKS, *, lock_override: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate one additive successor against the exact predecessor identity; return the successor lock.
    ``lock_override`` checks the same rules against an in-memory copy (used by verifiers and tamper controls)."""
    lock_file, predecessor_file = root / link.path, root / link.predecessor_path
    lock = lock_override if lock_override is not None else json.loads(lock_file.read_text(encoding="utf-8"))
    if lock.get("lock_id") != link.lock_id or lock.get("status") != "PASS":
        raise _broken(link, "IDENTITY_OR_STATUS")
    if not predecessor_file.is_file():
        raise _broken(link, "PREDECESSOR_MISSING")
    predecessor_bytes = predecessor_file.read_bytes()
    if lock.get(link.predecessor_digest_key) != sha256(predecessor_bytes):
        raise _broken(link, "PREDECESSOR_DIGEST_MISMATCH")
    commit = lock.get(link.predecessor_commit_key) if link.predecessor_commit_key else None
    if link.expected_predecessor_commit is not None and commit != link.expected_predecessor_commit:
        raise _broken(link, "PREDECESSOR_COMMIT_MISMATCH")
    if commit is not None:
        committed = _git_bytes(_git_root(root), commit, link.predecessor_path)
        if committed is None:
            raise _broken(link, "PREDECESSOR_COMMIT_UNREACHABLE")
        if sha256(committed) != sha256(predecessor_bytes):
            raise _broken(link, "PREDECESSOR_BYTES_DIFFER_FROM_IMMUTABLE_COMMIT")
    for field in link.required_false:
        if lock.get(field) is not False:
            raise _broken(link, f"SCOPE_DRIFT:{field}")
    if not isinstance(lock.get(link.frontend_map_key), dict) or not lock[link.frontend_map_key]:
        raise _broken(link, "NO_FRONTEND_BINDING")
    return lock


def tip_frontend_map(root: Path, links: tuple[Link, ...] = LINKS) -> dict[str, str] | None:
    """Frontend digest map of the last validly chained successor, or None when no successor lock exists (the caller keeps its own tip).

    A successor lock that is present but invalid raises: a broken or forged link never silently falls back to an older tip."""
    tip: dict[str, str] | None = None
    previous_path = FINAL_SHOWCASE
    for link in links:
        if not (root / link.path).exists():
            break
        if link.predecessor_path != previous_path:
            raise _broken(link, "OUT_OF_ORDER")
        tip = dict(validate_link(link, root, links)[link.frontend_map_key])
        previous_path = link.path
    return tip
