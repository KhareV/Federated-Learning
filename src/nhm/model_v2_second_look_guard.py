"""V2-010 one-shot guards for the three post-freeze second-look partitions.

Three fully independent persisted ARMED -> RUNNING -> COMPLETED state machines, one per
dataset ("INTERNAL_TEST", "INCART", "NSTDB"), each with its own guard file so that completing
one never affects the other two. Mirrors nhm.model_v2_calibration_guard's semantics exactly
(same state names, same precondition-mismatch check, same fail-closed behaviour) but is a
brand-new guard family: it does NOT reuse the V1 one-shot guards, the V2-007 official-
VALIDATION guard, or the V2-009 CALIBRATION guard. Only three dataset values are accepted.
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DATASETS = ("INTERNAL_TEST", "INCART", "NSTDB")

GUARD_RELATIVE_PATHS = {
    "INTERNAL_TEST": "reports/model_v2/v2_010/internal_test_second_look_guard.json",
    "INCART": "reports/model_v2/v2_010/incart_second_look_guard.json",
    "NSTDB": "reports/model_v2/v2_010/nstdb_second_look_guard.json",
}

GUARD_NAMES = {
    "INTERNAL_TEST": "V2_INTERNAL_TEST_SECOND_LOOK",
    "INCART": "V2_INCART_SECOND_LOOK",
    "NSTDB": "V2_NSTDB_SECOND_LOOK",
}


class SecondLookGuardViolation(PermissionError):
    """Raised before any waveform data is touched -- never mid-session."""


def _validate_dataset(dataset: str) -> None:
    if dataset not in DATASETS:
        raise SecondLookGuardViolation(f"UNKNOWN_SECOND_LOOK_DATASET:{dataset}")


def _git_sha(root: Path) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else None


def guard_path(root: Path, dataset: str) -> Path:
    _validate_dataset(dataset)
    return root / GUARD_RELATIVE_PATHS[dataset]


def read_guard_state(root: Path, dataset: str) -> dict[str, Any] | None:
    path = guard_path(root, dataset)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_guard_state(root: Path, dataset: str, state: dict[str, Any]) -> None:
    path = guard_path(root, dataset)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def arm_guard(root: Path, dataset: str, *, preconditions: dict[str, Any]) -> dict[str, Any]:
    """Create the initial ARMED guard file for one dataset. Call only once per dataset, at
    METHOD_COMMIT time, before any access to that dataset's waveform/prediction data."""
    existing = read_guard_state(root, dataset)
    if existing is not None:
        raise SecondLookGuardViolation(
            f"GUARD_ALREADY_EXISTS:{dataset}:state={existing.get('state')}"
        )
    state = {
        "guard_name": GUARD_NAMES[dataset],
        "dataset": dataset,
        "state": "ARMED",
        "armed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "armed_git_sha": _git_sha(root),
        "preconditions": preconditions,
    }
    _write_guard_state(root, dataset, state)
    return state


def check_and_begin_session(
    root: Path, dataset: str, *, observed_preconditions: dict[str, Any]
) -> dict[str, Any]:
    """The ONLY entry point into the one-shot session for this dataset. Call this BEFORE
    loading any of that dataset's waveform/prediction data."""
    state = read_guard_state(root, dataset)
    if state is None:
        raise SecondLookGuardViolation(f"GUARD_NOT_ARMED:{dataset}")
    current = state.get("state")
    if current == "COMPLETED":
        raise SecondLookGuardViolation(f"{GUARD_NAMES[dataset]}_ALREADY_CONSUMED")
    if current == "RUNNING":
        raise SecondLookGuardViolation(f"{GUARD_NAMES[dataset]}_PARTIALLY_CONSUMED")
    if current != "ARMED":
        raise SecondLookGuardViolation(f"GUARD_UNKNOWN_STATE:{dataset}:{current}")

    armed_preconditions = state.get("preconditions", {})
    mismatches = {
        key: {"armed": armed_preconditions.get(key), "observed": observed_preconditions.get(key)}
        for key in set(armed_preconditions) | set(observed_preconditions)
        if armed_preconditions.get(key) != observed_preconditions.get(key)
    }
    if mismatches:
        raise SecondLookGuardViolation(f"PRECONDITION_MISMATCH:{dataset}:{mismatches}")

    state = {
        **state,
        "state": "RUNNING",
        "running_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "running_git_sha": _git_sha(root),
    }
    _write_guard_state(root, dataset, state)
    return state


def complete_session(
    root: Path, dataset: str, *, completion_summary: dict[str, Any]
) -> dict[str, Any]:
    """Transition RUNNING -> COMPLETED after a fully successful prediction-artifact freeze."""
    state = read_guard_state(root, dataset)
    if state is None or state.get("state") != "RUNNING":
        raise SecondLookGuardViolation(
            f"CANNOT_COMPLETE_FROM_STATE:{dataset}:"
            f"{state.get('state') if state else None}"
        )
    state = {
        **state,
        "state": "COMPLETED",
        "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "completed_git_sha": _git_sha(root),
        "completion_summary": completion_summary,
    }
    _write_guard_state(root, dataset, state)
    return state


def mark_partially_consumed(
    root: Path, dataset: str, *, failure_summary: dict[str, Any]
) -> dict[str, Any]:
    """Record a crash/failure that occurred AFTER the session began. Never clears or
    resumes -- the partition is considered exposed and the guard stays permanently blocking
    until a human/audit review explicitly handles it out-of-band."""
    state = read_guard_state(root, dataset)
    if state is None:
        raise SecondLookGuardViolation(f"GUARD_NOT_ARMED:{dataset}")
    state = {
        **state,
        "state": "RUNNING",
        "partial_consumption_recorded_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "failure_summary": failure_summary,
        "requires_human_review": True,
    }
    _write_guard_state(root, dataset, state)
    return state


__all__ = [
    "DATASETS",
    "GUARD_NAMES",
    "GUARD_RELATIVE_PATHS",
    "SecondLookGuardViolation",
    "arm_guard",
    "check_and_begin_session",
    "complete_session",
    "guard_path",
    "mark_partially_consumed",
    "read_guard_state",
]
