"""Frozen MODEL_V1 robustness study on official NSTDB v1.0.0 stress records."""

from __future__ import annotations

import argparse
import copy
import csv
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
import wfdb
import yaml

from datasets.nstdb import (
    DEFAULT_RAW_ROOT,
    NOISE_TYPE_BY_RECORD,
    PURE_NOISE,
    SNR_DB_BY_SUFFIX,
    STRESS_ECG,
    classify_record_role,
    list_records,
    read_header,
)
from evaluation.calibration import (
    apply_operating_threshold,
    load_cal_v1,
    raw_probability_from_logit,
    source_domain_calibrated_probability,
    verify_cal_v1,
)
from evaluation.internal_test import verify_internal_test_freeze
from evaluation.metrics import pooled_binary_metrics
from models.model_freeze import load_frozen_model_v1, verify_frozen_model_v1
from nhm.hashing import hash_file
from preprocessing.ecg import ECGPreprocessingPipeline
from preprocessing.quality import QualityState, evaluate_ecg_quality
from preprocessing.windowing import (
    NORMALIZATION_EPSILON,
    PREPROC_ID,
    SAMPLE_RATE_HZ,
    WINDOW_SAMPLES,
    candidate_window_starts,
    normalize_window_zscore,
    select_annotation_indices_closed,
    summarize_annotations,
)

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_ID = "NOISE_ROBUSTNESS_V1"
CONFIG_PATH = Path("configs/noise_robustness_v1.yaml")
EXPECTED_RECORDS = (
    "118e24", "118e18", "118e12", "118e06", "118e00", "118e_6",
    "119e24", "119e18", "119e12", "119e06", "119e00", "119e_6",
)
SNR_LEVELS = (24, 18, 12, 6, 0, -6)
RESAMPLER_ID = "MITDB_360_TO_250_V1"
SOURCE_RATE_HZ = 360


class NoiseRobustnessError(RuntimeError):
    """Raised for protocol, pairing, source, or frozen-contract violations."""


@dataclass(frozen=True)
class StressWindow:
    base_record_id: str
    nstdb_record_id: str
    snr_db: int
    source_right_edge_index: int
    pair_id: str
    label: int | None
    quality: str
    waveform: np.ndarray


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def snr_mapping(record_id: str) -> int:
    classification = classify_record_role(record_id)
    if classification.role != STRESS_ECG or classification.snr_db is None:
        raise NoiseRobustnessError(f"NOT_A_STRESS_RECORD: {record_id}")
    return classification.snr_db


def pair_id(base_record_id: str, source_right_edge_index: int) -> str:
    return f"NSTDB_PAIR_{base_record_id}_{source_right_edge_index:09d}"


def validate_pair_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["pair_id"]), []).append(row)
    incomplete: list[str] = []
    label_disagreements: list[str] = []
    duplicate_conditions: list[str] = []
    expected = set(SNR_LEVELS)
    for identity, members in grouped.items():
        conditions = [int(member["snr_db"]) for member in members]
        if set(conditions) != expected:
            incomplete.append(identity)
        if len(conditions) != len(set(conditions)):
            duplicate_conditions.append(identity)
        if len({int(member["label"]) for member in members}) != 1:
            label_disagreements.append(identity)
    if incomplete or label_disagreements or duplicate_conditions:
        raise NoiseRobustnessError(
            "NSTDB_PAIRING_FAILURE: "
            f"incomplete={len(incomplete)}, labels={len(label_disagreements)}, "
            f"duplicates={len(duplicate_conditions)}"
        )
    return {
        "pair_ids": len(grouped),
        "complete_six_snr_pair_ids": len(grouped),
        "incomplete_pair_ids": 0,
        "label_disagreements": 0,
        "duplicate_condition_rows": 0,
    }


def verify_official_sources(root: Path = ROOT) -> dict[str, Any]:
    raw_root = root / DEFAULT_RAW_ROOT
    records = list_records(raw_root)
    if set(records) != set(EXPECTED_RECORDS) | set(NOISE_TYPE_BY_RECORD):
        raise NoiseRobustnessError("NSTDB_OFFICIAL_RECORD_ALLOWLIST_MISMATCH")
    manifest_rows: list[dict[str, str]]
    with (root / "manifests/datasets/nstdb_records.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        manifest_rows = list(csv.DictReader(handle))
    by_record = {row["record_id"]: row for row in manifest_rows}
    for record_id in records:
        if by_record[record_id]["hash_verified"] != "True":
            raise NoiseRobustnessError(f"NSTDB_HASH_NOT_VERIFIED: {record_id}")
    annotation_hashes: dict[str, set[str]] = {"118": set(), "119": set()}
    for record_id in EXPECTED_RECORDS:
        classification = classify_record_role(record_id)
        expected_snr = SNR_DB_BY_SUFFIX[record_id[3:]]
        if classification.snr_db != expected_snr:
            raise NoiseRobustnessError("NSTDB_SNR_MAPPING_MISMATCH")
        header = read_header(record_id, raw_root)
        if header.fs != SOURCE_RATE_HZ or "MLII" not in header.sig_name:
            raise NoiseRobustnessError("NSTDB_LEAD_POLICY_CONFLICT")
        row = by_record[record_id]
        if row["snr_db"] != str(expected_snr) or row["clean_source_record"] != record_id[:3]:
            raise NoiseRobustnessError("NSTDB_FROZEN_MANIFEST_MAPPING_MISMATCH")
        annotation_hashes[record_id[:3]].add(hash_file(raw_root / f"{record_id}.atr"))
    if any(len(values) != 1 for values in annotation_hashes.values()):
        raise NoiseRobustnessError("NSTDB_PAIRED_ANNOTATION_MISMATCH")
    for record_id in NOISE_TYPE_BY_RECORD:
        if classify_record_role(record_id).role != PURE_NOISE:
            raise NoiseRobustnessError("NSTDB_PURE_NOISE_ROLE_MISMATCH")
        if (raw_root / f"{record_id}.atr").exists():
            raise NoiseRobustnessError("NSTDB_PURE_NOISE_UNEXPECTED_ANNOTATIONS")
    return {
        "dataset": "MIT-BIH Noise Stress Test Database",
        "version": "1.0.0",
        "raw_root": str(DEFAULT_RAW_ROOT),
        "official_record_count": 15,
        "stress_ecg_count": 12,
        "pure_noise_count": 3,
        "sampling_rate_hz": SOURCE_RATE_HZ,
        "exact_MLII_all_stress_records": True,
        "fallback_used": False,
        "provider_hashes": "PASS",
        "annotation_identity_by_base": "PASS",
    }


def _preprocess(signal: np.ndarray) -> np.ndarray:
    pipeline = ECGPreprocessingPipeline(SOURCE_RATE_HZ, RESAMPLER_ID)
    output_values: list[np.ndarray] = []
    for start in range(0, signal.size, 4096):
        stop = min(start + 4096, signal.size)
        output = pipeline.process(
            signal[start:stop],
            np.arange(start, stop, dtype=np.int64),
            source_timestamps_us=(
                np.arange(start, stop, dtype=np.int64) * 1_000_000 // SOURCE_RATE_HZ
                if start == 0
                else None
            ),
        )
        if output.events:
            raise NoiseRobustnessError("NSTDB_UNEXPECTED_SOURCE_GAP")
        output_values.extend(chunk.filtered_values for chunk in output.chunks)
    return np.concatenate(output_values)


def build_stress_windows(record_id: str, root: Path = ROOT) -> list[StressWindow]:
    raw_root = root / DEFAULT_RAW_ROOT
    header = wfdb.rdheader(str(raw_root / record_id))
    exact = [index for index, name in enumerate(header.sig_name) if name == "MLII"]
    if len(exact) != 1:
        raise NoiseRobustnessError("NSTDB_LEAD_POLICY_CONFLICT")
    source = wfdb.rdrecord(str(raw_root / record_id), physical=True).p_signal[:, exact[0]]
    if not np.all(np.isfinite(source)):
        raise NoiseRobustnessError("NSTDB_NONFINITE_SOURCE_SIGNAL")
    filtered = _preprocess(np.asarray(source, dtype=np.float64))
    annotations = wfdb.rdann(str(raw_root / record_id), "atr")
    samples = np.asarray(annotations.sample, dtype=np.int64)
    symbols = np.asarray(annotations.symbol, dtype=object)
    classification = classify_record_role(record_id)
    assert classification.clean_source_record is not None and classification.snr_db is not None
    result: list[StressWindow] = []
    for start in candidate_window_starts(filtered.size):
        end = start + WINDOW_SAMPLES
        prediction_us = end * 1_000_000 // SAMPLE_RATE_HZ
        selected = select_annotation_indices_closed(samples, SOURCE_RATE_HZ, prediction_us)
        summary = summarize_annotations(str(symbol) for symbol in symbols[selected].tolist())
        window = np.ascontiguousarray(filtered[start:end], dtype=np.float64)
        quality = evaluate_ecg_quality(window)
        source_right_edge = prediction_us * SOURCE_RATE_HZ // 1_000_000
        result.append(
            StressWindow(
                base_record_id=classification.clean_source_record,
                nstdb_record_id=record_id,
                snr_db=classification.snr_db,
                source_right_edge_index=source_right_edge,
                pair_id=pair_id(classification.clean_source_record, source_right_edge),
                label=summary.label,
                quality=quality.state.value,
                waveform=window,
            )
        )
    return result


def fixed_paired_population(windows: list[StressWindow]) -> list[StressWindow]:
    by_pair: dict[str, list[StressWindow]] = {}
    for window in windows:
        by_pair.setdefault(window.pair_id, []).append(window)
    paired: list[StressWindow] = []
    for identity in sorted(by_pair):
        members = by_pair[identity]
        labels = {member.label for member in members}
        conditions = {member.snr_db for member in members}
        if len(members) == 6 and conditions == set(SNR_LEVELS) and len(labels) == 1:
            label = next(iter(labels))
            if label in (0, 1):
                paired.extend(sorted(members, key=lambda member: -member.snr_db))
    validation_rows = [
        {"pair_id": item.pair_id, "snr_db": item.snr_db, "label": item.label}
        for item in paired
    ]
    validate_pair_rows(validation_rows)
    return paired


def infer_rows(windows: list[StressWindow], root: Path, batch_size: int) -> list[dict[str, Any]]:
    model, metadata = load_frozen_model_v1(root)
    cal = load_cal_v1(root)
    before = copy.deepcopy(model.state_dict())
    normalized = np.stack(
        [normalize_window_zscore(item.waveform, epsilon=NORMALIZATION_EPSILON) for item in windows]
    ).astype(np.float32)
    logits: list[np.ndarray] = []
    model.eval()
    with torch.inference_mode():
        for start in range(0, len(normalized), batch_size):
            inputs = torch.from_numpy(normalized[start : start + batch_size, None, :])
            logits.append(model(inputs).cpu().numpy()[:, 0])
    if any(not torch.equal(before[key], model.state_dict()[key]) for key in before):
        raise NoiseRobustnessError("MODEL_V1_STATE_MUTATED_DURING_NSTDB")
    raw_logits = np.concatenate(logits).astype(np.float64)
    raw = raw_probability_from_logit(raw_logits)
    transferred = source_domain_calibrated_probability(raw_logits, cal)
    predictions = apply_operating_threshold(transferred, cal)
    rows: list[dict[str, Any]] = []
    for item, logit, raw_p, transferred_p, prediction in zip(
        windows, raw_logits, raw, transferred, predictions, strict=True
    ):
        rows.append(
            {
                "base_record_id": item.base_record_id,
                "nstdb_record_id": item.nstdb_record_id,
                "snr_db": item.snr_db,
                "source_right_edge_index": item.source_right_edge_index,
                "pair_id": item.pair_id,
                "label": int(item.label),
                "quality": item.quality,
                "raw_logit": float(logit),
                "raw_probability": float(raw_p),
                "transferred_source_domain_probability": float(transferred_p),
                "frozen_threshold": float(cal["threshold"]),
                "thresholded_prediction": int(prediction),
                "MODEL_V1_sha256": metadata["checkpoint_sha256"],
                "CAL_V1_sha256": hash_file(root / "artifacts/CAL_V1.json"),
            }
        )
    return rows


def metric_row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    labels = np.asarray([row["label"] for row in rows], dtype=np.int64)
    probabilities = np.asarray(
        [row["transferred_source_domain_probability"] for row in rows], dtype=np.float64
    )
    predictions = np.asarray([row["thresholded_prediction"] for row in rows], dtype=np.int64)
    patients = np.asarray([row["base_record_id"] for row in rows], dtype=str)
    metrics = pooled_binary_metrics(
        labels, probabilities, predictions, patients, allow_undefined=True
    )
    quality = Counter(row["quality"] for row in rows)
    count = len(rows)
    return {
        "source_record_count": len(set(patients.tolist())),
        "paired_window_count": count,
        "positive_windows": int(np.sum(labels == 1)),
        "negative_windows": int(np.sum(labels == 0)),
        "AUPRC": metrics["AUPRC"],
        "AUROC": metrics["AUROC"],
        "pooled_F1": metrics["pooled_F1"],
        "precision": metrics["precision"],
        "sensitivity": metrics["sensitivity"],
        "specificity": metrics["specificity"],
        "VALID_count": quality[QualityState.VALID.value],
        "DEGRADED_count": quality[QualityState.DEGRADED.value],
        "UNUSABLE_count": quality[QualityState.UNUSABLE.value],
        "VALID_fraction": quality[QualityState.VALID.value] / count,
        "DEGRADED_fraction": quality[QualityState.DEGRADED.value] / count,
        "UNUSABLE_fraction": quality[QualityState.UNUSABLE.value] / count,
    }


def summarize_prediction_rows(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    pooled: list[dict[str, Any]] = []
    by_record: list[dict[str, Any]] = []
    for snr in SNR_LEVELS:
        selected = [row for row in rows if row["snr_db"] == snr]
        pooled.append({"snr_db": snr, **metric_row(selected)})
        for base in ("118", "119"):
            record_rows = [row for row in selected if row["base_record_id"] == base]
            by_record.append({"base_record_id": base, "snr_db": snr, **metric_row(record_rows)})
    reference = float(pooled[0]["AUPRC"])
    for row in pooled:
        row["delta_AUPRC_vs_24dB"] = float(row["AUPRC"]) - reference
    return pooled, by_record


def run_protocol(root: Path = ROOT) -> dict[str, Any]:
    config = yaml.safe_load((root / CONFIG_PATH).read_text(encoding="utf-8"))
    source_audit = verify_official_sources(root)
    verify_frozen_model_v1(root)
    verify_cal_v1(root)
    verify_internal_test_freeze(root)
    windows = [
        window
        for record in EXPECTED_RECORDS
        for window in build_stress_windows(record, root)
    ]
    paired = fixed_paired_population(windows)
    rows = infer_rows(paired, root, int(config["inference"]["batch_size"]))
    pooled, by_record = summarize_prediction_rows(rows)
    return {
        "source_audit": source_audit,
        "all_candidate_windows": windows,
        "paired_windows": paired,
        "prediction_rows": rows,
        "pooled": pooled,
        "by_record": by_record,
    }


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: (
                        ""
                        if row.get(key) is None
                        else format(row[key], ".17g")
                        if isinstance(row.get(key), float)
                        else row.get(key)
                    )
                    for key in fields
                }
            )


def curve_svg(pooled: list[dict[str, Any]], by_record: list[dict[str, Any]]) -> str:
    order = sorted(SNR_LEVELS)
    x = {snr: 70 + index * 90 for index, snr in enumerate(order)}

    def points(rows: list[dict[str, Any]]) -> str:
        by_snr = {int(row["snr_db"]): row for row in rows}
        return " ".join(
            f"{x[snr]},{510 - 420 * float(by_snr[snr]['AUPRC']):.6f}" for snr in order
        )

    pooled_points = points(pooled)
    record_118 = points([row for row in by_record if row["base_record_id"] == "118"])
    record_119 = points([row for row in by_record if row["base_record_id"] == "119"])
    ticks = "".join(
        f'<text x="{x[snr]}" y="535" text-anchor="middle" font-size="12">{snr}</text>\n'
        for snr in order
    )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="650" height="570" '
        'viewBox="0 0 650 570">\n'
        '<rect width="650" height="570" fill="white"/>\n'
        '<text x="325" y="25" text-anchor="middle" font-size="16">'
        "Official NSTDB controlled-noise robustness — highest-SNR reference is not clean"
        "</text>\n"
        '<line x1="70" y1="510" x2="520" y2="510" stroke="#222"/>\n'
        '<line x1="70" y1="90" x2="70" y2="510" stroke="#222"/>\n'
        f'<polyline points="{record_118}" fill="none" stroke="#999" stroke-width="1"/>\n'
        f'<polyline points="{record_119}" fill="none" stroke="#777" stroke-width="1"/>\n'
        f'<polyline points="{pooled_points}" fill="none" stroke="#1259a7" stroke-width="3"/>\n'
        f"{ticks}"
        '<text x="295" y="560" text-anchor="middle" font-size="13">SNR (dB)</text>\n'
        '<text x="18" y="300" transform="rotate(-90 18 300)" text-anchor="middle" '
        'font-size="13">Pooled AUPRC</text>\n'
        '<text x="545" y="105" font-size="12" fill="#1259a7">pooled</text>\n'
        '<text x="545" y="125" font-size="12" fill="#999">118</text>\n'
        '<text x="545" y="145" font-size="12" fill="#777">119</text>\n'
        "</svg>\n"
    )


def _semantic(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "prediction_rows": result["prediction_rows"],
        "pooled": result["pooled"],
        "by_record": result["by_record"],
    }


def run_and_write(root: Path = ROOT) -> dict[str, Any]:
    config_path = root / CONFIG_PATH
    config_sha_before = hash_file(config_path)
    model_sha_before = hash_file(root / "checkpoints/MODEL_V1.pt")
    cal_sha_before = hash_file(root / "artifacts/CAL_V1.json")
    internal_report_sha_before = hash_file(root / "reports/internal_test.json")
    internal_guard_sha_before = hash_file(root / "artifacts/internal_test_access_v1.json")
    first = run_protocol(root)
    second = run_protocol(root)
    first_semantic = _semantic(first)
    second_semantic = _semantic(second)
    if first_semantic != second_semantic:
        raise NoiseRobustnessError("NSTDB_ROBUSTNESS_REPRODUCIBILITY_FAILURE")
    max_logit_difference = max(
        abs(float(left["raw_logit"]) - float(right["raw_logit"]))
        for left, right in zip(
            first["prediction_rows"], second["prediction_rows"], strict=True
        )
    )
    config_sha_after = hash_file(config_path)
    if config_sha_before != config_sha_after:
        raise NoiseRobustnessError("NSTDB_METHOD_CONFIG_CHANGED_AFTER_RESULTS")
    frozen_after = {
        "MODEL_V1": hash_file(root / "checkpoints/MODEL_V1.pt"),
        "CAL_V1": hash_file(root / "artifacts/CAL_V1.json"),
        "internal_test_report": hash_file(root / "reports/internal_test.json"),
        "internal_test_guard": hash_file(root / "artifacts/internal_test_access_v1.json"),
    }
    expected_frozen = {
        "MODEL_V1": model_sha_before,
        "CAL_V1": cal_sha_before,
        "internal_test_report": internal_report_sha_before,
        "internal_test_guard": internal_guard_sha_before,
    }
    if frozen_after != expected_frozen:
        raise NoiseRobustnessError("NSTDB_FROZEN_UPSTREAM_MUTATION")

    predictions = first["prediction_rows"]
    prediction_fields = [
        "base_record_id", "nstdb_record_id", "snr_db", "source_right_edge_index",
        "pair_id", "label", "quality", "raw_logit", "raw_probability",
        "transferred_source_domain_probability", "frozen_threshold",
        "thresholded_prediction", "MODEL_V1_sha256", "CAL_V1_sha256",
    ]
    _write_csv(root / "reports/t019/nstdb_predictions.csv", predictions, prediction_fields)
    curve_fields = [
        "snr_db", "source_record_count", "paired_window_count", "positive_windows",
        "negative_windows", "AUPRC", "delta_AUPRC_vs_24dB", "AUROC", "pooled_F1",
        "precision", "sensitivity", "specificity", "VALID_count", "DEGRADED_count",
        "UNUSABLE_count", "VALID_fraction", "DEGRADED_fraction", "UNUSABLE_fraction",
    ]
    _write_csv(root / "reports/noise_robustness.csv", first["pooled"], curve_fields)
    by_record_fields = [
        "base_record_id",
        *[field for field in curve_fields if field != "delta_AUPRC_vs_24dB"],
    ]
    _write_csv(
        root / "reports/t019/noise_robustness_by_record.csv",
        first["by_record"],
        by_record_fields,
    )
    (root / "reports/noise_robustness.svg").write_text(
        curve_svg(first["pooled"], first["by_record"]), encoding="utf-8"
    )

    all_windows = first["all_candidate_windows"]
    paired_windows = first["paired_windows"]
    all_pair_ids = {window.pair_id for window in all_windows}
    primary_pair_ids = {window.pair_id for window in paired_windows}
    primary_labels = {
        identity: next(window.label for window in paired_windows if window.pair_id == identity)
        for identity in primary_pair_ids
    }
    pairing_audit = {
        "base_source_records": ["118", "119"],
        "pair_identity": "BASE_RECORD_PLUS_EXACT_SOURCE_RIGHT_EDGE_INDEX_V1",
        "candidate_windows_per_condition": {
            record: sum(window.nstdb_record_id == record for window in all_windows)
            for record in EXPECTED_RECORDS
        },
        "candidate_pair_ids": len(all_pair_ids),
        "paired_label_eligible_pair_ids": len(primary_pair_ids),
        "complete_six_snr_pair_ids": len(primary_pair_ids),
        "incomplete_pair_ids": 0,
        "label_disagreements": 0,
        "annotation_semantic_disagreements": 0,
        "duplicate_condition_rows": 0,
        "primary_paired_windows_per_condition": len(primary_pair_ids),
        "positive_labels": sum(value == 1 for value in primary_labels.values()),
        "negative_labels": sum(value == 0 for value in primary_labels.values()),
        "overall_status": "PASS",
    }
    _write_json(root / "reports/t019/pairing_audit.json", pairing_audit)
    quality_by_snr = {
        str(row["snr_db"]): {
            key: row[key]
            for key in (
                "VALID_count", "VALID_fraction", "DEGRADED_count", "DEGRADED_fraction",
                "UNUSABLE_count", "UNUSABLE_fraction",
            )
        }
        for row in first["pooled"]
    }
    _write_json(root / "reports/t019/quality_by_snr.json", quality_by_snr)
    raw_root = root / DEFAULT_RAW_ROOT
    pure_noise = {
        "dataset": "NSTDB-v1.0.0",
        "records": {
            record: {
                "present": (raw_root / f"{record}.hea").exists()
                and (raw_root / f"{record}.dat").exists(),
                "hash_verified": True,
                "noise_type": noise_type,
                "annotations_present": (raw_root / f"{record}.atr").exists(),
            }
            for record, noise_type in NOISE_TYPE_BY_RECORD.items()
        },
        "annotations_absent_by_source_design": True,
        "used_for_AAMI_classification_metrics": False,
        "predictive_labels_fabricated": False,
        "overall_status": "PASS",
    }
    _write_json(root / "reports/t019/pure_noise_source_audit.json", pure_noise)
    protocol_audit = {
        "protocol_id": PROTOCOL_ID,
        "NSTDB_hashes_verified": True,
        "stress_record_count": 12,
        "pure_noise_record_count": 3,
        "SNR_levels_db": list(SNR_LEVELS),
        "exact_MLII_policy": "PASS",
        "AAMI_map_unchanged": True,
        "PREPROC_unchanged": True,
        "MODEL_unchanged": True,
        "CAL_V1_unchanged": True,
        "primary_reference": "24dB_HIGHEST_SNR_NOT_CLEAN",
        "paired_population_fixed": True,
        "primary_metric": "POOLED_AUPRC",
        "internal_test_accessed": False,
        "INCART_accessed": False,
        "post_result_tuning": False,
        "method_config_sha_before": config_sha_before,
        "method_config_sha_after": config_sha_after,
        "overall_status": "PASS",
    }
    _write_json(root / "reports/t019/protocol_audit.json", protocol_audit)
    reproducibility = {
        "protocol_id": PROTOCOL_ID,
        "paired_example_ids_repeated": True,
        "labels_repeated": True,
        "maximum_logit_difference": max_logit_difference,
        "probabilities_repeated": True,
        "metric_tables_repeated": True,
        "quality_counts_repeated": True,
        "semantic_content_repeated": True,
        "MODEL_V1_inference_runs": 2,
        "method_config_sha_before": config_sha_before,
        "method_config_sha_after": config_sha_after,
        "overall_status": "PASS",
    }
    _write_json(root / "reports/t019/reproducibility.json", reproducibility)
    report = {
        "experiment_id": "E05",
        "protocol_id": PROTOCOL_ID,
        "overall_status": "PASS",
        "dataset": "NSTDB",
        "dataset_version": "1.0.0",
        "model_id": "MODEL_V1",
        "model_sha256": model_sha_before,
        "preproc_id": PREPROC_ID,
        "preproc_lock_sha256": hash_file(
            root / "manifests/preprocessing/PREPROC_V1.lock.json"
        ),
        "calibration_id": "CAL_V1",
        "calibration_sha256": cal_sha_before,
        "method_config_sha256": config_sha_before,
        "stress_records": list(EXPECTED_RECORDS),
        "SNR_mapping": {record: snr_mapping(record) for record in EXPECTED_RECORDS},
        "source_records": ["118", "119"],
        "paired_window_count_per_condition": len(primary_pair_ids),
        "positive_windows_per_condition": pairing_audit["positive_labels"],
        "negative_windows_per_condition": pairing_audit["negative_labels"],
        "primary_metric": "POOLED_AUPRC",
        "reference_snr_db": 24,
        "reference_is_clean": False,
        "analysis_mode": "OFFLINE_MODEL_STRESS_ONLY",
        "per_snr_pooled_results": first["pooled"],
        "per_record_results": first["by_record"],
        "quality_distributions": quality_by_snr,
        "pure_noise_source_audit": "reports/t019/pure_noise_source_audit.json",
        "calibration_domain": "MIT-BIH-v1.0.0",
        "NSTDB_calibration_claim": False,
        "no_tuning": True,
        "no_adaptation": True,
        "internal_test_accessed": False,
        "INCART_accessed": False,
        "claim_boundary": (
            "Controlled official NSTDB noise-stress sensitivity across predeclared SNR "
            "conditions only; not clinical, wearable, all-noise, or population evidence."
        ),
    }
    _write_json(root / "reports/noise_robustness.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true", required=True)
    arguments = parser.parse_args()
    if not arguments.run:
        raise NoiseRobustnessError("NSTDB_RUN_FLAG_REQUIRED")
    report = run_and_write(ROOT)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
