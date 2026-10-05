# ruff: noqa: E501
"""CAPSTONE_FEDERATION_RECOVERY_V1 -- restart recovery of RUNNING federation runs.

Only round-boundary resume is supported (arbitrary mid-round resume is not). A RUNNING run is resumed
iff a valid checkpoint exists whose bound identity matches the run (run id, protocol id, cohort
identity, algorithm, planned rounds, last committed round, state sha, state-file sha) and the event log
covers it. Anything else is marked FAILED -- state is never fabricated."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from product.federation.artifact_store import ArtifactError, FederationArtifactStore
from product.federation.execution_binding import BINDING_ID, PROTOCOL_ID

RECOVERY_ID = "CAPSTONE_FEDERATION_RECOVERY_V1"


@dataclass
class RecoveryDecision:
    run_id: str
    action: str                     # RESUME | FAIL
    reason: str
    last_committed_round: int = 0
    record: dict[str, Any] = field(default_factory=dict)
    state: Any = None


def assess(row: dict[str, Any], artifacts: FederationArtifactStore, cohort_identity: str
           ) -> RecoveryDecision:
    run_id = row["run_id"]
    meta = artifacts.read_run_meta(run_id)
    if meta is None or meta.get("run_id") != run_id:
        return RecoveryDecision(run_id, "FAIL", "RUN_METADATA_MISSING_OR_INCONSISTENT")
    latest = artifacts.latest_checkpoint_round(run_id)
    if latest is None:
        return RecoveryDecision(run_id, "FAIL", "NO_VALID_CHECKPOINT")
    try:
        record, state = artifacts.read_checkpoint(run_id, latest)
    except ArtifactError as error:
        return RecoveryDecision(run_id, "FAIL", error.code)
    bindings = {
        "run_id": run_id, "protocol_id": PROTOCOL_ID, "binding_id": BINDING_ID,
        "cohort_manifest_sha256": cohort_identity, "algorithm": row["algorithm"],
        "secagg_mode": row["secagg_mode"], "planned_rounds": row["planned_rounds"],
        "last_committed_round": latest}
    for key, expected in bindings.items():
        if record.get(key) != expected:
            return RecoveryDecision(run_id, "FAIL", f"CHECKPOINT_BINDING_MISMATCH:{key}")
    if not 1 <= latest < row["planned_rounds"]:
        return RecoveryDecision(run_id, "FAIL", "CHECKPOINT_ROUND_OUT_OF_RANGE")
    if len(artifacts.read_events(run_id)) < record.get("event_count", 10**9):
        return RecoveryDecision(run_id, "FAIL", "EVENT_LOG_SHORTER_THAN_CHECKPOINT")
    return RecoveryDecision(run_id, "RESUME", "VALID_CHECKPOINT", latest, record, state)
