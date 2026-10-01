"""C031-EA patient-ranking repair and controlled noise-type stress utilities."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import torch

from datasets.mitdb import DEFAULT_RAW_ROOT, EXPECTED_FS_HZ, load_annotations, load_mlii
from evaluation.calibration import (
    apply_operating_threshold,
    load_cal_v1,
    source_domain_calibrated_probability,
)
from evaluation.metrics import pooled_binary_metrics
from evaluation.noise import _preprocess
from federated.feature_noise import build_noise_bank, mix_noise
from models.model_freeze import load_frozen_model_v1
from preprocessing.windowing import (
    NORMALIZATION_EPSILON,
    SAMPLE_RATE_HZ,
    WINDOW_SAMPLES,
    normalize_window_zscore,
    select_annotation_indices_closed,
    summarize_annotations,
)

NOISE_TYPES = {
    "BASELINE_WANDER": "bw",
    "ELECTRODE_MOTION": "em",
    "MUSCLE_ARTIFACT": "ma",
}
SNR_LEVELS = (24, 18, 12, 6, 0, -6)
SEGMENT_NAMESPACE = "C031_NOISE_TYPE_V1"


def patient_brier_ranking(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row["patient_pseudonym"])].append(row)
    result = []
    for patient in sorted(groups):
        selected = groups[patient]
        labels = np.asarray([int(row["label"]) for row in selected], dtype=np.int64)
        probabilities = np.asarray(
            [float(row["source_domain_calibrated_probability"]) for row in selected],
            dtype=np.float64,
        )
        predictions = np.asarray(
            [int(row["thresholded_prediction"]) for row in selected], dtype=np.int64
        )
        positive, negative = int(labels.sum()), int(labels.size - labels.sum())
        tp = int(np.sum((labels == 1) & (predictions == 1)))
        tn = int(np.sum((labels == 0) & (predictions == 0)))
        fp = int(np.sum((labels == 0) & (predictions == 1)))
        fn = int(np.sum((labels == 1) & (predictions == 0)))
        f1 = 2 * tp / (2 * tp + fp + fn) if positive else None
        result.append(
            {
                "patient_pseudonym": patient,
                "window_count": int(labels.size),
                "positive": positive,
                "negative": negative,
                "brier_score": float(np.mean((probabilities - labels) ** 2)),
                "misclassification_count": int(np.sum(labels != predictions)),
                "misclassification_fraction": float(np.mean(labels != predictions)),
                "positive_F1": f1
                if f1 is not None
                else "NOT_INTERPRETABLE_FOR_OVERALL_PATIENT_RANKING",
                "positive_F1_status": "DEFINED_POSITIVE_CLASS_DIAGNOSTIC"
                if positive
                else "NOT_INTERPRETABLE_FOR_OVERALL_PATIENT_RANKING",
                "sensitivity": tp / (tp + fn) if positive else "UNDEFINED_SINGLE_CLASS",
                "specificity": tn / (tn + fp) if negative else "UNDEFINED_SINGLE_CLASS",
                "specificity_status": "DEFINED"
                if negative
                else "NOT_INTERPRETABLE_NO_NEGATIVE_WINDOWS",
            }
        )
    ordered = sorted(result, key=lambda row: (float(row["brier_score"]), row["patient_pseudonym"]))
    ordered[0]["ranking_status"] = "BEST_BY_BRIER"
    ordered[-1]["ranking_status"] = "WORST_BY_BRIER"
    for row in ordered[1:-1]:
        row["ranking_status"] = "UNRANKED_EXTREME"
    return ordered


def noise_offset(base_window_id: str, noise_type: str, noise_length: int) -> int:
    if noise_type not in NOISE_TYPES:
        raise ValueError(f"unknown noise type: {noise_type}")
    material = f"{SEGMENT_NAMESPACE}|{base_window_id}|{noise_type}".encode()
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big") % (
        noise_length - WINDOW_SAMPLES + 1
    )


def reconstruct_base_windows(
    root: Path, base_rows: list[dict[str, Any]]
) -> tuple[np.ndarray, np.ndarray]:
    signals = {
        record: _preprocess(load_mlii(record, root / DEFAULT_RAW_ROOT)) for record in ("118", "119")
    }
    annotations = {
        record: load_annotations(record, root / DEFAULT_RAW_ROOT) for record in ("118", "119")
    }
    windows, labels = [], []
    for row in base_rows:
        record = str(row["base_record_id"])
        source_right = int(row["source_right_edge_index"])
        canonical_end = source_right * SAMPLE_RATE_HZ // EXPECTED_FS_HZ
        clean = np.ascontiguousarray(
            signals[record][canonical_end - WINDOW_SAMPLES : canonical_end], dtype=np.float64
        )
        if clean.shape != (WINDOW_SAMPLES,):
            raise RuntimeError("NOISE_TYPE_BASE_WINDOW_CONFLICT")
        prediction_us = source_right * 1_000_000 // EXPECTED_FS_HZ
        annotation = annotations[record]
        selected = select_annotation_indices_closed(
            np.asarray(annotation.sample), EXPECTED_FS_HZ, prediction_us
        )
        label = summarize_annotations(str(annotation.symbol[index]) for index in selected).label
        if label != int(row["label"]):
            raise RuntimeError("NOISE_TYPE_BASE_WINDOW_CONFLICT")
        windows.append(clean)
        labels.append(label)
    return np.stack(windows), np.asarray(labels, dtype=np.int64)


def infer_noise_matrix(
    root: Path,
    base_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    clean, labels = reconstruct_base_windows(root, base_rows)
    bank, bank_audit = build_noise_bank(root)
    model, _ = load_frozen_model_v1(root)
    calibration = load_cal_v1(root)
    model.eval()

    def infer(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        normalized = np.stack(
            [normalize_window_zscore(row, epsilon=NORMALIZATION_EPSILON) for row in values]
        ).astype(np.float32)
        outputs = []
        with torch.inference_mode():
            for start in range(0, len(normalized), 128):
                tensor = torch.from_numpy(normalized[start : start + 128, None, :])
                outputs.append(model(tensor).numpy()[:, 0])
        logits = np.concatenate(outputs).astype(np.float64)
        probabilities = source_domain_calibrated_probability(logits, calibration)
        return probabilities, apply_operating_threshold(probabilities, calibration)

    clean_probabilities, clean_predictions = infer(clean)
    prediction_rows: list[dict[str, Any]] = []
    fixtures: list[dict[str, Any]] = []
    metrics: list[dict[str, Any]] = []
    for noise_type, source in NOISE_TYPES.items():
        offsets = [
            noise_offset(str(row["base_window_id"]), noise_type, bank[source].size)
            for row in base_rows
        ]
        segments = np.stack([bank[source][offset : offset + WINDOW_SAMPLES] for offset in offsets])
        for snr in SNR_LEVELS:
            noisy_rows, achieved_values = [], []
            for clean_row, segment in zip(clean, segments, strict=True):
                noisy, achieved = mix_noise(clean_row, segment, float(snr))
                noisy_rows.append(noisy)
                achieved_values.append(achieved)
            probabilities, predictions = infer(np.stack(noisy_rows))
            if max(abs(value - snr) for value in achieved_values) > 0.05:
                raise RuntimeError("C031_SNR_FIXTURE_FAILURE")
            for index, base in enumerate(base_rows):
                prediction_rows.append(
                    {
                        "base_window_id": base["base_window_id"],
                        "base_record_id": base["base_record_id"],
                        "source_right_edge_index": base["source_right_edge_index"],
                        "label": int(labels[index]),
                        "noise_type": noise_type,
                        "noise_source": source,
                        "noise_offset": offsets[index],
                        "snr_db": snr,
                        "achieved_snr_db": achieved_values[index],
                        "calibrated_probability": float(probabilities[index]),
                        "thresholded_prediction": int(predictions[index]),
                        "clean_thresholded_prediction": int(clean_predictions[index]),
                    }
                )
            pooled = pooled_binary_metrics(
                labels,
                probabilities,
                predictions,
                np.asarray([row["base_record_id"] for row in base_rows]),
                allow_undefined=False,
            )
            tp = int(np.sum((labels == 1) & (predictions == 1)))
            tn = int(np.sum((labels == 0) & (predictions == 0)))
            fp = int(np.sum((labels == 0) & (predictions == 1)))
            fn = int(np.sum((labels == 1) & (predictions == 0)))
            clean_auprc = pooled_binary_metrics(
                labels,
                clean_probabilities,
                clean_predictions,
                np.asarray([row["base_record_id"] for row in base_rows]),
                allow_undefined=False,
            )["AUPRC"]
            metrics.append(
                {
                    "noise_type": noise_type,
                    "noise_source": source,
                    "snr_db": snr,
                    "windows": len(labels),
                    "positive": int(labels.sum()),
                    "negative": int(len(labels) - labels.sum()),
                    "source_records": 2,
                    "AUPRC": pooled["AUPRC"],
                    "delta_AUPRC_vs_clean": float(pooled["AUPRC"] - clean_auprc),
                    "AUROC": pooled["AUROC"],
                    "F1": pooled["pooled_F1"],
                    "precision": pooled["precision"],
                    "sensitivity": pooled["sensitivity"],
                    "specificity": pooled["specificity"],
                    "TP": tp,
                    "FP": fp,
                    "TN": tn,
                    "FN": fn,
                    "mean_calibrated_probability": float(np.mean(probabilities)),
                    "decision_changes_vs_clean": int(np.sum(predictions != clean_predictions)),
                }
            )
            fixtures.append(
                {
                    "noise_type": noise_type,
                    "source": source,
                    "snr_db": snr,
                    "base_window_id": base_rows[0]["base_window_id"],
                    "offset": offsets[0],
                    "achieved_snr_db": achieved_values[0],
                    "absolute_error_db": abs(achieved_values[0] - snr),
                    "status": "PASS",
                    "source_audit": bank_audit[source],
                }
            )
    return prediction_rows, metrics, fixtures
