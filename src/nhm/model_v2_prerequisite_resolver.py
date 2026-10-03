"""Generic MODEL_V2-only prerequisite resolver.

Integrates the narrow resolves_conditional_skip predicate (model_v2_conditional_prerequisite)
into an actual prerequisite-resolution path for the MODEL_V2 lineage. A prerequisite task is
resolved when its status is PASS, or when it is SKIPPED_BY_PROTOCOL and the narrow predicate
confirms the skip is backed by a predeclared conditional branch and frozen disposition
evidence. This module is MODEL_V2-only and never touches canonical T001-T036 prerequisite
semantics, which are governed entirely by src/nhm/coverage.py.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import yaml

from nhm.model_v2_conditional_prerequisite import resolves_conditional_skip

ROOT = Path(__file__).resolve().parents[2]


def is_v2_prerequisite_resolved(
    status: str,
    *,
    task_predeclares_conditional_skip: bool = False,
    has_frozen_disposition_evidence: bool = False,
) -> bool:
    """A MODEL_V2 prerequisite is resolved if PASS outright, or if SKIPPED_BY_PROTOCOL and
    the narrow conditional-skip predicate confirms it. Never treats SKIPPED_BY_PROTOCOL as
    resolved on its own -- the caller must supply real evidence flags."""
    if status == "PASS":
        return True
    return resolves_conditional_skip(
        status, task_predeclares_conditional_skip, has_frozen_disposition_evidence
    )


def v2_005_prerequisite_resolved_for_v2_007(root: Path = ROOT) -> bool:
    """Reads the actual committed V2-005 registry row, the frozen active protocol, and
    hybrid_disposition.json evidence, and returns whether V2-005 is a resolved prerequisite
    for V2-007, under the frozen conditional contract: status SKIPPED_BY_PROTOCOL, hybrid
    trigger FALSE, disposition evidence exists and is internally consistent, zero hybrid
    fits, and V2G4 PASS.

    The predeclaration check reads the active protocol's own
    hybrid_trigger.if_false_task_status field (frozen, immutable) rather than scanning the
    registry's free-text notes column -- notes prose legitimately gets rewritten with
    outcome-specific wording once a result exists, so it is not a dependable predeclaration
    signal."""
    with (root / "manifests/model_v2/task_registry_v1.csv").open(newline="") as handle:
        tasks = {row["task_id"]: row for row in csv.DictReader(handle)}
    with (root / "manifests/model_v2/gate_registry_v1.csv").open(newline="") as handle:
        gates = {row["gate_id"]: row["status"] for row in csv.DictReader(handle)}

    v2_005_row = tasks.get("V2-005")
    if v2_005_row is None:
        return False

    status = v2_005_row["status"]

    protocol_path = root / "configs/model_v2/research_protocol_v2.yaml"
    protocol = yaml.safe_load(protocol_path.read_text(encoding="utf-8"))
    predeclared = (
        protocol.get("hybrid_trigger", {}).get("if_false_task_status") == "SKIPPED_BY_PROTOCOL"
    )

    disposition_path = root / "reports/model_v2/v2_005/hybrid_disposition.json"
    has_evidence = disposition_path.exists()
    if has_evidence:
        disposition = json.loads(disposition_path.read_text(encoding="utf-8"))
        has_evidence = (
            disposition.get("trigger") is False
            and disposition.get("hybrid_model_created") is False
            and disposition.get("neural_fits_added") == 0
        )

    v2g4_pass = gates.get("V2G4") == "PASS"

    return (
        is_v2_prerequisite_resolved(
            status,
            task_predeclares_conditional_skip=predeclared,
            has_frozen_disposition_evidence=has_evidence,
        )
        and v2g4_pass
    )
