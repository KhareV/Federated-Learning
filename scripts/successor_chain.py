# ruff: noqa: E501
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
    Link("NHM_HARDWARE_MONGO_MONITOR_001", "artifacts/hardware/NHM_HARDWARE_MONGO_MONITOR_001.lock.json", "artifacts/unified_studio/NHM_UNIFIED_LIVE_FEDERATION_STUDIO_001.lock.json",
         "predecessor_lock_sha256", "predecessor_commit", "1501c9de890342d7aa286ed3521053799b48e81e", "frontend_files",
         ("released_model_changed", "calibration_applied_to_candidate", "candidate_promoted_or_deployed", "historical_locks_edited", "automatically_pushed", "frozen_scientific_evidence_edited")),
    Link("NHM_RECORDED_HARDWARE_FL_001", "artifacts/hardware_demo/NHM_RECORDED_HARDWARE_FL_001.lock.json", "artifacts/hardware/NHM_HARDWARE_MONGO_MONITOR_001.lock.json",
         "predecessor_lock_sha256", "predecessor_commit", "e2377adb066381e4914a5c073c56a3ec821ead0c", "frontend_files",
         ("released_model_changed", "calibration_applied_to_candidate", "candidate_promoted_or_deployed", "historical_locks_edited", "automatically_pushed", "frozen_scientific_evidence_edited")),
    Link("NHM_HARDWARE_MONITOR_LIFECYCLE_001", "artifacts/hardware_demo/NHM_HARDWARE_MONITOR_LIFECYCLE_001.lock.json", "artifacts/hardware_demo/NHM_RECORDED_HARDWARE_FL_001.lock.json",
         "predecessor_lock_sha256", "predecessor_commit", "89b89041653d26198261a1028f09652343882257", "frontend_files",
         ("released_model_changed", "calibration_applied_to_candidate", "candidate_promoted_or_deployed", "historical_locks_edited", "automatically_pushed", "frozen_scientific_evidence_edited")),
    Link("NHM_HARDWARE_LIVE_UNIFIED_001", "artifacts/hardware_demo/NHM_HARDWARE_LIVE_UNIFIED_001.lock.json", "artifacts/hardware_demo/NHM_HARDWARE_MONITOR_LIFECYCLE_001.lock.json",
         "predecessor_lock_sha256", "predecessor_commit", "49855ec9da7b349852a7dac34525de5ccb5160fb", "frontend_files",
         ("released_model_changed", "calibration_applied_to_candidate", "candidate_promoted_or_deployed", "historical_locks_edited", "automatically_pushed", "frozen_scientific_evidence_edited")),
    Link("NHM_UI_RESIDUAL_REPAIR_001", "artifacts/ui/NHM_UI_RESIDUAL_REPAIR_001.lock.json", "artifacts/hardware_demo/NHM_HARDWARE_LIVE_UNIFIED_001.lock.json",
         "predecessor_lock_sha256", "predecessor_commit", "21a5fad1bea34fc197a797f55dbda7ca39fded3f", "frontend_files",
         ("released_model_changed", "calibration_applied_to_candidate", "candidate_promoted_or_deployed", "historical_locks_edited", "automatically_pushed", "frozen_scientific_evidence_edited")),
    Link("NHM_HARDWARE_V2_OBSERVATORY_001", "artifacts/hardware_demo/NHM_HARDWARE_V2_OBSERVATORY_001.lock.json", "artifacts/ui/NHM_UI_RESIDUAL_REPAIR_001.lock.json",
         "predecessor_lock_sha256", "predecessor_commit", "4cd4462a4d9a0dab0ee8a890fc9be9f26b1be5cf", "frontend_files",
         ("released_model_changed", "calibration_applied_to_candidate", "candidate_promoted_or_deployed", "historical_locks_edited", "automatically_pushed", "frozen_scientific_evidence_edited")),
    Link("NHM_SESSION_SOURCE_MIXED_TOPOLOGY_001", "artifacts/ui/NHM_SESSION_SOURCE_MIXED_TOPOLOGY_001.lock.json", "artifacts/hardware_demo/NHM_HARDWARE_V2_OBSERVATORY_001.lock.json",
         "predecessor_lock_sha256", "predecessor_commit", "bf335bbd63d29f556f9dde376c12baf6cb97f768", "frontend_files",
         ("released_model_changed", "calibration_applied_to_candidate", "candidate_promoted_or_deployed", "historical_locks_edited", "automatically_pushed", "frozen_scientific_evidence_edited")),
    Link("NHM_STARTER_FLOW_001", "artifacts/ui/NHM_STARTER_FLOW_001.lock.json", "artifacts/ui/NHM_SESSION_SOURCE_MIXED_TOPOLOGY_001.lock.json",
         "predecessor_lock_sha256", "predecessor_commit", "0aeb76173a8812c30a7842a6f283107af1423496", "frontend_files",
         ("released_model_changed", "calibration_applied_to_candidate", "candidate_promoted_or_deployed", "historical_locks_edited", "automatically_pushed", "frozen_scientific_evidence_edited")),
    Link("NHM_HARDWARE_V2_ANY_WINDOW_001", "artifacts/ui/NHM_HARDWARE_V2_ANY_WINDOW_001.lock.json", "artifacts/ui/NHM_STARTER_FLOW_001.lock.json",
         "predecessor_lock_sha256", "predecessor_commit", "cf5eb8633e8a81777f5da0a44632b7148747b8d3", "frontend_files",
         ("released_model_changed", "calibration_applied_to_candidate", "candidate_promoted_or_deployed", "historical_locks_edited", "automatically_pushed", "frozen_scientific_evidence_edited")),
    Link("NHM_HARDWARE_DEMO_SESSION_001", "artifacts/ui/NHM_HARDWARE_DEMO_SESSION_001.lock.json", "artifacts/ui/NHM_HARDWARE_V2_ANY_WINDOW_001.lock.json",
         "predecessor_lock_sha256", "predecessor_commit", "ab74593db2e908ab093d4bcc7f2ae32737594815", "frontend_files",
         ("released_model_changed", "calibration_applied_to_candidate", "candidate_promoted_or_deployed", "historical_locks_edited", "automatically_pushed", "frozen_scientific_evidence_edited")),
    Link("NHM_HARDWARE_STARTER_MODEL_001", "artifacts/ui/NHM_HARDWARE_STARTER_MODEL_001.lock.json", "artifacts/ui/NHM_HARDWARE_DEMO_SESSION_001.lock.json",
         "predecessor_lock_sha256", "predecessor_commit", "1fe230f39e8eddc3c7cb8d39c859e9bdcc8dcc27", "frontend_files",
         ("released_model_changed", "calibration_applied_to_candidate", "candidate_promoted_or_deployed", "historical_locks_edited", "automatically_pushed", "frozen_scientific_evidence_edited")),
    Link("NHM_HARDWARE_REJECTION_REASONS_001", "artifacts/ui/NHM_HARDWARE_REJECTION_REASONS_001.lock.json", "artifacts/ui/NHM_HARDWARE_STARTER_MODEL_001.lock.json",
         "predecessor_lock_sha256", "predecessor_commit", "cf2e26722d8c8980ad5b84ec90cfc9a86501865c", "frontend_files",
         ("released_model_changed", "calibration_applied_to_candidate", "candidate_promoted_or_deployed", "historical_locks_edited", "automatically_pushed", "frozen_scientific_evidence_edited")),
    Link("NHM_REALISTIC_COHORT_001", "artifacts/ui/NHM_REALISTIC_COHORT_001.lock.json", "artifacts/ui/NHM_HARDWARE_REJECTION_REASONS_001.lock.json",
         "predecessor_lock_sha256", "predecessor_commit", "acc855274ef9d3fa554a8bb18b5c6292e981b51b", "frontend_files",
         ("released_model_changed", "calibration_applied_to_candidate", "candidate_promoted_or_deployed", "historical_locks_edited", "automatically_pushed", "frozen_scientific_evidence_edited")),
    Link("NHM_CANDIDATE_LIBRARY_001", "artifacts/ui/NHM_CANDIDATE_LIBRARY_001.lock.json", "artifacts/ui/NHM_REALISTIC_COHORT_001.lock.json",
         "predecessor_lock_sha256", "predecessor_commit", "979efee79349784f97017d2bfc4f0b1211016cb9", "frontend_files",
         ("released_model_changed", "calibration_applied_to_candidate", "candidate_promoted_or_deployed", "historical_locks_edited", "automatically_pushed", "frozen_scientific_evidence_edited")),
    Link("NHM_STATE_CONSISTENCY_AND_DEMO_OPS_001", "artifacts/ui/NHM_STATE_CONSISTENCY_AND_DEMO_OPS_001.lock.json", "artifacts/ui/NHM_CANDIDATE_LIBRARY_001.lock.json",
         "predecessor_lock_sha256", "predecessor_commit", "5f375af26f4a85cd48f324c83d21cf4f3af94e6b", "frontend_files",
         ("released_model_changed", "calibration_applied_to_candidate", "candidate_promoted_or_deployed", "historical_locks_edited", "automatically_pushed", "frozen_scientific_evidence_edited")),
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git_bytes(git_root: Path, commit: str, path: str) -> bytes | None:
    result = subprocess.run(["git", "show", f"{commit}:{path}"], cwd=git_root, capture_output=True)
    return result.stdout if result.returncode == 0 else None


def _git_root(root: Path) -> Path:
    """Where immutable predecessor commits are looked up: an explicit override, the tree itself when it is a repository, else the repository this module lives in
    (shadow trees built by older tests copy locks and frontend files but have no .git)."""
    override = os.environ.get("NHM_GOVERNANCE_GIT_ROOT")
    if override:
        return Path(override)
    return root if (root / ".git").exists() else ROOT


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


def accounted_changes(root: Path = ROOT, links: tuple[Link, ...] = LINKS) -> set[str]:
    """Frontend files whose tip bytes differ from the final-showcase baseline.
    Used by the historical accounting tests: drift is legal only when completely accounted for here. An invalid link raises; there is no fallback."""
    baseline = dict(json.loads((root / FINAL_SHOWCASE).read_text())["bound_artifacts"])
    tip = dict(baseline)
    for link in links:
        if not (root / link.path).exists():
            break
        tip = dict(validate_link(link, root, links)[link.frontend_map_key])
    return {path for path in set(baseline) | set(tip) if baseline.get(path) != tip.get(path)}


def accounted_bound_files(root: Path = ROOT, links: tuple[Link, ...] = LINKS) -> set[str]:
    """All implementation and evidence paths explicitly bound by valid successors."""
    bound: dict[str, str] = {}
    for link in links:
        if not (root / link.path).exists():
            break
        lock = validate_link(link, root, links)
        values = lock.get("bound_files", {})
        if not isinstance(values, dict):
            raise _broken(link, "NO_BOUND_FILES")
        bound.update(values)
    return {path for path, digest in bound.items() if (root / path).is_file() and sha256((root / path).read_bytes()) == digest}
