#!/usr/bin/env python3
"""T009: build the deterministic MITDB_SPLIT_V1 patient partition.

Offline, deterministic, real-data only. Reads the already-acquired, hash-verified local MIT-
BIH raw annotations (T006 scope) and the frozen AAMI_SVF_MAP_V1 mapper (T008/G4/F04). Builds
patient groups, computes patient-level S/V/F presence, and deterministically allocates
patient groups to TRAIN/VALIDATION/CALIBRATION/INTERNAL_TEST via one predeclared algorithm
and one fixed seed -- no seed search, no manual movement, no model/result input.

No window-building, no preprocessing, no model training, no external evaluation. G5/F05 are
NOT closed here -- that is T010's independent leakage audit and freeze.
"""

from __future__ import annotations

import csv
import json
import sys
from io import StringIO
from pathlib import Path
from typing import Any

import yaml

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from datasets import mitdb  # noqa: E402
from datasets.grouping import (  # noqa: E402
    GROUPING_RULE_ID,
    PARTITIONS,
    TARGET_PROPORTIONS,
    apportion_partition_capacities,
    apportion_stratum_capacities,
    assign_partitions,
    build_mitdb_patient_groups,
    compute_patient_event_presence,
    validate_split,
)
from datasets.labels import MAP_ID as LABEL_MAP_ID  # noqa: E402
from datasets.mitdb import LEAD_POLICY_ID  # noqa: E402

REPORT_DIR = ROOT / "reports/t009"
SPLIT_DIR = ROOT / "manifests/splits"

SPLIT_ID = "MITDB_SPLIT_V1"
SPLIT_SEED = 20260927
ROUNDING_ALGORITHM = "LARGEST_REMAINDER_HAMILTON"
ALLOCATION_ALGORITHM = "EXACT_INTEGER_MIN_SQUARED_DEVIATION"
STABLE_ORDER_METHOD = "SHA256(split_id, split_seed, stratum, participant_group_id)"


def _read_eligible_records() -> dict[str, dict[str, str]]:
    with (ROOT / "manifests/datasets/mitdb_mlii_records.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        return {row["record_id"]: row for row in csv.DictReader(handle)}


def _read_exclusions() -> dict[str, str]:
    with (ROOT / "manifests/datasets/mitdb_mlii_exclusions.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        return {row["record_id"]: row["reason"] for row in csv.DictReader(handle)}


def _record_annotations(record_id: str) -> list[tuple[str, int, int]]:
    header = mitdb.read_header(record_id)
    annotation = mitdb.load_annotations(record_id)
    return [
        (symbol, int(sample), header.sig_len)
        for symbol, sample in zip(annotation.symbol, annotation.sample, strict=True)
    ]


def _dict_rows_to_csv_text(rows: list[dict[str, Any]], fieldnames: list[str]) -> str:
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def build_split() -> dict[str, Any]:
    """Pure with respect to already-written upstream artifacts: reads the same frozen T006
    eligibility manifest and the same frozen AAMI_SVF_MAP_V1 mapper every call, so two calls
    in the same repository state produce byte-identical text artifacts (T009 Section 32)."""
    eligible_by_id = _read_eligible_records()
    eligible_record_ids = sorted(eligible_by_id, key=int)
    exclusion_reasons = _read_exclusions()
    all_record_ids = mitdb.list_records()

    if set(all_record_ids) != set(eligible_record_ids) | set(exclusion_reasons):
        raise RuntimeError(
            "PATIENT_GROUPING_CONFLICT: source record set does not equal "
            "eligible | excluded from the frozen T006 manifests"
        )

    group_rows = build_mitdb_patient_groups(all_record_ids, eligible_record_ids, exclusion_reasons)
    groups_text = _dict_rows_to_csv_text(
        [
            {
                "record_id": row.record_id,
                "participant_group_id": row.participant_group_id,
                "core_channel_eligible": str(row.core_channel_eligible).upper(),
                "eligibility_reason": row.eligibility_reason,
                "records_in_group": row.records_in_group,
                "source_dataset": row.source_dataset,
                "grouping_rule": row.grouping_rule,
            }
            for row in sorted(group_rows, key=lambda row: int(row.record_id))
        ],
        [
            "record_id", "participant_group_id", "core_channel_eligible", "eligibility_reason",
            "records_in_group", "source_dataset", "grouping_rule",
        ],
    )

    eligible_group_records: dict[str, list[str]] = {}
    for row in group_rows:
        if row.core_channel_eligible:
            eligible_group_records.setdefault(row.participant_group_id, []).append(row.record_id)
    eligible_group_ids = sorted(eligible_group_records)

    if len(eligible_record_ids) != 46:
        raise RuntimeError(
            f"PATIENT_GROUPING_CONFLICT: expected 46 eligible records, got "
            f"{len(eligible_record_ids)}"
        )
    if len(eligible_group_ids) != 45:
        raise RuntimeError(
            f"PATIENT_GROUPING_CONFLICT: expected 45 eligible patient groups, got "
            f"{len(eligible_group_ids)}"
        )

    presence_by_group = {}
    for group_id, record_ids in eligible_group_records.items():
        record_annotations = {record_id: _record_annotations(record_id) for record_id in record_ids}
        presence_by_group[group_id] = compute_patient_event_presence(group_id, record_annotations)

    strata_text = _dict_rows_to_csv_text(
        [
            {
                "participant_group_id": group_id,
                "record_ids": ";".join(eligible_group_records[group_id]),
                "record_count": len(eligible_group_records[group_id]),
                "has_svf_event": str(presence_by_group[group_id].has_svf_event).upper(),
                "mapped_N_count": presence_by_group[group_id].mapped_n,
                "mapped_S_count": presence_by_group[group_id].mapped_s,
                "mapped_V_count": presence_by_group[group_id].mapped_v,
                "mapped_F_count": presence_by_group[group_id].mapped_f,
                "mapped_Q_count": presence_by_group[group_id].mapped_q,
                "unmappable_count": presence_by_group[group_id].unmappable,
                "nonbeat_count": presence_by_group[group_id].nonbeat,
            }
            for group_id in eligible_group_ids
        ],
        [
            "participant_group_id", "record_ids", "record_count", "has_svf_event",
            "mapped_N_count", "mapped_S_count", "mapped_V_count", "mapped_F_count",
            "mapped_Q_count", "unmappable_count", "nonbeat_count",
        ],
    )

    positive_group_ids = sorted(
        group_id for group_id in eligible_group_ids if presence_by_group[group_id].has_svf_event
    )
    negative_group_ids = sorted(
        group_id
        for group_id in eligible_group_ids
        if not presence_by_group[group_id].has_svf_event
    )

    partition_capacities = apportion_partition_capacities(len(eligible_group_ids))
    positive_quotas = apportion_stratum_capacities(
        partition_capacities.quotas, len(positive_group_ids)
    )
    negative_quotas = {
        partition: partition_capacities.quotas[partition] - positive_quotas[partition]
        for partition in PARTITIONS
    }

    assignments = assign_partitions(
        SPLIT_ID,
        SPLIT_SEED,
        positive_group_ids,
        negative_group_ids,
        positive_quotas,
        negative_quotas,
    )
    validation = validate_split(assignments, eligible_group_ids)
    if validation["status"] != "PASS":
        raise RuntimeError(f"SPLIT_CONSTRUCTION_CONFLICT: {validation['errors']}")

    partition_by_group = {row.participant_group_id: row.partition for row in assignments}
    group_201_202 = "MITDB_P201_202"
    if group_201_202 not in eligible_group_ids:
        raise RuntimeError("PATIENT_GROUPING_CONFLICT: MITDB_P201_202 missing from eligible groups")

    split_rows = []
    for record_id in eligible_record_ids:
        group_id = participant_group_id_lookup(group_rows, record_id)
        split_rows.append(
            {
                "record_id": record_id,
                "participant_group_id": group_id,
                "partition": partition_by_group[group_id],
                "has_svf_event": str(presence_by_group[group_id].has_svf_event).upper(),
                "group_record_count": len(eligible_group_records[group_id]),
                "split_id": SPLIT_ID,
                "split_seed": SPLIT_SEED,
                "lead_policy_id": LEAD_POLICY_ID,
                "label_map_id": LABEL_MAP_ID,
            }
        )
    split_rows.sort(key=lambda row: int(row["record_id"]))
    split_text = _dict_rows_to_csv_text(
        split_rows,
        [
            "record_id", "participant_group_id", "partition", "has_svf_event",
            "group_record_count", "split_id", "split_seed", "lead_policy_id", "label_map_id",
        ],
    )

    split_yaml = {
        "split_id": SPLIT_ID,
        "spec_version": "2.2",
        "source_dataset": "MITDB",
        "source_dataset_version": "1.0.0",
        "lead_policy_id": LEAD_POLICY_ID,
        "label_map_id": LABEL_MAP_ID,
        "split_seed": SPLIT_SEED,
        "grouping_rule": GROUPING_RULE_ID,
        "stratification_variable": "has_svf_event",
        "target_proportions": dict(TARGET_PROPORTIONS),
        "allocation_algorithm": ALLOCATION_ALGORITHM,
        "rounding_algorithm": ROUNDING_ALGORITHM,
        "stable_order_method": STABLE_ORDER_METHOD,
        "split_status": "DRAFT_VALIDATED",
        "freeze_status": "NOT_FROZEN",
        "owning_task": "T009",
        "freeze_owning_task": "T010",
        "notes": (
            "Draft, internally validated by T009. Independent leakage audit and freeze (G5/"
            "F05) are owned by T010, not this task."
        ),
    }
    split_yaml_text = yaml.safe_dump(split_yaml, sort_keys=False)

    return {
        "eligible_record_ids": eligible_record_ids,
        "eligible_group_ids": eligible_group_ids,
        "excluded_record_ids": sorted(exclusion_reasons, key=int),
        "group_rows": group_rows,
        "groups_text": groups_text,
        "strata_text": strata_text,
        "split_rows": split_rows,
        "split_text": split_text,
        "split_yaml_text": split_yaml_text,
        "presence_by_group": presence_by_group,
        "positive_group_ids": positive_group_ids,
        "negative_group_ids": negative_group_ids,
        "partition_capacities": partition_capacities,
        "positive_quotas": positive_quotas,
        "negative_quotas": negative_quotas,
        "assignments": assignments,
        "validation": validation,
        "partition_by_group": partition_by_group,
        "group_201_202_partition": partition_by_group[group_201_202],
    }


def participant_group_id_lookup(group_rows: list[Any], record_id: str) -> str:
    for row in group_rows:
        if row.record_id == record_id:
            return row.participant_group_id
    raise KeyError(record_id)


def write_partition_roles() -> Path:
    roles = {
        "TRAIN": {
            "allowed": [
                "fit model weights",
                "fit feature/scaler parameters",
                "derive augmentation settings",
                "derive majority-class baseline",
            ],
            "forbidden": [],
        },
        "VALIDATION": {
            "allowed": ["architecture/hyperparameter selection", "early stopping"],
            "forbidden": ["final test reporting", "calibration fitting"],
        },
        "CALIBRATION": {
            "allowed": ["temperature scaling", "operating threshold selection"],
            "forbidden": ["architecture changes", "model training"],
        },
        "INTERNAL_TEST": {
            "allowed": ["one final locked internal evaluation after model/calibration freeze"],
            "forbidden": ["all tuning", "all fitting", "threshold choice", "architecture choice"],
        },
    }
    output_path = SPLIT_DIR / "partition_roles_v1.yaml"
    output_path.write_text(
        yaml.safe_dump(
            {"split_id": SPLIT_ID, "incart_note": "INCART is entirely outside this split.",
             "partitions": roles},
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return output_path


def write_class_coverage(result: dict[str, Any]) -> Path:
    presence = result["presence_by_group"]
    partition_by_group = result["partition_by_group"]
    rows = []
    for partition in PARTITIONS:
        group_ids = [g for g, p in partition_by_group.items() if p == partition]
        has_svf = sum(1 for g in group_ids if presence[g].has_svf_event)
        no_svf = len(group_ids) - has_svf
        rows.append(
            {
                "partition": partition,
                "patient_count": len(group_ids),
                "has_svf_patient_count": has_svf,
                "no_svf_patient_count": no_svf,
                "has_svf_fraction": round(has_svf / len(group_ids), 6) if group_ids else 0.0,
                "mapped_N": sum(presence[g].mapped_n for g in group_ids),
                "mapped_S": sum(presence[g].mapped_s for g in group_ids),
                "mapped_V": sum(presence[g].mapped_v for g in group_ids),
                "mapped_F": sum(presence[g].mapped_f for g in group_ids),
                "mapped_Q": sum(presence[g].mapped_q for g in group_ids),
                "unmappable": sum(presence[g].unmappable for g in group_ids),
            }
        )
    output_path = REPORT_DIR / "class_coverage.csv"
    fieldnames = list(rows[0].keys())
    output_path.write_text(_dict_rows_to_csv_text(rows, fieldnames), encoding="utf-8")
    return output_path


def _upstream_hashes() -> dict[str, str]:
    """Hashes of the split's decisive upstream inputs, so T010 can prove the split was built
    from the same frozen upstream state (T009 Section 31/47)."""
    paths = [
        ROOT / "manifests/datasets/mitdb_mlii_records.csv",
        ROOT / "manifests/datasets/mitdb_mlii_exclusions.csv",
        ROOT / "manifests/datasets/mitdb_v1.yaml",
        ROOT / "manifests/labels/AAMI_SVF_MAP_V1.yaml",
        ROOT / "datasets/labels.py",
    ]
    return {str(path.relative_to(ROOT)): hash_file(path) for path in paths}


def write_split_generation_report(result: dict[str, Any], regeneration_match: bool) -> Path:
    record_counts = {
        partition: sum(1 for row in result["split_rows"] if row["partition"] == partition)
        for partition in PARTITIONS
    }
    patient_counts = {
        partition: sum(1 for p in result["partition_by_group"].values() if p == partition)
        for partition in PARTITIONS
    }
    report = {
        "task_id": "T009",
        "split_id": SPLIT_ID,
        "split_seed": SPLIT_SEED,
        "eligible_record_count": len(result["eligible_record_ids"]),
        "eligible_patient_group_count": len(result["eligible_group_ids"]),
        "excluded_records": result["excluded_record_ids"],
        "partition_target_proportions": dict(TARGET_PROPORTIONS),
        "partition_patient_quotas": dict(result["partition_capacities"].quotas),
        "partition_record_counts": record_counts,
        "partition_patient_counts": patient_counts,
        "total_svf_positive_patient_groups": len(result["positive_group_ids"]),
        "total_no_svf_patient_groups": len(result["negative_group_ids"]),
        "positive_patient_quota_by_partition": dict(result["positive_quotas"]),
        "negative_patient_quota_by_partition": dict(result["negative_quotas"]),
        "records_201_202_same_group": True,
        "records_201_202_same_partition": True,
        "records_201_202_group_id": "MITDB_P201_202",
        "records_201_202_partition": result["group_201_202_partition"],
        "algorithm": ALLOCATION_ALGORITHM,
        "rounding_method": ROUNDING_ALGORITHM,
        "stable_order_method": STABLE_ORDER_METHOD,
        "candidate_seeds_tried": 1,
        "manual_adjustments": "none",
        "unassigned_patient_count": result["validation"]["unassigned_count"],
        "duplicate_assignment_count": result["validation"]["duplicate_assignment_count"],
        "pairwise_patient_overlap_count": result["validation"]["pairwise_overlap_count"],
        "split_status": "DRAFT_VALIDATED",
        "freeze_status": "NOT_FROZEN",
        "upstream_hashes": _upstream_hashes(),
        "determinism_check": regeneration_match,
        "overall_status": (
            "PASS" if result["validation"]["status"] == "PASS" and regeneration_match else "FAIL"
        ),
    }
    output_path = REPORT_DIR / "split_generation.json"
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_path


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    SPLIT_DIR.mkdir(parents=True, exist_ok=True)

    first = build_split()
    second = build_split()
    regeneration_match = (
        first["groups_text"] == second["groups_text"]
        and first["strata_text"] == second["strata_text"]
        and first["split_text"] == second["split_text"]
        and first["split_yaml_text"] == second["split_yaml_text"]
    )
    if not regeneration_match:
        raise RuntimeError(
            "SPLIT_CONSTRUCTION_CONFLICT: deterministic regeneration produced different output"
        )

    (SPLIT_DIR / "mitdb_groups.csv").write_text(first["groups_text"], encoding="utf-8")
    (SPLIT_DIR / "mitdb_patient_strata.csv").write_text(first["strata_text"], encoding="utf-8")
    (SPLIT_DIR / "MITDB_SPLIT_V1.csv").write_text(first["split_text"], encoding="utf-8")
    (SPLIT_DIR / "MITDB_SPLIT_V1.yaml").write_text(first["split_yaml_text"], encoding="utf-8")
    write_partition_roles()
    write_class_coverage(first)
    write_split_generation_report(first, regeneration_match)

    print(
        f"T009 split: eligible_records={len(first['eligible_record_ids'])} "
        f"eligible_groups={len(first['eligible_group_ids'])} "
        f"positive={len(first['positive_group_ids'])} negative={len(first['negative_group_ids'])} "
        f"201/202 partition={first['group_201_202_partition']} "
        f"determinism_check={regeneration_match}"
    )


if __name__ == "__main__":
    main()
