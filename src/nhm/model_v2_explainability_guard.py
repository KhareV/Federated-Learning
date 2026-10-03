"""V2-011 one-shot analysis guards.

Two independent persisted ARMED -> RUNNING -> COMPLETED state machines:

* V2_EXPLAINABILITY_CASE_ACCESS_ONCE -- the four frozen explainability-case waveform accesses.
* V2_NOISE_TYPE_ERROR_ANALYSIS_ONCE  -- the single controlled C031-derived V2 noise-type run.

Same fail-closed semantics as nhm.model_v2_second_look_guard (precondition mismatch, already
consumed, partially consumed) but a separate guard family with separate state files; it does
not reuse the V1 guards, the official-VALIDATION guard, the CAL_V2 guard or the V2-010
second-look guards.
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

GUARDS = ("CASE_ACCESS", "NOISE_TYPE")

GUARD_NAMES = {
    "CASE_ACCESS": "V2_EXPLAINABILITY_CASE_ACCESS_ONCE",
    "NOISE_TYPE": "V2_NOISE_TYPE_ERROR_ANALYSIS_ONCE",
}

GUARD_RELATIVE_PATHS = {
    "CASE_ACCESS": "reports/model_v2/v2_011/case_access_guard.json",
    "NOISE_TYPE": "reports/model_v2/v2_011/noise_type_access_guard.json",
}


class ExplainabilityGuardViolation(PermissionError):
    """Raised before any protected data is touched -- never mid-session."""


def _validate(guard: str) -> None:
    if guard not in GUARDS:
        raise ExplainabilityGuardViolation(f"UNKNOWN_V2_011_GUARD:{guard}")


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _git_sha(root: Path) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else None


def guard_path(root: Path, guard: str) -> Path:
    _validate(guard)
    return root / GUARD_RELATIVE_PATHS[guard]


def read_guard_state(root: Path, guard: str) -> dict[str, Any] | None:
    path = guard_path(root, guard)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write(root: Path, guard: str, state: dict[str, Any]) -> None:
    path = guard_path(root, guard)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def arm_guard(root: Path, guard: str, *, preconditions: dict[str, Any]) -> dict[str, Any]:
    existing = read_guard_state(root, guard)
    if existing is not None:
        raise ExplainabilityGuardViolation(
            f"GUARD_ALREADY_EXISTS:{guard}:state={existing.get('state')}"
        )
    state = {
        "guard_name": GUARD_NAMES[guard],
        "guard": guard,
        "state": "ARMED",
        "armed_at": _now(),
        "armed_git_sha": _git_sha(root),
        "preconditions": preconditions,
    }
    _write(root, guard, state)
    return state


def check_and_begin_session(
    root: Path, guard: str, *, observed_preconditions: dict[str, Any]
) -> dict[str, Any]:
    state = read_guard_state(root, guard)
    if state is None:
        raise ExplainabilityGuardViolation(f"GUARD_NOT_ARMED:{guard}")
    current = state.get("state")
    if current == "COMPLETED":
        raise ExplainabilityGuardViolation(f"{GUARD_NAMES[guard]}_ALREADY_CONSUMED")
    if current == "RUNNING":
        raise ExplainabilityGuardViolation(f"{GUARD_NAMES[guard]}_PARTIALLY_CONSUMED")
    if current != "ARMED":
        raise ExplainabilityGuardViolation(f"GUARD_UNKNOWN_STATE:{guard}:{current}")
    armed = state.get("preconditions", {})
    mismatches = {
        key: {"armed": armed.get(key), "observed": observed_preconditions.get(key)}
        for key in set(armed) | set(observed_preconditions)
        if armed.get(key) != observed_preconditions.get(key)
    }
    if mismatches:
        raise ExplainabilityGuardViolation(f"PRECONDITION_MISMATCH:{guard}:{mismatches}")
    state = {**state, "state": "RUNNING", "running_at": _now(), "running_git_sha": _git_sha(root)}
    _write(root, guard, state)
    return state


def complete_session(
    root: Path, guard: str, *, completion_summary: dict[str, Any]
) -> dict[str, Any]:
    state = read_guard_state(root, guard)
    if state is None or state.get("state") != "RUNNING":
        raise ExplainabilityGuardViolation(
            f"CANNOT_COMPLETE_FROM_STATE:{guard}:{state.get('state') if state else None}"
        )
    state = {
        **state,
        "state": "COMPLETED",
        "completed_at": _now(),
        "completed_git_sha": _git_sha(root),
        "completion_summary": completion_summary,
    }
    _write(root, guard, state)
    return state


def mark_partially_consumed(
    root: Path, guard: str, *, failure_summary: dict[str, Any]
) -> dict[str, Any]:
    state = read_guard_state(root, guard)
    if state is None:
        raise ExplainabilityGuardViolation(f"GUARD_NOT_ARMED:{guard}")
    state = {
        **state,
        "state": "RUNNING",
        "partial_consumption_recorded_at": _now(),
        "failure_summary": failure_summary,
        "requires_human_review": True,
    }
    _write(root, guard, state)
    return state


__all__ = [
    "GUARDS",
    "GUARD_NAMES",
    "GUARD_RELATIVE_PATHS",
    "ExplainabilityGuardViolation",
    "arm_guard",
    "check_and_begin_session",
    "complete_session",
    "guard_path",
    "mark_partially_consumed",
    "read_guard_state",
]
