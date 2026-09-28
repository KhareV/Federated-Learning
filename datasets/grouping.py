"""Patient grouping and deterministic stratified partition allocation for MITDB_SPLIT_V1.

Pure functions only -- no dataset/file I/O, no preprocessing, no model or evaluation
dependency. Callers (scripts/build_mitdb_split_t009.py) own reading raw records/annotations
and writing artifacts. The split unit is the participant group, never a window, beat, record
fragment, or random row; overlapping windows later inherit their record's group membership,
they never determine it.

Grouping rule: the one authoritative, pre-declared MIT-BIH multi-record relationship is
records 201 and 202 (v2.2 Section 11). No other relationship is inferred from signal,
annotation, morphology, or any other content -- every other eligible record is its own
participant group.
"""

from __future__ import annotations

import hashlib
import itertools
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from math import floor
from typing import Any

from datasets.labels import map_annotation_symbol

GROUPING_RULE_ID = "MITDB_GROUPING_V1"

# The single pre-declared multi-record patient relationship. participant_group_id values are
# project statistical grouping identifiers, not claims about real-world patient identity.
MULTI_RECORD_GROUPS: Mapping[str, tuple[str, ...]] = {"MITDB_P201_202": ("201", "202")}

PARTITIONS: tuple[str, ...] = ("TRAIN", "VALIDATION", "CALIBRATION", "INTERNAL_TEST")
TARGET_PROPORTIONS: Mapping[str, float] = {
    "TRAIN": 0.60,
    "VALIDATION": 0.15,
    "CALIBRATION": 0.10,
    "INTERNAL_TEST": 0.15,
}


def participant_group_id_for_record(record_id: str) -> str:
    """MITDB_P{record_id} for every record, except 201/202 which share MITDB_P201_202."""
    for group_id, members in MULTI_RECORD_GROUPS.items():
        if record_id in members:
            return group_id
    return f"MITDB_P{record_id}"


@dataclass(frozen=True)
class PatientGroupRow:
    record_id: str
    participant_group_id: str
    core_channel_eligible: bool
    eligibility_reason: str
    records_in_group: int
    source_dataset: str = "MITDB"
    grouping_rule: str = GROUPING_RULE_ID


def build_mitdb_patient_groups(
    all_record_ids: Sequence[str],
    eligible_record_ids: Sequence[str],
    exclusion_reasons: Mapping[str, str],
) -> list[PatientGroupRow]:
    """One row per *source* record (retains excluded records so exclusions stay visible).

    201 and 202 are grouped before any eligibility or partition decision is made; grouping
    never depends on eligibility.
    """
    eligible = set(eligible_record_ids)
    members_by_group: dict[str, list[str]] = {}
    for record_id in all_record_ids:
        members_by_group.setdefault(participant_group_id_for_record(record_id), []).append(
            record_id
        )

    rows = []
    for record_id in all_record_ids:
        group_id = participant_group_id_for_record(record_id)
        is_eligible = record_id in eligible
        reason = (
            "ELIGIBLE_EXACT_MLII" if is_eligible else exclusion_reasons.get(record_id, "UNKNOWN")
        )
        rows.append(
            PatientGroupRow(
                record_id=record_id,
                participant_group_id=group_id,
                core_channel_eligible=is_eligible,
                eligibility_reason=reason,
                records_in_group=len(members_by_group[group_id]),
            )
        )
    return rows


@dataclass(frozen=True)
class PatientEventPresence:
    participant_group_id: str
    has_svf_event: bool
    mapped_n: int
    mapped_s: int
    mapped_v: int
    mapped_f: int
    mapped_q: int
    unmappable: int
    nonbeat: int


def compute_patient_event_presence(
    participant_group_id: str,
    record_annotations: Mapping[str, Iterable[tuple[str, int, int]]],
) -> PatientEventPresence:
    """`record_annotations` maps record_id -> an iterable of raw, unfiltered
    (symbol, sample, sig_len) tuples for that record. Only in-signal annotations
    (0 <= sample < sig_len) count toward `has_svf_event` or the descriptive class counts --
    the frozen v2.2 in-signal invariant, enforced structurally even though MIT-BIH currently
    has no known pre/post-signal anomaly (unlike INCART, see T007/T008).

    `has_svf_event` is the logical OR across every record in the group (201/202 included):
    the group is evaluated as one unit, never per-record.
    """
    counts = {"N": 0, "S": 0, "V": 0, "F": 0, "Q": 0, "UNMAPPABLE": 0, "NOT_A_BEAT": 0}
    has_svf = False
    for raw_annotations in record_annotations.values():
        for symbol, sample, sig_len in raw_annotations:
            if not (0 <= sample < sig_len):
                continue
            mapped = map_annotation_symbol(symbol)
            counts[mapped.mapped_class] += 1
            if mapped.mapped_class in ("S", "V", "F"):
                has_svf = True
    return PatientEventPresence(
        participant_group_id=participant_group_id,
        has_svf_event=has_svf,
        mapped_n=counts["N"],
        mapped_s=counts["S"],
        mapped_v=counts["V"],
        mapped_f=counts["F"],
        mapped_q=counts["Q"],
        unmappable=counts["UNMAPPABLE"],
        nonbeat=counts["NOT_A_BEAT"],
    )


@dataclass(frozen=True)
class ApportionmentResult:
    quotas: Mapping[str, int]
    raw: Mapping[str, float]
    method: str = "LARGEST_REMAINDER_HAMILTON"


def apportion_partition_capacities(
    total: int,
    proportions: Mapping[str, float] = TARGET_PROPORTIONS,
    order: Sequence[str] = PARTITIONS,
) -> ApportionmentResult:
    """Hamilton / largest-remainder apportionment of `total` patient groups across
    partitions. Ties in the fractional remainder break in the fixed `order` (TRAIN,
    VALIDATION, CALIBRATION, INTERNAL_TEST)."""
    raw = {key: total * proportions[key] for key in order}
    quotas = {key: floor(raw[key]) for key in order}
    remaining = total - sum(quotas.values())
    by_remainder = sorted(
        order, key=lambda key: (-(raw[key] - quotas[key]), order.index(key))
    )
    for key in by_remainder[:remaining]:
        quotas[key] += 1
    return ApportionmentResult(quotas=quotas, raw=raw)


def apportion_stratum_capacities(
    partition_quotas: Mapping[str, int],
    total_positive: int,
    order: Sequence[str] = PARTITIONS,
) -> dict[str, int]:
    """Exact integer allocation of `total_positive` patient groups across partitions,
    minimizing squared deviation from the proportional-to-capacity expectation, subject to
    0 <= p_i <= partition_quotas[i] and sum(p_i) == total_positive. Enumerates all feasible
    vectors (the partition count is fixed and small) and breaks ties deterministically by
    preferring a lexicographically larger vector in the fixed `order`. No model or result
    information enters this objective."""
    total = sum(partition_quotas.values())
    if not 0 <= total_positive <= total:
        raise ValueError(f"total_positive {total_positive} out of range [0, {total}]")
    expected = {
        key: partition_quotas[key] * (total_positive / total) if total else 0.0 for key in order
    }

    best: tuple[Any, tuple[int, ...]] | None = None
    ranges = [range(0, partition_quotas[key] + 1) for key in order]
    for combo in itertools.product(*ranges):
        if sum(combo) != total_positive:
            continue
        objective = sum(
            (count - expected[key]) ** 2 for count, key in zip(combo, order, strict=True)
        )
        tie_break = tuple(-count for count in combo)
        candidate_key = (round(objective, 9), tie_break)
        if best is None or candidate_key < best[0]:
            best = (candidate_key, combo)
    if best is None:
        raise ValueError(
            f"no feasible allocation of {total_positive} positive patients across capacities "
            f"{dict(partition_quotas)}"
        )
    return dict(zip(order, best[1], strict=True))


def stable_group_order(
    split_id: str, split_seed: int, stratum: str, participant_group_ids: Sequence[str]
) -> list[str]:
    """Deterministic, machine/process/OS-independent ordering via SHA-256 digest of
    (split_id, split_seed, stratum, participant_group_id)."""

    def digest(group_id: str) -> str:
        payload = f"{split_id}{split_seed}{stratum}{group_id}".encode()
        return hashlib.sha256(payload).hexdigest()

    return sorted(participant_group_ids, key=digest)


@dataclass(frozen=True)
class PartitionAssignment:
    participant_group_id: str
    partition: str
    has_svf_event: bool


def assign_partitions(
    split_id: str,
    split_seed: int,
    positive_group_ids: Sequence[str],
    negative_group_ids: Sequence[str],
    positive_quotas: Mapping[str, int],
    negative_quotas: Mapping[str, int],
    order: Sequence[str] = PARTITIONS,
) -> list[PartitionAssignment]:
    """Deterministically order each stratum (via `stable_group_order`) and slice it into
    consecutive quota-sized blocks in the fixed partition `order`. No manual movement."""
    assignments: list[PartitionAssignment] = []
    for stratum_label, group_ids, quotas, has_svf in (
        ("POSITIVE", positive_group_ids, positive_quotas, True),
        ("NEGATIVE", negative_group_ids, negative_quotas, False),
    ):
        ordered = stable_group_order(split_id, split_seed, stratum_label, group_ids)
        cursor = 0
        for partition in order:
            quota = quotas[partition]
            for group_id in ordered[cursor : cursor + quota]:
                assignments.append(PartitionAssignment(group_id, partition, has_svf))
            cursor += quota
        if cursor != len(ordered):
            raise ValueError(
                f"{stratum_label} quota total {cursor} != group count {len(ordered)}"
            )
    return assignments


def validate_split(
    assignments: Sequence[PartitionAssignment], eligible_group_ids: Sequence[str]
) -> dict[str, Any]:
    """Structural leakage/completeness checks internal to T009 (T010 performs the
    independent audit). Reports zero overlap, zero unassigned, zero duplicates for a valid
    split; never silently repairs a defect."""
    errors: list[str] = []
    assigned_ids = [row.participant_group_id for row in assignments]
    assigned_set = set(assigned_ids)
    eligible_set = set(eligible_group_ids)

    duplicate_count = len(assigned_ids) - len(assigned_set)
    if duplicate_count:
        errors.append(f"{duplicate_count} duplicate group assignment(s) detected")

    missing = eligible_set - assigned_set
    extra = assigned_set - eligible_set
    if missing:
        errors.append(f"unassigned eligible groups: {sorted(missing)}")
    if extra:
        errors.append(f"assigned groups outside eligible set: {sorted(extra)}")

    by_partition: dict[str, set[str]] = {}
    for row in assignments:
        by_partition.setdefault(row.partition, set()).add(row.participant_group_id)
    partitions = sorted(by_partition)
    pairwise_overlaps: list[tuple[str, str, list[str]]] = []
    for i in range(len(partitions)):
        for j in range(i + 1, len(partitions)):
            overlap = by_partition[partitions[i]] & by_partition[partitions[j]]
            if overlap:
                pairwise_overlaps.append((partitions[i], partitions[j], sorted(overlap)))
    if pairwise_overlaps:
        errors.append(f"pairwise patient overlap detected: {pairwise_overlaps}")

    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "unassigned_count": len(missing),
        "duplicate_assignment_count": duplicate_count,
        "pairwise_overlap_count": len(pairwise_overlaps),
    }
