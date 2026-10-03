"""V2-010 shared second-look library: loaders, V2 inference, and closure audits for the
three post-freeze comparative datasets (INTERNAL_TEST, INCART, NSTDB). Reuses every
model-agnostic I/O / windowing / preprocessing function from the frozen V1 evaluation
modules UNCHANGED (never redefines windowing, quality, or preprocessing logic); only the
model (MODEL_V2_FINAL) and calibration (CAL_V2) are new. Never imports or calls any
MODEL_V1-specific inference function (load_frozen_model_v1, extract_logits_once,
evaluation.external_incart.run_external_once's model, evaluation.noise.infer_rows).
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import numpy as np
import torch

from datasets.incart import DEFAULT_RAW_ROOT
from evaluation.calibration import (
    apply_operating_threshold,
    raw_probability_from_logit,
    source_domain_calibrated_probability,
)
from evaluation.external_incart import _infer_windows, _record_windows, load_patient_map
from evaluation.internal_test import InternalPopulation, load_internal_population
from evaluation.noise import (
    EXPECTED_RECORDS,
    StressWindow,
    build_stress_windows,
    fixed_paired_population,
)
from models.cal_v2_verify import load_cal_v2
from models.model_v2_final_freeze import load_model_v2_final
from nhm.hashing import hash_file
from preprocessing.windowing import NORMALIZATION_EPSILON, normalize_window_zscore

ROOT = Path(__file__).resolve().parents[1]


class V2SecondLookError(RuntimeError):
    """Raised for any V2-010 closure, scope, or integrity failure."""


# Shared, single-source-of-truth guard-precondition upstream maps: used identically by
# scripts/freeze_v2_010_method.py (to arm) and each run_v2_010_*.py session script (to
# observe) so the two can never silently drift.
COMMON_UPSTREAM = {
    "model_v2_final_checkpoint_sha256": "checkpoints/MODEL_V2_FINAL.pt",
    "model_v2_final_manifest_sha256": "checkpoints/MODEL_V2_FINAL.manifest.json",
    "model_v2_final_frozen_config_sha256": "configs/model_v2_final_frozen.yaml",
    "cal_v2_sha256": "artifacts/CAL_V2.json",
    "protocol_v3_lock_sha256": "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V3.lock.json",
}

DATASET_UPSTREAM = {
    "INTERNAL_TEST": {
        "split_sha256": "manifests/splits/MITDB_SPLIT_V1.csv",
        "window_manifest_sha256": "manifests/windows/MITDB_WINDOWS_V1.csv",
        "preproc_lock_sha256": "manifests/preprocessing/PREPROC_V1.lock.json",
        "v1_prediction_table_sha256": "reports/internal_test_predictions.csv",
    },
    "INCART": {
        "patient_map_sha256": "manifests/datasets/incart_patient_map.csv",
        "lead_ii_records_sha256": "manifests/datasets/incart_lead_ii_records.csv",
        "incart_dataset_lock_sha256": "manifests/datasets/incart_v1.yaml",
        "v1_prediction_table_sha256": "reports/external_incart_predictions.csv",
    },
    "NSTDB": {
        "nstdb_records_manifest_sha256": "manifests/datasets/nstdb_records.csv",
        "nstdb_dataset_lock_sha256": "manifests/datasets/nstdb_v1.yaml",
        "v1_prediction_table_sha256": "reports/t019/nstdb_predictions.csv",
    },
}


def observed_preconditions(root: Path, dataset: str) -> dict[str, str]:
    common = {key: hash_file(root / path) for key, path in COMMON_UPSTREAM.items()}
    specific = {key: hash_file(root / path) for key, path in DATASET_UPSTREAM[dataset].items()}
    return {**common, **specific}


# ---------------------------------------------------------------------------
# INTERNAL_TEST
# ---------------------------------------------------------------------------


def load_internal_test_population(root: Path = ROOT) -> InternalPopulation:
    """Reuses evaluation.internal_test.load_internal_population unchanged -- generic I/O,
    never model-specific."""
    return load_internal_population(root)


def extract_logits_v2_internal(
    population: InternalPopulation, root: Path, batch_size: int
) -> np.ndarray:
    model, _ = load_model_v2_final(root)
    before = copy.deepcopy(model.state_dict())
    normalized = np.stack(
        [
            normalize_window_zscore(row, epsilon=NORMALIZATION_EPSILON)
            for row in population.waveforms
        ]
    ).astype(np.float32)
    output: list[np.ndarray] = []
    model.eval()
    with torch.inference_mode():
        for start in range(0, len(normalized), batch_size):
            batch = torch.from_numpy(normalized[start : start + batch_size, None, :])
            output.append(model(batch).cpu().numpy()[:, 0])
    if any(not torch.equal(before[key], model.state_dict()[key]) for key in before):
        raise V2SecondLookError("MODEL_V2_FINAL_STATE_MUTATED_DURING_INTERNAL_TEST")
    return np.concatenate(output).astype(np.float64)


# ---------------------------------------------------------------------------
# INCART
# ---------------------------------------------------------------------------


def incart_patient_map(root: Path = ROOT) -> dict[str, str]:
    return load_patient_map(root)


def extract_incart_v2_rows(root: Path, batch_size: int) -> tuple[list[dict[str, Any]], list[str]]:
    """Reuses evaluation.external_incart._record_windows (model-agnostic window/annotation
    extraction) and _infer_windows (takes the model as a parameter), substituting
    MODEL_V2_FINAL for MODEL_V1. Never calls run_external_once or any MODEL_V1 loader."""
    patient_map = incart_patient_map(root)
    model, _ = load_model_v2_final(root)
    model.eval()
    before = copy.deepcopy(model.state_dict())
    manifest_rows: list[dict[str, Any]] = []
    all_logits: list[np.ndarray] = []
    accessed_paths: list[str] = []
    with torch.inference_mode():
        for record_id in sorted(patient_map):
            rows, waveforms = _record_windows(record_id, patient_map[record_id], root)
            accessed_paths.extend(
                [
                    str(DEFAULT_RAW_ROOT / f"{record_id}.hea"),
                    str(DEFAULT_RAW_ROOT / f"{record_id}.dat"),
                    str(DEFAULT_RAW_ROOT / f"{record_id}.atr"),
                ]
            )
            eligible_rows = [row for row in rows if row["core_eligible"] == "TRUE"]
            logits = _infer_windows(model, waveforms, batch_size)
            if len(eligible_rows) != len(logits):
                raise V2SecondLookError("INCART_V2_ELIGIBLE_WAVEFORM_CLOSURE_FAILURE")
            for row, logit in zip(eligible_rows, logits, strict=True):
                manifest_rows.append(row)
                all_logits.append(logit)
    if any(not torch.equal(before[key], model.state_dict()[key]) for key in before):
        raise V2SecondLookError("MODEL_V2_FINAL_STATE_MUTATED_DURING_INCART")
    return (
        [
            {**row, "raw_logit": float(logit)}
            for row, logit in zip(manifest_rows, all_logits, strict=True)
        ],
        accessed_paths,
    )


# ---------------------------------------------------------------------------
# NSTDB
# ---------------------------------------------------------------------------


def build_all_nstdb_stress_windows(root: Path = ROOT) -> list[StressWindow]:
    return [window for record in EXPECTED_RECORDS for window in build_stress_windows(record, root)]


def nstdb_paired_population(root: Path = ROOT) -> list[StressWindow]:
    return fixed_paired_population(build_all_nstdb_stress_windows(root))


def infer_rows_v2_nstdb(
    windows: list[StressWindow], root: Path, batch_size: int
) -> list[dict[str, Any]]:
    """Mirrors evaluation.noise.infer_rows exactly, substituting MODEL_V2_FINAL/CAL_V2 for
    MODEL_V1/CAL_V1. Never calls evaluation.noise.infer_rows itself."""
    model, metadata = load_model_v2_final(root)
    cal = load_cal_v2(root)
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
        raise V2SecondLookError("MODEL_V2_FINAL_STATE_MUTATED_DURING_NSTDB")
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
                "MODEL_V2_FINAL_sha256": metadata["checkpoint_sha256"],
                "CAL_V2_sha256": hash_file(root / "artifacts/CAL_V2.json"),
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Frozen V1 prediction-table readers (never recompute, read only)
# ---------------------------------------------------------------------------


def read_v1_internal_predictions(root: Path = ROOT) -> list[dict[str, str]]:
    import csv

    with (root / "reports/internal_test_predictions.csv").open(newline="", encoding="utf-8") as h:
        return list(csv.DictReader(h))


def read_v1_incart_predictions(root: Path = ROOT) -> list[dict[str, str]]:
    import csv

    with (root / "reports/external_incart_predictions.csv").open(
        newline="", encoding="utf-8"
    ) as h:
        return list(csv.DictReader(h))


def read_v1_nstdb_predictions(root: Path = ROOT) -> list[dict[str, str]]:
    import csv

    with (root / "reports/t019/nstdb_predictions.csv").open(newline="", encoding="utf-8") as h:
        return list(csv.DictReader(h))


__all__ = [
    "V2SecondLookError",
    "build_all_nstdb_stress_windows",
    "extract_incart_v2_rows",
    "extract_logits_v2_internal",
    "incart_patient_map",
    "infer_rows_v2_nstdb",
    "load_internal_test_population",
    "nstdb_paired_population",
    "read_v1_incart_predictions",
    "read_v1_internal_predictions",
    "read_v1_nstdb_predictions",
]
