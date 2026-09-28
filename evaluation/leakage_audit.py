"""Reusable, dataset-agnostic leakage-audit primitives.

Owns: patient/group disjointness checks, partition-vocabulary/role/fit-scope contracts, the
external (INCART) data-role guard, a window-manifest provenance leakage auditor, and the
frozen-split verifier (`verify_frozen_split`) that later tasks (T011+) call before consuming
`MITDB_SPLIT_V1`.

Deliberately independent of PyTorch, models, training, Flower, FastAPI, and the dashboard --
this module must be importable by pure split/leakage validation without dragging in any model
runtime. All checks fail closed: on any detected problem they either return a FAIL status
report or raise a typed `LeakageAuditError` subclass, never silently continue.
"""

from __future__ import annotations

import itertools
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from nhm.hashing import hash_file

PARTITIONS: tuple[str, ...] = ("TRAIN", "VALIDATION", "CALIBRATION", "INTERNAL_TEST")


class LeakageAuditError(Exception):
    """Base class for every leakage-audit failure. Callers must not catch-and-continue."""


class SplitHashMismatch(LeakageAuditError):
    pass


class SplitPatientOverlap(LeakageAuditError):
    pass


class SplitGroupingMismatch(LeakageAuditError):
    pass


class SplitEligibilityMismatch(LeakageAuditError):
    pass


class SplitUpstreamMismatch(LeakageAuditError):
    pass


class PartitionRoleViolation(LeakageAuditError):
    pass


class FitScopeViolation(LeakageAuditError):
    pass


class ExternalDataRoleViolation(LeakageAuditError):
    pass


class WindowLeakageError(LeakageAuditError):
    pass


# ---------------------------------------------------------------------------------------
# Population / disjointness audits (generic; operate on plain row mappings, no dataset I/O)
# ---------------------------------------------------------------------------------------


def audit_eligible_record_closure(
    split_rows: Sequence[Mapping[str, str]], eligible_record_ids: Iterable[str]
) -> dict[str, Any]:
    split_ids = {row["record_id"] for row in split_rows}
    eligible_set = set(eligible_record_ids)
    missing = sorted(eligible_set - split_ids)
    extra = sorted(split_ids - eligible_set)
    errors = []
    if missing:
        errors.append(f"missing eligible records: {missing}")
    if extra:
        errors.append(f"unexpected records in split: {extra}")
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "missing": missing,
        "extra": extra,
    }


def audit_group_disjointness(
    rows: Sequence[Mapping[str, str]], group_field: str, partition_field: str
) -> dict[str, Any]:
    """Generic reusable check: no value of `group_field` may appear under more than one
    distinct value of `partition_field`. Used for the MITDB patient/record/hash audits here
    and, unchanged, for federated client manifests (T025)."""
    groups_by_partition: dict[str, set[str]] = {}
    for row in rows:
        groups_by_partition.setdefault(row[partition_field], set()).add(row[group_field])
    partitions = sorted(groups_by_partition)
    overlaps: list[tuple[str, str, list[str]]] = []
    for left, right in itertools.combinations(partitions, 2):
        overlap = groups_by_partition[left] & groups_by_partition[right]
        if overlap:
            overlaps.append((left, right, sorted(overlap)))
    return {
        "status": "PASS" if not overlaps else "FAIL",
        "pairwise_overlaps": overlaps,
        "partitions": partitions,
    }


def audit_group_assignment_completeness(
    split_rows: Sequence[Mapping[str, str]], eligible_group_ids: Iterable[str]
) -> dict[str, Any]:
    groups_in_split: dict[str, set[str]] = {}
    for row in split_rows:
        groups_in_split.setdefault(row["participant_group_id"], set()).add(row["partition"])
    eligible_set = set(eligible_group_ids)
    assigned_set = set(groups_in_split)
    unassigned = sorted(eligible_set - assigned_set)
    unexpected = sorted(assigned_set - eligible_set)
    multiply_assigned = sorted(
        group_id for group_id, partitions in groups_in_split.items() if len(partitions) > 1
    )
    errors = []
    if unassigned:
        errors.append(f"unassigned eligible groups: {unassigned}")
    if unexpected:
        errors.append(f"assigned groups outside eligible set: {unexpected}")
    if multiply_assigned:
        errors.append(f"groups spanning multiple partitions: {multiply_assigned}")
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "unassigned_count": len(unassigned),
        "multiply_assigned_count": len(multiply_assigned),
    }


def audit_partition_vocabulary(
    rows: Sequence[Mapping[str, str]], allowed: Iterable[str] = PARTITIONS
) -> dict[str, Any]:
    observed = {row["partition"] for row in rows}
    invalid = sorted(observed - set(allowed))
    return {"status": "PASS" if not invalid else "FAIL", "invalid_partitions": invalid}


def audit_group_invariant(
    split_rows: Sequence[Mapping[str, str]], record_ids: Sequence[str]
) -> dict[str, Any]:
    """Assert every record in `record_ids` shares one participant_group_id and one partition
    (the 201/202 invariant, generalized to any fixed multi-record set)."""
    matching = [row for row in split_rows if row["record_id"] in record_ids]
    groups = {row["participant_group_id"] for row in matching}
    partitions = {row["partition"] for row in matching}
    same_group = len(groups) == 1 and len(matching) == len(record_ids)
    same_partition = len(partitions) == 1 and len(matching) == len(record_ids)
    return {
        "status": "PASS" if same_group and same_partition else "FAIL",
        "same_group": same_group,
        "same_partition": same_partition,
        "group_id": next(iter(groups)) if len(groups) == 1 else None,
        "partition": next(iter(partitions)) if len(partitions) == 1 else None,
        "record_count_found": len(matching),
    }


# ---------------------------------------------------------------------------------------
# Partition-use and fit-scope contracts (v2.2 Section 11 leakage matrix)
# ---------------------------------------------------------------------------------------

PARTITION_ALLOWED_OPERATIONS: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "TRAIN": frozenset(
            {
                "FIT_MODEL_WEIGHTS", "FIT_FEATURE_TRANSFORM", "FIT_SCALER",
                "DERIVE_AUGMENTATION", "DERIVE_MAJORITY_BASELINE",
            }
        ),
        "VALIDATION": frozenset({"MODEL_SELECTION", "HYPERPARAMETER_SELECTION", "EARLY_STOPPING"}),
        "CALIBRATION": frozenset({"TEMPERATURE_SCALING", "THRESHOLD_SELECTION"}),
        "INTERNAL_TEST": frozenset({"FINAL_LOCKED_INTERNAL_EVALUATION"}),
    }
)

# The exact partition set each operation must be fit on -- neither a subset nor a superset.
FIT_SCOPE_CONTRACT: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "FIT_MODEL_WEIGHTS": frozenset({"TRAIN"}),
        "FIT_FEATURE_TRANSFORM": frozenset({"TRAIN"}),
        "FIT_SCALER": frozenset({"TRAIN"}),
        "DERIVE_AUGMENTATION": frozenset({"TRAIN"}),
        "DERIVE_MAJORITY_BASELINE": frozenset({"TRAIN"}),
        "MODEL_SELECTION": frozenset({"VALIDATION"}),
        "HYPERPARAMETER_SELECTION": frozenset({"VALIDATION"}),
        "EARLY_STOPPING": frozenset({"VALIDATION"}),
        "TEMPERATURE_SCALING": frozenset({"CALIBRATION"}),
        "THRESHOLD_SELECTION": frozenset({"CALIBRATION"}),
        "FINAL_LOCKED_INTERNAL_EVALUATION": frozenset({"INTERNAL_TEST"}),
    }
)


def assert_partition_use_allowed(partition: str, operation: str) -> None:
    """Raise PartitionRoleViolation unless `operation` is one of the operations locked v2.2
    Section 11 permits on `partition`."""
    if partition not in PARTITION_ALLOWED_OPERATIONS:
        raise PartitionRoleViolation(f"unknown partition {partition!r}")
    allowed = PARTITION_ALLOWED_OPERATIONS[partition]
    if operation not in allowed:
        raise PartitionRoleViolation(
            f"operation {operation!r} is not permitted on partition {partition!r}; "
            f"allowed: {sorted(allowed)}"
        )


def audit_fit_scope(operation: str, fit_partitions: Sequence[str]) -> None:
    """Raise FitScopeViolation unless `operation` was fit on exactly its permitted partition
    set -- catches both leakage (fitting on TRAIN+VALIDATION) and role violations (fitting a
    TRAIN-only operation on CALIBRATION)."""
    if operation not in FIT_SCOPE_CONTRACT:
        raise FitScopeViolation(f"unknown operation {operation!r}")
    allowed_partitions = FIT_SCOPE_CONTRACT[operation]
    observed = set(fit_partitions)
    if observed != allowed_partitions:
        raise FitScopeViolation(
            f"{operation!r} must be fit on exactly {sorted(allowed_partitions)}, "
            f"got {sorted(observed)}"
        )


# ---------------------------------------------------------------------------------------
# External-dataset (INCART) role guard -- T007 dataset_roles_v1.yaml lock, contract only
# ---------------------------------------------------------------------------------------

# INCART is locked_external_evaluation_only (T007): none of these operations may ever use
# INCART, before or after the single frozen primary external run (T020) -- including using
# INCART's own results to retroactively tune anything upstream.
INCART_FORBIDDEN_OPERATIONS: frozenset[str] = frozenset(
    {
        "TRAINING", "MODEL_SELECTION", "THRESHOLD_SELECTION", "TEMPERATURE_SCALING",
        "LEAD_SELECTION", "MAPPING_ADAPTATION", "PREPROCESSING_TUNING",
    }
)


def assert_incart_operation_allowed(operation: str) -> None:
    if operation in INCART_FORBIDDEN_OPERATIONS:
        raise ExternalDataRoleViolation(
            f"INCART operation {operation!r} is forbidden -- INCART is locked "
            "external-evaluation-only (T007 dataset role lock); this may never occur, "
            "before or after the primary frozen external run (T020)."
        )


# ---------------------------------------------------------------------------------------
# Window-manifest provenance leakage audit (synthetic harness now; real windows at T013)
# ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class WindowAuditRow:
    example_id: str
    participant_group_id: str
    record_id: str
    partition: str
    start_sample: int
    end_sample: int
    source_hash: str


def _intervals_overlap_or_adjacent(a: WindowAuditRow, b: WindowAuditRow) -> bool:
    return not (a.end_sample < b.start_sample or b.end_sample < a.start_sample)


def audit_window_manifest(
    rows: Sequence[WindowAuditRow],
    split_lookup: Mapping[str, tuple[str, str]],
    eligible_record_ids: Iterable[str],
) -> dict[str, Any]:
    """Operates on window provenance metadata only -- never waveform arrays. `split_lookup`
    maps record_id -> (participant_group_id, partition) from the frozen split. Detects:
    duplicate example_id, excluded-record leakage, partition/grouping inheritance mismatch,
    patient/record/source-hash crossing across partitions, and cross-partition overlapping
    or neighboring intervals from the same record. Within-partition overlap is expected and
    never flagged."""
    errors: list[str] = []
    eligible = set(eligible_record_ids)

    example_ids = [row.example_id for row in rows]
    duplicate_ids = sorted({eid for eid in example_ids if example_ids.count(eid) > 1})
    if duplicate_ids:
        errors.append(f"duplicate example_id(s): {duplicate_ids}")

    excluded_hits = sorted({row.record_id for row in rows if row.record_id not in eligible})
    if excluded_hits:
        errors.append(f"window references ineligible/excluded record(s): {excluded_hits}")

    for row in rows:
        if row.record_id not in split_lookup:
            continue
        expected_group, expected_partition = split_lookup[row.record_id]
        if row.participant_group_id != expected_group:
            errors.append(
                f"{row.example_id}: participant_group_id {row.participant_group_id!r} != "
                f"frozen split group {expected_group!r} for record {row.record_id}"
            )
        if row.partition != expected_partition:
            errors.append(
                f"{row.example_id}: partition {row.partition!r} != frozen split partition "
                f"{expected_partition!r} for record {row.record_id}"
            )

    patient_check = audit_group_disjointness(
        [
            {"participant_group_id": row.participant_group_id, "partition": row.partition}
            for row in rows
        ],
        "participant_group_id", "partition",
    )
    if patient_check["status"] != "PASS":
        errors.append(f"patient crossing across partitions: {patient_check['pairwise_overlaps']}")

    record_check = audit_group_disjointness(
        [{"record_id": row.record_id, "partition": row.partition} for row in rows],
        "record_id", "partition",
    )
    if record_check["status"] != "PASS":
        errors.append(f"record crossing across partitions: {record_check['pairwise_overlaps']}")

    hash_check = audit_group_disjointness(
        [{"source_hash": row.source_hash, "partition": row.partition} for row in rows],
        "source_hash", "partition",
    )
    if hash_check["status"] != "PASS":
        errors.append(f"duplicate source_hash across partitions: {hash_check['pairwise_overlaps']}")

    by_record: dict[str, list[WindowAuditRow]] = {}
    for row in rows:
        by_record.setdefault(row.record_id, []).append(row)
    for record_id, record_rows in by_record.items():
        if len({row.partition for row in record_rows}) <= 1:
            continue
        for a, b in itertools.combinations(record_rows, 2):
            if a.partition != b.partition and _intervals_overlap_or_adjacent(a, b):
                errors.append(
                    f"cross-partition overlapping/neighboring interval: {a.example_id} "
                    f"({a.partition}) vs {b.example_id} ({b.partition}) on record {record_id}"
                )

    return {"status": "PASS" if not errors else "FAIL", "errors": errors}


# ---------------------------------------------------------------------------------------
# Frozen-split verifier -- later tasks (T011+) call this before consuming MITDB_SPLIT_V1
# ---------------------------------------------------------------------------------------

_LOCK_ARTIFACT_FIELDS: Mapping[str, str] = MappingProxyType(
    {
        "split_sha256": "manifests/splits/MITDB_SPLIT_V1.csv",
        "split_yaml_sha256": "manifests/splits/MITDB_SPLIT_V1.yaml",
        "groups_sha256": "manifests/splits/mitdb_groups.csv",
        "strata_sha256": "manifests/splits/mitdb_patient_strata.csv",
        "partition_roles_sha256": "manifests/splits/partition_roles_v1.yaml",
        "label_map_sha256": "manifests/labels/AAMI_SVF_MAP_V1.yaml",
        "eligible_manifest_sha256": "manifests/datasets/mitdb_mlii_records.csv",
    }
)


def verify_frozen_split(
    root: Path, lock_path: Path | None = None
) -> dict[str, Any]:
    """Fail-closed: raises a typed LeakageAuditError on the first detected problem. Returns a
    small confirmation dict only on full success. Never repairs or regenerates anything.

    Layered defense: byte-hash comparison against the lock catches any tampering first; the
    semantic checks below additionally catch a forged/stale lock whose recorded hash was
    dishonestly updated to match tampered content.
    """
    from nhm.coverage import read_csv

    lock_path = lock_path or (root / "manifests/splits/MITDB_SPLIT_V1.lock.json")
    if not lock_path.exists():
        raise SplitHashMismatch(f"no freeze lock found at {lock_path}; split is not frozen")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if lock.get("status") != "FROZEN":
        raise SplitHashMismatch(f"lock status is {lock.get('status')!r}, expected FROZEN")

    for field, relative_path in _LOCK_ARTIFACT_FIELDS.items():
        expected = lock.get(field)
        actual = hash_file(root / relative_path)
        if actual != expected:
            raise SplitHashMismatch(
                f"{relative_path}: lock expected {expected}, recomputed {actual} (field {field})"
            )

    split_rows = read_csv(root / "manifests/splits/MITDB_SPLIT_V1.csv")
    strata_rows = read_csv(root / "manifests/splits/mitdb_patient_strata.csv")
    eligible_rows = read_csv(root / "manifests/datasets/mitdb_mlii_records.csv")
    eligible_ids = {row["record_id"] for row in eligible_rows}

    eligibility = audit_eligible_record_closure(split_rows, eligible_ids)
    if eligibility["status"] != "PASS":
        raise SplitEligibilityMismatch(str(eligibility["errors"]))

    completeness = audit_group_assignment_completeness(
        split_rows, {row["participant_group_id"] for row in strata_rows}
    )
    if completeness["status"] != "PASS":
        raise SplitEligibilityMismatch(str(completeness["errors"]))

    disjointness = audit_group_disjointness(split_rows, "participant_group_id", "partition")
    if disjointness["status"] != "PASS":
        raise SplitPatientOverlap(str(disjointness["pairwise_overlaps"]))

    vocabulary = audit_partition_vocabulary(split_rows)
    if vocabulary["status"] != "PASS":
        raise SplitGroupingMismatch(
            f"invalid partition value(s): {vocabulary['invalid_partitions']}"
        )

    invariant = audit_group_invariant(split_rows, ["201", "202"])
    if invariant["status"] != "PASS":
        raise SplitGroupingMismatch(f"201/202 invariant violated: {invariant}")

    strata_by_group = {row["participant_group_id"]: row["has_svf_event"] for row in strata_rows}
    for row in split_rows:
        expected_strata = strata_by_group.get(row["participant_group_id"])
        if expected_strata is not None and row["has_svf_event"] != expected_strata:
            raise SplitGroupingMismatch(
                f"record {row['record_id']}: split has_svf_event={row['has_svf_event']!r} != "
                f"mitdb_patient_strata.csv value {expected_strata!r} for group "
                f"{row['participant_group_id']!r}"
            )

    from datasets.labels import MAP_ID
    from datasets.mitdb import LEAD_POLICY_ID

    expected_row_fields = {
        "split_id": lock["split_id"],
        "split_seed": str(lock["split_seed"]),
        "lead_policy_id": lock["lead_policy_id"],
        "label_map_id": lock["label_map_id"],
    }
    for row in split_rows:
        for field, expected_value in expected_row_fields.items():
            if row[field] != expected_value:
                raise SplitUpstreamMismatch(
                    f"record {row['record_id']}: {field}={row[field]!r} != "
                    f"lock value {expected_value!r}"
                )

    if lock.get("label_map_id") != MAP_ID:
        raise SplitUpstreamMismatch(
            f"lock label_map_id {lock.get('label_map_id')!r} != current {MAP_ID!r}"
        )
    if lock.get("lead_policy_id") != LEAD_POLICY_ID:
        raise SplitUpstreamMismatch(
            f"lock lead_policy_id {lock.get('lead_policy_id')!r} != current {LEAD_POLICY_ID!r}"
        )

    return {"status": "PASS", "lock_path": str(lock_path), "split_id": lock["split_id"]}
