"""V2-007 one-shot official-VALIDATION access guard.

The frozen MIT-BIH official VALIDATION partition may be scored by MODEL_V2 exactly once, in
one locked session (V2-007 Section 30/31). This module persists ARMED -> RUNNING -> COMPLETED
state to disk (reports/model_v2/v2_007/validation_access_guard.json) so a second invocation --
even from a freshly restarted process -- is rejected BEFORE any waveform data is touched. This
is a SEPARATE, additive firewall on top of (never instead of) the CV-role firewall
(nhm.model_v2_cv_role_guard's OFFICIAL_VALIDATION role, which still requires
checkpoint_finalized=True on every individual read) and the partition firewall
(nhm.model_v2_partition_guard).
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

GUARD_RELATIVE_PATH = "reports/model_v2/v2_007/validation_access_guard.json"


class OfficialValidationGuardViolation(PermissionError):
    """Raised before any waveform data is touched -- never mid-session."""


def _git_sha(root: Path) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else None


def guard_path(root: Path) -> Path:
    return root / GUARD_RELATIVE_PATH


def read_guard_state(root: Path) -> dict[str, Any] | None:
    path = guard_path(root)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_guard_state(root: Path, state: dict[str, Any]) -> None:
    path = guard_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def arm_guard(root: Path, *, preconditions: dict[str, Any]) -> dict[str, Any]:
    """Create the initial ARMED guard file. Call only once, at METHOD_COMMIT time, before any
    V2-007 fit. Raises if a guard file already exists (never re-arm over existing state)."""
    existing = read_guard_state(root)
    if existing is not None:
        raise OfficialValidationGuardViolation(
            f"GUARD_ALREADY_EXISTS: state={existing.get('state')}"
        )
    state = {
        "state": "ARMED",
        "armed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "armed_git_sha": _git_sha(root),
        "preconditions": preconditions,
    }
    _write_guard_state(root, state)
    return state


def check_and_begin_session(
    root: Path, *, observed_preconditions: dict[str, Any]
) -> dict[str, Any]:
    """The ONLY entry point into the one-shot official-VALIDATION session. Call this BEFORE
    loading any official-VALIDATION waveform data.

    - If the guard file is absent: raises (must be armed first, at METHOD_COMMIT time).
    - If state == COMPLETED: raises MODEL_V2_VALIDATION_ALREADY_CONSUMED. No data is touched.
    - If state == RUNNING: raises MODEL_V2_VALIDATION_PARTIALLY_CONSUMED (a prior session
      crashed mid-access; human/audit review is required per V2-007 Section 60 -- this
      function never silently resumes or retries).
    - If state == ARMED: verifies observed_preconditions exactly match the ones recorded at
      arm time (method commit / checkpoint hashes / bootstrap-draw lock / V1 reference
      hashes), then atomically transitions ARMED -> RUNNING and returns the new state.
    """
    state = read_guard_state(root)
    if state is None:
        raise OfficialValidationGuardViolation("GUARD_NOT_ARMED")
    current = state.get("state")
    if current == "COMPLETED":
        raise OfficialValidationGuardViolation("MODEL_V2_VALIDATION_ALREADY_CONSUMED")
    if current == "RUNNING":
        raise OfficialValidationGuardViolation("MODEL_V2_VALIDATION_PARTIALLY_CONSUMED")
    if current != "ARMED":
        raise OfficialValidationGuardViolation(f"GUARD_UNKNOWN_STATE:{current}")

    armed_preconditions = state.get("preconditions", {})
    mismatches = {
        key: {"armed": armed_preconditions.get(key), "observed": observed_preconditions.get(key)}
        for key in set(armed_preconditions) | set(observed_preconditions)
        if armed_preconditions.get(key) != observed_preconditions.get(key)
    }
    if mismatches:
        raise OfficialValidationGuardViolation(f"PRECONDITION_MISMATCH:{mismatches}")

    state = {
        **state,
        "state": "RUNNING",
        "running_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "running_git_sha": _git_sha(root),
    }
    _write_guard_state(root, state)
    return state


def complete_session(root: Path, *, completion_summary: dict[str, Any]) -> dict[str, Any]:
    """Transition RUNNING -> COMPLETED after a fully successful prediction-artifact freeze.
    Raises if the guard is not currently RUNNING (never completes an un-begun or already
    completed session)."""
    state = read_guard_state(root)
    if state is None or state.get("state") != "RUNNING":
        raise OfficialValidationGuardViolation(
            f"CANNOT_COMPLETE_FROM_STATE:{state.get('state') if state else None}"
        )
    state = {
        **state,
        "state": "COMPLETED",
        "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "completed_git_sha": _git_sha(root),
        "completion_summary": completion_summary,
    }
    _write_guard_state(root, state)
    return state


def mark_partially_consumed(root: Path, *, failure_summary: dict[str, Any]) -> dict[str, Any]:
    """Record a crash/failure that occurred AFTER the session began (state was RUNNING).
    Never clears or resumes -- the partition is considered exposed and the guard stays
    permanently blocking until a human/audit review explicitly handles it out-of-band."""
    state = read_guard_state(root)
    if state is None:
        raise OfficialValidationGuardViolation("GUARD_NOT_ARMED")
    state = {
        **state,
        "state": "RUNNING",
        "partial_consumption_recorded_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "failure_summary": failure_summary,
        "requires_human_review": True,
    }
    _write_guard_state(root, state)
    return state


__all__ = [
    "GUARD_RELATIVE_PATH",
    "OfficialValidationGuardViolation",
    "arm_guard",
    "check_and_begin_session",
    "complete_session",
    "guard_path",
    "mark_partially_consumed",
    "read_guard_state",
]
