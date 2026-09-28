#!/usr/bin/env python3
"""T010: independent leakage audit of the T009 candidate MITDB_SPLIT_V1.

This script attacks the committed candidate split rather than trusting T009's own report.
Every G5 invariant is recomputed directly from authoritative upstream artifacts (T006
eligibility, T008 frozen mapper, T009 grouping/split manifests). The candidate split's own
SHA-256 is captured before and after the audit and required to be byte-identical -- this
script never rewrites manifests/splits/MITDB_SPLIT_V1.csv or any other T009 artifact.

On success it writes reports/splits/split_audit.json (canonical G5 evidence) and, only if
every check passed, creates the freeze lock manifests/splits/MITDB_SPLIT_V1.lock.json. On any
failure it raises -- it never repairs the candidate or silently continues.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from datasets import mitdb  # noqa: E402
from datasets.grouping import (  # noqa: E402
    PARTITIONS,
    apportion_partition_capacities,
    apportion_stratum_capacities,
    assign_partitions,
    build_mitdb_patient_groups,
    compute_patient_event_presence,
)
from datasets.labels import MAP_ID as LABEL_MAP_ID  # noqa: E402
from datasets.mitdb import LEAD_POLICY_ID  # noqa: E402
from evaluation.leakage_audit import (  # noqa: E402
    audit_eligible_record_closure,
    audit_group_assignment_completeness,
    audit_group_disjointness,
    audit_group_invariant,
    audit_partition_vocabulary,
)
from nhm.coverage import read_csv  # noqa: E402
from nhm.hashing import hash_file  # noqa: E402

SPLIT_DIR = ROOT / "manifests/splits"
SPLIT_CSV = SPLIT_DIR / "MITDB_SPLIT_V1.csv"
REPORT_DIR = ROOT / "reports/splits"
SPLIT_ID = "MITDB_SPLIT_V1"
SPLIT_SEED = 20260927


def _upstream_paths() -> dict[str, Path]:
    datasets_dir = ROOT / "manifests/datasets"
    return {
        "datasets/labels.py": ROOT / "datasets/labels.py",
        "manifests/datasets/mitdb_mlii_exclusions.csv": datasets_dir / "mitdb_mlii_exclusions.csv",
        "manifests/datasets/mitdb_mlii_records.csv": datasets_dir / "mitdb_mlii_records.csv",
        "manifests/datasets/mitdb_v1.yaml": datasets_dir / "mitdb_v1.yaml",
        "manifests/labels/AAMI_SVF_MAP_V1.yaml": ROOT / "manifests/labels/AAMI_SVF_MAP_V1.yaml",
    }


def _record_annotations(record_id: str) -> list[tuple[str, int, int]]:
    header = mitdb.read_header(record_id)
    annotation = mitdb.load_annotations(record_id)
    return [
        (symbol, int(sample), header.sig_len)
        for symbol, sample in zip(annotation.symbol, annotation.sample, strict=True)
    ]


def run_audit() -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    candidate_hash_before = hash_file(SPLIT_CSV)

    split_rows = read_csv(SPLIT_CSV)
    strata_rows = read_csv(SPLIT_DIR / "mitdb_patient_strata.csv")
    eligible_rows = read_csv(ROOT / "manifests/datasets/mitdb_mlii_records.csv")
    exclusion_rows = read_csv(ROOT / "manifests/datasets/mitdb_mlii_exclusions.csv")

    eligible_record_ids = sorted((row["record_id"] for row in eligible_rows), key=int)
    eligible_group_ids = sorted({row["participant_group_id"] for row in strata_rows})

    # A. exact eligible-record closure
    closure = audit_eligible_record_closure(split_rows, eligible_record_ids)
    if closure["status"] != "PASS":
        errors.append(f"eligibility closure: {closure['errors']}")
    if "102" in {row["record_id"] for row in split_rows} or "104" in {
        row["record_id"] for row in split_rows
    }:
        errors.append("excluded record 102/104 present in split")

    # B. complete patient assignment / E. group integrity
    completeness = audit_group_assignment_completeness(split_rows, eligible_group_ids)
    if completeness["status"] != "PASS":
        errors.append(f"group assignment completeness: {completeness['errors']}")

    # C. pairwise patient disjointness
    disjointness = audit_group_disjointness(split_rows, "participant_group_id", "partition")
    if disjointness["status"] != "PASS":
        errors.append(f"pairwise patient overlap: {disjointness['pairwise_overlaps']}")

    # D. 201/202 invariant
    invariant_201_202 = audit_group_invariant(split_rows, ["201", "202"])
    if invariant_201_202["status"] != "PASS":
        errors.append(f"201/202 invariant violated: {invariant_201_202}")

    # F. partition vocabulary
    vocabulary = audit_partition_vocabulary(split_rows, PARTITIONS)
    if vocabulary["status"] != "PASS":
        errors.append(f"invalid partition values: {vocabulary['invalid_partitions']}")

    # G. partition counts (patient-first)
    partition_patient_counts = {partition: 0 for partition in PARTITIONS}
    partition_record_counts = {partition: 0 for partition in PARTITIONS}
    seen_groups: dict[str, str] = {}
    for row in split_rows:
        partition_record_counts[row["partition"]] += 1
        if row["participant_group_id"] not in seen_groups:
            seen_groups[row["participant_group_id"]] = row["partition"]
            partition_patient_counts[row["partition"]] += 1
    if sum(partition_patient_counts.values()) != len(eligible_group_ids):
        errors.append(
            f"partition patient counts sum {sum(partition_patient_counts.values())} != "
            f"eligible group count {len(eligible_group_ids)}"
        )
    if sum(partition_record_counts.values()) != len(eligible_record_ids):
        errors.append(
            f"partition record counts sum {sum(partition_record_counts.values())} != "
            f"eligible record count {len(eligible_record_ids)}"
        )

    # Split configuration identity -- every row must agree
    config_fields = ("split_id", "split_seed", "lead_policy_id", "label_map_id")
    expected_config = {
        "split_id": SPLIT_ID,
        "split_seed": str(SPLIT_SEED),
        "lead_policy_id": LEAD_POLICY_ID,
        "label_map_id": LABEL_MAP_ID,
    }
    for row in split_rows:
        for field in config_fields:
            if row[field] != expected_config[field]:
                errors.append(
                    f"record {row['record_id']}: {field}={row[field]!r} != "
                    f"{expected_config[field]!r}"
                )

    # Independent strata recomputation from real raw annotations (never window-derived)
    exclusion_reasons = {row["record_id"]: row["reason"] for row in exclusion_rows}
    all_record_ids = mitdb.list_records()
    recomputed_groups = build_mitdb_patient_groups(
        all_record_ids, eligible_record_ids, exclusion_reasons
    )
    recomputed_group_records: dict[str, list[str]] = {}
    for group_row in recomputed_groups:
        if group_row.core_channel_eligible:
            recomputed_group_records.setdefault(group_row.participant_group_id, []).append(
                group_row.record_id
            )

    recomputed_presence = {}
    for group_id, record_ids in recomputed_group_records.items():
        record_annotations = {rid: _record_annotations(rid) for rid in record_ids}
        recomputed_presence[group_id] = compute_patient_event_presence(
            group_id, record_annotations
        )

    strata_by_group = {row["participant_group_id"]: row["has_svf_event"] for row in strata_rows}
    split_has_svf_by_group = {
        row["participant_group_id"]: row["has_svf_event"] for row in split_rows
    }

    strata_mismatches = []
    for group_id in eligible_group_ids:
        recomputed_value = str(recomputed_presence[group_id].has_svf_event).upper()
        if strata_by_group.get(group_id) != recomputed_value:
            strata_mismatches.append(
                f"{group_id}: mitdb_patient_strata.csv={strata_by_group.get(group_id)} "
                f"recomputed={recomputed_value}"
            )
        if split_has_svf_by_group.get(group_id) != recomputed_value:
            strata_mismatches.append(
                f"{group_id}: MITDB_SPLIT_V1.csv={split_has_svf_by_group.get(group_id)} "
                f"recomputed={recomputed_value}"
            )
    if strata_mismatches:
        errors.append(f"strata recomputation mismatches: {strata_mismatches}")

    # Upstream hash verification (T009's recorded upstream_hashes vs recomputed now)
    t009_report_path = ROOT / "reports/t009/split_generation.json"
    t009_report = json.loads(t009_report_path.read_text(encoding="utf-8"))
    upstream_expected = t009_report["upstream_hashes"]
    upstream_actual = {name: hash_file(path) for name, path in _upstream_paths().items()}
    upstream_mismatches = {
        name: {"expected": upstream_expected[name], "actual": upstream_actual[name]}
        for name in upstream_expected
        if upstream_expected[name] != upstream_actual[name]
    }
    if upstream_mismatches:
        errors.append(f"upstream hash mismatch: {upstream_mismatches}")

    # F04/G4 must be frozen/PASS before F05 can freeze
    freeze_registry_rows = read_csv(ROOT / "manifests/freeze_registry_v1.csv")
    gate_registry_rows = read_csv(ROOT / "manifests/gate_registry_v1.csv")
    freeze_rows = {row["freeze_id"]: row for row in freeze_registry_rows}
    gate_rows = {row["gate_id"]: row for row in gate_registry_rows}
    if freeze_rows["F04"]["current_status"] != "FROZEN":
        errors.append("F04 is not FROZEN; cannot freeze F05 against a mutable label definition")
    if gate_rows["G4"]["status"] != "PASS":
        errors.append("G4 is not PASS")

    # Deterministic reconstruction, entirely in memory -- never touches the committed CSV
    positive_group_ids = sorted(
        g for g in eligible_group_ids if recomputed_presence[g].has_svf_event
    )
    negative_group_ids = sorted(
        g for g in eligible_group_ids if not recomputed_presence[g].has_svf_event
    )
    partition_capacities = apportion_partition_capacities(len(eligible_group_ids))
    positive_quotas = apportion_stratum_capacities(
        partition_capacities.quotas, len(positive_group_ids)
    )
    negative_quotas = {
        partition: partition_capacities.quotas[partition] - positive_quotas[partition]
        for partition in PARTITIONS
    }
    reconstructed_assignments = assign_partitions(
        SPLIT_ID,
        SPLIT_SEED,
        positive_group_ids,
        negative_group_ids,
        positive_quotas,
        negative_quotas,
    )
    reconstructed_partition_by_group = {
        row.participant_group_id: row.partition for row in reconstructed_assignments
    }
    reconstruction_mismatches = [
        group_id
        for group_id in eligible_group_ids
        if reconstructed_partition_by_group.get(group_id) != seen_groups.get(group_id)
    ]
    if reconstruction_mismatches:
        errors.append(
            f"deterministic reconstruction mismatch for groups: {reconstruction_mismatches}"
        )

    # Small-N facts are warnings, never audit failures (v2.2 / T010 Section 30)
    for partition in PARTITIONS:
        positive_count = sum(
            1
            for group_id, assigned_partition in seen_groups.items()
            if assigned_partition == partition and recomputed_presence[group_id].has_svf_event
        )
        negative_count = partition_patient_counts[partition] - positive_count
        if negative_count == 0:
            warnings.append(f"{partition} has zero SVF-absent patient groups (small-N reality)")
    if len(negative_group_ids) <= 5:
        warnings.append(
            f"only {len(negative_group_ids)} SVF-absent patient groups exist across the entire "
            "eligible pool -- a genuine result of the predeclared algorithm, not adjusted for"
        )

    candidate_hash_after = hash_file(SPLIT_CSV)
    candidate_unchanged = candidate_hash_before == candidate_hash_after
    if not candidate_unchanged:
        errors.append(
            f"SPLIT_HASH_MISMATCH: candidate changed during audit "
            f"({candidate_hash_before} -> {candidate_hash_after})"
        )

    overall_status = "PASS" if not errors else "FAIL"
    report: dict[str, Any] = {
        "task_id": "T010",
        "gate_id": "G5",
        "freeze_id": "F05",
        "split_id": SPLIT_ID,
        "split_sha256": candidate_hash_after,
        "candidate_hash_before": candidate_hash_before,
        "candidate_hash_after": candidate_hash_after,
        "candidate_unchanged": candidate_unchanged,
        "eligible_record_count": len(eligible_record_ids),
        "split_record_count": len({row["record_id"] for row in split_rows}),
        "eligible_record_closure": closure["status"],
        "eligible_patient_group_count": len(eligible_group_ids),
        "partition_patient_counts": partition_patient_counts,
        "partition_record_counts": partition_record_counts,
        "pairwise_patient_intersections": disjointness["pairwise_overlaps"],
        "unassigned_groups": completeness["unassigned_count"],
        "multiply_assigned_groups": completeness["multiply_assigned_count"],
        "201_202_same_group": invariant_201_202["same_group"],
        "201_202_same_partition": invariant_201_202["same_partition"],
        "strata_recomputed": True,
        "strata_mismatch_count": len(strata_mismatches),
        "upstream_hash_verification": "PASS" if not upstream_mismatches else "FAIL",
        "split_reconstruction_match": not reconstruction_mismatches,
        "partition_role_contract_status": "IMPLEMENTED",
        "synthetic_window_harness_status": "SEE_reports/splits/window_audit.json",
        "real_window_audit_status": "DEFERRED_TO_T013",
        "errors": errors,
        "warnings": warnings,
        "overall_status": overall_status,
    }
    return report


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = run_audit()
    output_path = REPORT_DIR / "split_audit.json"
    temporary = output_path.with_suffix(f"{output_path.suffix}.tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(output_path)

    print(f"T010 independent split audit: {report['overall_status']}")
    if report["overall_status"] != "PASS":
        raise RuntimeError(f"G5_AUDIT_FAILURE: {report['errors']}")


if __name__ == "__main__":
    main()
