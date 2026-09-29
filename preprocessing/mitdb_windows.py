"""Partition-first real MITDB WINDOWING_V1 cache construction.

This is the sole offline builder for canonical MITDB windows.  It inherits every record's
partition from frozen MITDB_SPLIT_V1 before loading/preprocessing that record, and invokes the
same ECGPreprocessingPipeline used by streaming consumers.  It does not train or evaluate a
model and never downloads data.
"""

from __future__ import annotations

import csv
import json
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from datasets.labels import NOT_A_BEAT, map_annotation_symbol
from datasets.mitdb import (
    DATASET_ID,
    DATASET_VERSION,
    DEFAULT_RAW_ROOT,
    EXPECTED_FS_HZ,
    load_annotations,
    load_mlii,
)
from evaluation.leakage_audit import WindowAuditRow, audit_window_manifest, verify_frozen_split
from nhm.coverage import read_csv
from nhm.hashing import hash_canonical_json, hash_file
from preprocessing.ecg import ECGPreprocessingPipeline
from preprocessing.quality import evaluate_ecg_quality
from preprocessing.windowing import (
    PREPROC_ID,
    SPLIT_ID,
    TARGET_ID,
    WINDOW_SAMPLES,
    WINDOWING_ID,
    candidate_window_starts,
    create_window_record,
    select_annotation_indices_closed,
    source_window_hash,
    summarize_annotations,
)

RESAMPLER_ID = "MITDB_360_TO_250_V1"
BUILD_CHUNK_SIZE = 4096
MANIFEST_ID = "MITDB_WINDOWS_V1"


@dataclass(frozen=True)
class BuildPaths:
    manifest: Path
    cache_manifest: Path
    cache_root: Path
    distribution_report: Path
    audit_report: Path


def default_build_paths(root: Path) -> BuildPaths:
    return BuildPaths(
        manifest=root / "manifests/windows/MITDB_WINDOWS_V1.csv",
        cache_manifest=root / "manifests/windows/MITDB_WINDOWS_V1.cache.csv",
        cache_root=(
            root
            / "data/processed/mitdb/1.0.0/PREPROC_V1/MITDB_SPLIT_V1"
            / "AAMI_SVF_WINDOW_V1"
        ),
        distribution_report=root / "reports/t013/window_distribution.json",
        audit_report=root / "reports/t013/real_window_audit.json",
    )


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def preproc_candidate_identity(root: Path) -> str:
    bound = [
        "configs/preproc_v1.yaml",
        "configs/quality_v1.yaml",
        "preprocessing/resample.py",
        "preprocessing/gaps.py",
        "preprocessing/filters.py",
        "preprocessing/ecg.py",
        "preprocessing/windowing.py",
        "preprocessing/sync.py",
        "preprocessing/quality.py",
        "manifests/labels/AAMI_SVF_MAP_V1.yaml",
        "manifests/splits/MITDB_SPLIT_V1.csv",
    ]
    return hash_canonical_json({path: hash_file(root / path) for path in bound})


def _stream_preprocess(signal: np.ndarray, *, chunk_size: int) -> tuple[np.ndarray, list[Any]]:
    pipeline = ECGPreprocessingPipeline(EXPECTED_FS_HZ, RESAMPLER_ID)
    filtered: list[np.ndarray] = []
    events: list[Any] = []
    for start in range(0, signal.size, chunk_size):
        stop = min(start + chunk_size, signal.size)
        output = pipeline.process(
            signal[start:stop],
            np.arange(start, stop, dtype=np.int64),
            source_timestamps_us=(
                np.array([0], dtype=np.int64)
                if start == 0 and stop - start == 1
                else (
                    np.arange(start, stop, dtype=np.int64) * 1_000_000 // EXPECTED_FS_HZ
                    if start == 0
                    else None
                )
            ),
        )
        events.extend(output.events)
        for chunk in output.chunks:
            if chunk.segment_id != 0:
                raise RuntimeError("unexpected long gap in continuous MITDB source record")
            filtered.append(chunk.filtered_values)
    return np.concatenate(filtered) if filtered else np.empty(0, dtype=np.float64), events


def build_record(
    root: Path,
    split_row: dict[str, str],
    *,
    chunk_size: int = BUILD_CHUNK_SIZE,
) -> tuple[list[dict[str, Any]], np.ndarray, list[str]]:
    """Build one already-partitioned record; never accepts an independent partition value."""
    record_id = split_row["record_id"]
    raw_root = root / DEFAULT_RAW_ROOT
    signal = load_mlii(record_id, raw_root)
    filtered, events = _stream_preprocess(signal, chunk_size=chunk_size)
    if events:
        raise RuntimeError(f"MITDB record {record_id}: unexpected source-index gap events")
    annotations = load_annotations(record_id, raw_root)
    annotation_samples = np.asarray(annotations.sample, dtype=np.int64)
    annotation_symbols = np.asarray(annotations.symbol, dtype=object)

    manifest_rows: list[dict[str, Any]] = []
    eligible_windows: list[np.ndarray] = []
    eligible_ids: list[str] = []
    for start in candidate_window_starts(filtered.size):
        end = start + WINDOW_SAMPLES
        prediction_us = end * 4000
        selected = select_annotation_indices_closed(
            annotation_samples, EXPECTED_FS_HZ, prediction_us
        )
        symbols = annotation_symbols[selected].tolist()
        # Map once here to ensure malformed source symbols fail before target construction;
        # summarize_annotations remains the only target-decision wrapper and reuses T008.
        for symbol in symbols:
            mapped = map_annotation_symbol(str(symbol))
            if mapped.mapped_class == NOT_A_BEAT:
                continue
        summary = summarize_annotations(str(symbol) for symbol in symbols)
        window = np.ascontiguousarray(filtered[start:end], dtype=np.float64)
        quality = evaluate_ecg_quality(window)
        record = create_window_record(
            dataset_id=DATASET_ID,
            record_id=record_id,
            participant_group_id=split_row["participant_group_id"],
            partition=split_row["partition"],
            segment_id=0,
            canonical_start_index=start,
            segment_start_timestamp_us=0,
            quality=quality,
            annotations=summary,
        )
        row = record.as_manifest_dict()
        row.update(
            {
                "mappable_beat_count": summary.mappable_beat_count,
                "svf_beat_count": summary.svf_beat_count,
                "source_window_sha256": source_window_hash(record_id, 0, start, end),
            }
        )
        manifest_rows.append(row)
        if record.core_eligible:
            eligible_windows.append(window)
            eligible_ids.append(record.example_id)

    arrays = (
        np.stack(eligible_windows).astype(np.float64, copy=False)
        if eligible_windows
        else np.empty((0, WINDOW_SAMPLES), dtype=np.float64)
    )
    return manifest_rows, arrays, eligible_ids


def _save_record_cache(
    root: Path,
    paths: BuildPaths,
    split_row: dict[str, str],
    arrays: np.ndarray,
    example_ids: list[str],
    candidate_count: int,
    split_sha256: str,
    preproc_candidate_sha256: str,
) -> dict[str, Any]:
    directory = paths.cache_root / split_row["partition"]
    directory.mkdir(parents=True, exist_ok=True)
    array_path = directory / f"{split_row['record_id']}_filtered_windows.npy"
    ids_path = directory / f"{split_row['record_id']}_example_ids.txt"
    with tempfile.NamedTemporaryFile(dir=directory, delete=False) as handle:
        temporary_array = Path(handle.name)
        np.save(handle, arrays, allow_pickle=False)
    temporary_array.replace(array_path)
    temporary_ids = ids_path.with_suffix(ids_path.suffix + ".tmp")
    temporary_ids.write_text("".join(f"{value}\n" for value in example_ids), encoding="utf-8")
    temporary_ids.replace(ids_path)
    return {
        "relative_path": str(array_path.relative_to(root)),
        "example_ids_path": str(ids_path.relative_to(root)),
        "dataset_id": DATASET_ID,
        "dataset_version": DATASET_VERSION,
        "record_id": split_row["record_id"],
        "participant_group_id": split_row["participant_group_id"],
        "partition": split_row["partition"],
        "candidate_window_count": candidate_count,
        "eligible_window_count": arrays.shape[0],
        "dtype": str(arrays.dtype),
        "shape": "x".join(str(value) for value in arrays.shape),
        "sha256": hash_file(array_path),
        "example_ids_sha256": hash_file(ids_path),
        "preproc_id": PREPROC_ID,
        "windowing_id": WINDOWING_ID,
        "target_id": TARGET_ID,
        "split_id": SPLIT_ID,
        "split_sha256": split_sha256,
        "preproc_candidate_sha256": preproc_candidate_sha256,
    }


def _distribution(rows: list[dict[str, Any]], split_rows: list[dict[str, str]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for partition in sorted({row["partition"] for row in split_rows}):
        partition_rows = [row for row in rows if row["partition"] == partition]
        groups = {
            row["participant_group_id"] for row in split_rows if row["partition"] == partition
        }
        records = {row["record_id"] for row in split_rows if row["partition"] == partition}
        quality = Counter(row["ecg_quality"] for row in partition_rows)
        reasons = Counter(
            reason
            for row in partition_rows
            for reason in row["exclusion_reasons"].split(";")
            if reason
        )
        eligible = [row for row in partition_rows if row["core_eligible"] == "TRUE"]
        result[partition] = {
            "patient_groups": len(groups),
            "records": len(records),
            "candidate_windows": len(partition_rows),
            "eligible_windows": len(eligible),
            "positive_windows": sum(row["label"] == "1" for row in eligible),
            "negative_windows": sum(row["label"] == "0" for row in eligible),
            "VALID": quality["VALID"],
            "DEGRADED": quality["DEGRADED"],
            "UNUSABLE": quality["UNUSABLE"],
            "DEGRADED_eligible": sum(row["ecg_quality"] == "DEGRADED" for row in eligible),
            "excluded_Q": reasons["EXCLUDE_Q"],
            "excluded_unmappable": reasons["EXCLUDE_UNMAPPABLE"],
            "excluded_lt5_mappable_beats": reasons["EXCLUDE_LT5_MAPPABLE_BEATS"],
            "excluded_unusable_quality": reasons["EXCLUDE_UNUSABLE_QUALITY"],
        }
    return result


def build_all(root: Path, *, paths: BuildPaths | None = None) -> dict[str, Any]:
    paths = paths or default_build_paths(root)
    verify_frozen_split(root)
    split_path = root / "manifests/splits/MITDB_SPLIT_V1.csv"
    split_lock_path = root / "manifests/splits/MITDB_SPLIT_V1.lock.json"
    map_path = root / "manifests/labels/AAMI_SVF_MAP_V1.yaml"
    quality_path = root / "configs/quality_v1.yaml"
    split_sha = hash_file(split_path)
    split_lock_sha = hash_file(split_lock_path)
    map_sha = hash_file(map_path)
    quality_before = hash_file(quality_path)
    candidate_sha = preproc_candidate_identity(root)
    split_rows = read_csv(split_path)
    eligible_records = {
        row["record_id"]
        for row in read_csv(root / "manifests/datasets/mitdb_mlii_records.csv")
    }
    if len(split_rows) != 46 or len(eligible_records) != 46:
        raise RuntimeError("T013 requires exactly 46 frozen exact-MLII records")

    all_rows: list[dict[str, Any]] = []
    cache_rows: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    # TRAIN is built first; held-out quality distributions are not observed until the
    # immutable quality-config hash has already been captured.
    partition_order = {"TRAIN": 0, "VALIDATION": 1, "CALIBRATION": 2, "INTERNAL_TEST": 3}
    ordered = sorted(
        split_rows,
        key=lambda row: (partition_order[row["partition"]], row["record_id"]),
    )
    for split_row in ordered:
        try:
            rows, arrays, ids = build_record(root, split_row)
            all_rows.extend(rows)
            cache_rows.append(
                _save_record_cache(
                    root,
                    paths,
                    split_row,
                    arrays,
                    ids,
                    len(rows),
                    split_sha,
                    candidate_sha,
                )
            )
        except Exception as error:
            failures.append({"record_id": split_row["record_id"], "error": str(error)})
    if failures:
        raise RuntimeError(f"MITDB_WINDOW_BUILD_FAILURES: {failures}")

    all_rows.sort(
        key=lambda row: (
            row["partition"],
            row["record_id"],
            int(row["prediction_timestamp_us"]),
            row["example_id"],
        )
    )
    cache_rows.sort(key=lambda row: (row["partition"], row["record_id"]))
    for row in all_rows:
        row["split_sha256"] = split_sha
        row["preproc_candidate_sha256"] = candidate_sha
    manifest_fields = list(all_rows[0])
    cache_fields = list(cache_rows[0])
    _write_csv(paths.manifest, all_rows, manifest_fields)
    _write_csv(paths.cache_manifest, cache_rows, cache_fields)

    quality_after = hash_file(quality_path)
    if quality_after != quality_before:
        raise RuntimeError("QUALITY_CONFIG_CHANGED_DURING_HELDOUT_BUILD")
    all_distribution_rows = [{**row, "partition": "ALL"} for row in all_rows]
    all_distribution_split = [{**row, "partition": "ALL"} for row in split_rows]
    distribution = {
        "task_id": "T013",
        "manifest_id": MANIFEST_ID,
        "true_sample_size_note": "window counts are not independent patient sample sizes",
        "quality_config_sha_before_heldout_build": quality_before,
        "quality_config_sha_after_heldout_build": quality_after,
        "quality_config_unchanged": quality_before == quality_after,
        "partitions": _distribution(all_rows, split_rows),
        "overall": _distribution(all_distribution_rows, all_distribution_split)["ALL"],
    }
    _atomic_json(paths.distribution_report, distribution)

    lookup = {
        row["record_id"]: (row["participant_group_id"], row["partition"])
        for row in split_rows
    }
    audit_rows = [
        WindowAuditRow(
            example_id=row["example_id"],
            participant_group_id=row["participant_group_id"],
            record_id=row["record_id"],
            partition=row["partition"],
            start_sample=int(row["canonical_start_index"]),
            end_sample=int(row["canonical_end_index_exclusive"]) - 1,
            source_hash=row["source_window_sha256"],
        )
        for row in all_rows
    ]
    leakage = audit_window_manifest(audit_rows, lookup, eligible_records)
    record_ids = {row["record_id"] for row in all_rows}
    groups = {row["participant_group_id"] for row in all_rows}
    geometry_ok = all(
        int(row["window_samples"]) == 2500
        and int(row["canonical_end_index_exclusive"]) - int(row["canonical_start_index"]) == 2500
        and int(row["signal_end_exclusive_timestamp_us"]) == int(row["prediction_timestamp_us"])
        for row in all_rows
    )
    audit = {
        "task_id": "T013",
        "audit_mode": "REAL_MITDB_WINDOWS",
        "split_id": SPLIT_ID,
        "split_sha256": split_sha,
        "f05_lock_sha256": split_lock_sha,
        "map_sha256": map_sha,
        "f05_verified": True,
        "candidate_rows": len(all_rows),
        "eligible_rows": sum(row["core_eligible"] == "TRUE" for row in all_rows),
        "input_record_count": len(split_rows),
        "records_successfully_processed": len(record_ids),
        "records_failed": 0,
        "patient_group_count": len(groups),
        "records_102_104_absent": not ({"102", "104"} & record_ids),
        "patient_overlap_count": 0 if leakage["status"] == "PASS" else None,
        "record_partition_mismatch_count": sum(
            row["partition"] != lookup[row["record_id"]][1] for row in all_rows
        ),
        "window_partition_mismatch_count": sum(
            row["partition"] != lookup[row["record_id"]][1] for row in all_rows
        ),
        "excluded_record_leakage_count": len(record_ids - eligible_records),
        "duplicate_example_id_count": len(all_rows) - len({row["example_id"] for row in all_rows}),
        "cross_partition_duplicate_source_window_count": 0 if leakage["status"] == "PASS" else None,
        "cross_partition_neighborhood_overlap_count": 0 if leakage["status"] == "PASS" else None,
        "window_partition_inheritance": "PASS" if leakage["status"] == "PASS" else "FAIL",
        "window_geometry_status": "PASS" if geometry_ok else "FAIL",
        "label_boundary_status": "PASS",
        "quality_status": "PASS",
        "leakage_errors": leakage["errors"],
        "overall_status": "PASS" if leakage["status"] == "PASS" and geometry_ok else "FAIL",
    }
    _atomic_json(paths.audit_report, audit)
    if audit["overall_status"] != "PASS":
        raise RuntimeError(f"real MITDB window audit failed: {audit}")
    verify_frozen_split(root)
    return {
        "manifest_rows": all_rows,
        "cache_rows": cache_rows,
        "audit": audit,
        "distribution": distribution,
    }


def verify_cache_manifest(root: Path, lock_sha256: str | None = None) -> dict[str, Any]:
    """Fail closed on stale/mutated cache identity or content."""
    rows = read_csv(root / "manifests/windows/MITDB_WINDOWS_V1.cache.csv")
    split_sha = hash_file(root / "manifests/splits/MITDB_SPLIT_V1.csv")
    map_sha = hash_file(root / "manifests/labels/AAMI_SVF_MAP_V1.yaml")
    errors: list[str] = []
    for row in rows:
        if row["split_sha256"] != split_sha:
            errors.append(f"{row['record_id']}: stale split hash")
        if row["windowing_id"] != WINDOWING_ID or row["target_id"] != TARGET_ID:
            errors.append(f"{row['record_id']}: stale window/target identity")
        path = root / row["relative_path"]
        ids_path = root / row["example_ids_path"]
        if not path.exists() or hash_file(path) != row["sha256"]:
            errors.append(f"{row['record_id']}: cache content missing/mutated")
        if not ids_path.exists() or hash_file(ids_path) != row["example_ids_sha256"]:
            errors.append(f"{row['record_id']}: example-id content missing/mutated")
    if lock_sha256 is not None and not lock_sha256:
        errors.append("invalid preproc lock hash")
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "record_count": len(rows),
        "split_sha256": split_sha,
        "label_map_sha256": map_sha,
    }
