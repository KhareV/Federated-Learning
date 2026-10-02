"""MODEL_V2 TRAIN-CV role-access firewall (V2-002).

Partition-level protection (nhm.model_v2_partition_guard) is insufficient inside V2-002:
OPTIMISE, INNER_VALIDATION, and OUTER_TEST are all patient-group roles that live entirely
inside the already-TRAIN-allowed partition. This module adds a SECOND, additive firewall on
top of (never instead of) the partition guard: every real-waveform read during a CV fit must
declare its role, stage, and outer fold, and is rejected BEFORE any file is opened if that
role is not permitted for the calling stage, or if the declared outer fold does not match the
fit's own experiment fold (wrong-fold rejection), or if an OUTER_TEST read is attempted before
that fit's checkpoint has been explicitly finalized.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Collection
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

KNOWN_ROLES = frozenset({"OPTIMISE", "INNER_VALIDATION", "OUTER_TEST"})

# Stage -> roles that stage is permitted to read waveform data for.
STAGE_ALLOWED_ROLES: dict[str, frozenset[str]] = {
    "V2-002_TRAIN_SELECT": frozenset({"OPTIMISE", "INNER_VALIDATION"}),
    "V2-002_OUTER_EVAL": frozenset({"OUTER_TEST"}),
}

LEDGER_RELATIVE_PATH = "reports/model_v2/v2_002/cv_role_access_ledger.jsonl"


class CVRoleAccessViolation(PermissionError):
    """A V2-002 stage attempted to read a TRAIN-CV role outside its permitted scope, the
    wrong outer fold, or (for OUTER_TEST) before its checkpoint was finalized."""


def _git_sha(root: Path) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _append_ledger(root: Path, row: dict[str, Any]) -> None:
    ledger_path = root / LEDGER_RELATIVE_PATH
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def check_cv_role_allowed(
    role: str,
    stage_id: str,
    *,
    requested_outer_fold: int,
    experiment_outer_fold: int,
    checkpoint_finalized: bool = False,
) -> None:
    """Raise CVRoleAccessViolation BEFORE any file/cache is opened if the access is not
    permitted. Call this first in every real-waveform-reading code path."""
    if role not in KNOWN_ROLES:
        raise CVRoleAccessViolation(f"UNKNOWN_CV_ROLE:{role}")
    if stage_id not in STAGE_ALLOWED_ROLES:
        raise CVRoleAccessViolation(f"UNKNOWN_CV_STAGE:{stage_id}")
    if role not in STAGE_ALLOWED_ROLES[stage_id]:
        raise CVRoleAccessViolation(
            f"CV_ROLE_FIREWALL_DENIED: stage={stage_id} role={role} "
            f"allowed={sorted(STAGE_ALLOWED_ROLES[stage_id])}"
        )
    if requested_outer_fold != experiment_outer_fold:
        raise CVRoleAccessViolation(
            "CV_ROLE_FIREWALL_WRONG_FOLD: "
            f"requested_outer_fold={requested_outer_fold} "
            f"experiment_outer_fold={experiment_outer_fold}"
        )
    if role == "OUTER_TEST" and not checkpoint_finalized:
        raise CVRoleAccessViolation(
            "CV_ROLE_FIREWALL_OUTER_TEST_BEFORE_CHECKPOINT_FINALIZED"
        )


def record_cv_role_access(
    root: Path,
    *,
    task_id: str,
    experiment_id: str,
    outer_fold: int,
    seed: int,
    role: str,
    stage_id: str,
    participant_group_ids: Collection[str],
    example_id_count: int,
    access_purpose: str,
) -> None:
    """Append one row to the CV-role access ledger. Call only AFTER check_cv_role_allowed has
    not raised, and after the waveform read has actually happened."""
    _append_ledger(
        root,
        {
            "timestamp_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "task_id": task_id,
            "experiment_id": experiment_id,
            "outer_fold": outer_fold,
            "seed": seed,
            "role": role,
            "stage_id": stage_id,
            "participant_group_ids": sorted(participant_group_ids),
            "example_id_count": example_id_count,
            "access_purpose": access_purpose,
            "git_sha": _git_sha(root),
        },
    )
