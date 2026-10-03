"""V2-009 one-shot CALIBRATION access guard (V2_CALIBRATION_ONCE).

Mirrors nhm.model_v2_official_validation_guard's ARMED -> RUNNING -> COMPLETED state
machine exactly, persisted to disk so a second invocation -- even from a freshly restarted
process -- is rejected BEFORE any waveform data is touched. Separate, additive guard: the
official-VALIDATION guard and this CALIBRATION guard are independent one-shot locks over
different partitions.
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

GUARD_RELATIVE_PATH = "reports/model_v2/v2_009/calibration_access_guard.json"


class CalibrationGuardViolation(PermissionError):
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
    """Create the initial ARMED guard file. Call only once, at METHOD_COMMIT time, before
    any V2-009 CALIBRATION access. Raises if a guard file already exists."""
    existing = read_guard_state(root)
    if existing is not None:
        raise CalibrationGuardViolation(f"GUARD_ALREADY_EXISTS: state={existing.get('state')}")
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
    """The ONLY entry point into the one-shot CALIBRATION session. Call this BEFORE loading
    any CALIBRATION waveform data."""
    state = read_guard_state(root)
    if state is None:
        raise CalibrationGuardViolation("GUARD_NOT_ARMED")
    current = state.get("state")
    if current == "COMPLETED":
        raise CalibrationGuardViolation("V2_CALIBRATION_ALREADY_CONSUMED")
    if current == "RUNNING":
        raise CalibrationGuardViolation("V2_CALIBRATION_PARTIALLY_CONSUMED")
    if current != "ARMED":
        raise CalibrationGuardViolation(f"GUARD_UNKNOWN_STATE:{current}")

    armed_preconditions = state.get("preconditions", {})
    mismatches = {
        key: {"armed": armed_preconditions.get(key), "observed": observed_preconditions.get(key)}
        for key in set(armed_preconditions) | set(observed_preconditions)
        if armed_preconditions.get(key) != observed_preconditions.get(key)
    }
    if mismatches:
        raise CalibrationGuardViolation(f"PRECONDITION_MISMATCH:{mismatches}")

    state = {
        **state,
        "state": "RUNNING",
        "running_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "running_git_sha": _git_sha(root),
    }
    _write_guard_state(root, state)
    return state


def complete_session(root: Path, *, completion_summary: dict[str, Any]) -> dict[str, Any]:
    """Transition RUNNING -> COMPLETED after a fully successful prediction-artifact freeze."""
    state = read_guard_state(root)
    if state is None or state.get("state") != "RUNNING":
        raise CalibrationGuardViolation(
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
    """Record a crash/failure that occurred AFTER the session began. Never clears or
    resumes -- the partition is considered exposed and the guard stays permanently blocking
    until a human/audit review explicitly handles it out-of-band."""
    state = read_guard_state(root)
    if state is None:
        raise CalibrationGuardViolation("GUARD_NOT_ARMED")
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
    "CalibrationGuardViolation",
    "arm_guard",
    "check_and_begin_session",
    "complete_session",
    "guard_path",
    "mark_partially_consumed",
    "read_guard_state",
]
