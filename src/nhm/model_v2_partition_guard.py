"""MODEL_V2-only partition-access firewall (V2-001).

Every MODEL_V2 research stage must explicitly declare which frozen MITDB partitions
(TRAIN/VALIDATION/CALIBRATION/INTERNAL_TEST) or external evaluation domains
(INCART/NSTDB/BIDMC) it is permitted to read waveform or prediction data from. This module
is additive: no existing V1 loader (datasets/*, evaluation/*) is modified. It fails closed --
a forbidden partition raises PartitionAccessViolation before the underlying file is ever
opened -- and logs every successful access to an append-only ledger.

Metadata-only inspection of frozen manifests (CSV/JSON identity, hashes, counts) is NOT
gated here; only waveform/prediction array reads are.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Collection
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

KNOWN_PARTITIONS = frozenset(
    {"TRAIN", "VALIDATION", "CALIBRATION", "INTERNAL_TEST", "INCART", "NSTDB", "BIDMC"}
)

LEDGER_RELATIVE_PATH = "reports/model_v2/access_ledger.jsonl"


class PartitionAccessViolation(PermissionError):
    """A MODEL_V2 stage attempted to read a partition outside its declared allowlist."""


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


def check_partition_allowed(
    partition: str, stage_id: str, allowed_partitions: Collection[str]
) -> None:
    """Raise PartitionAccessViolation if partition is not explicitly allowed for stage_id.

    Call this BEFORE opening any file/cache for a waveform/prediction read."""
    if partition not in KNOWN_PARTITIONS:
        raise PartitionAccessViolation(f"UNKNOWN_PARTITION:{partition}")
    allowed = set(allowed_partitions)
    if not allowed <= KNOWN_PARTITIONS:
        raise PartitionAccessViolation(f"UNKNOWN_ALLOWED_PARTITION:{allowed - KNOWN_PARTITIONS}")
    if partition not in allowed:
        raise PartitionAccessViolation(
            f"MODEL_V2_PARTITION_FIREWALL_DENIED: stage={stage_id} partition={partition} "
            f"allowed={sorted(allowed)}"
        )


def load_model_v2_partition(
    partition: str,
    stage_id: str,
    allowed_partitions: Collection[str],
    *,
    source_path: str | Path,
    root: Path,
    access_type: str = "waveform_read",
    experiment_id: str | None = None,
) -> np.ndarray:
    """Fail-closed waveform/prediction-array loader gated by an explicit per-stage allowlist.

    Raises PartitionAccessViolation BEFORE source_path is opened if partition is not in
    allowed_partitions. On success, loads the array (np.load, allow_pickle=False) and appends
    one row to reports/model_v2/access_ledger.jsonl, then returns the array.
    """
    check_partition_allowed(partition, stage_id, allowed_partitions)

    resolved = Path(source_path)
    array = np.load(resolved, allow_pickle=False)
    rows = int(array.shape[0]) if hasattr(array, "shape") and array.ndim >= 1 else None

    relative = str(resolved.relative_to(root)) if resolved.is_relative_to(root) else str(resolved)
    _append_ledger(
        root,
        {
            "timestamp_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "stage_id": stage_id,
            "experiment_id": experiment_id,
            "partition": partition,
            "access_type": access_type,
            "rows": rows,
            "source_path": relative,
            "git_sha": _git_sha(root),
        },
    )
    return array
