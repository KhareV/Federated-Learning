"""Deterministic patient-cluster bootstrap with explicit draw multiplicity."""

from __future__ import annotations

from typing import Any

import numpy as np

from evaluation.metrics import METRIC_NAMES, patient_f1_values, pooled_binary_metrics

BOOTSTRAP_METHOD_ID = "PATIENT_CLUSTER_PERCENTILE_95_V1"


class BootstrapError(ValueError):
    """Raised when cluster-bootstrap inputs or configuration are invalid."""


def generate_patient_draws(
    patient_ids: np.ndarray, replicates: int, seed: int
) -> tuple[np.ndarray, np.ndarray]:
    patients = np.asarray(sorted(set(np.asarray(patient_ids, dtype=str).tolist())), dtype=str)
    if patients.size == 0:
        raise BootstrapError("NO_PATIENT_CLUSTERS")
    if replicates != 2000:
        raise BootstrapError("BOOTSTRAP_REPLICATES_MUST_EQUAL_2000")
    rng = np.random.Generator(np.random.PCG64(seed))
    draws = rng.integers(0, patients.size, size=(replicates, patients.size), dtype=np.int64)
    return patients, draws


def expand_cluster_draw(
    patient_ids: np.ndarray, patients: np.ndarray, draw: np.ndarray
) -> np.ndarray:
    row_patients = np.asarray(patient_ids, dtype=str)
    blocks = [np.flatnonzero(row_patients == patients[int(index)]) for index in draw]
    if any(block.size == 0 for block in blocks):
        raise BootstrapError("UNKNOWN_PATIENT_CLUSTER")
    return np.concatenate(blocks)


def bootstrap_replicates(
    patient_ids: np.ndarray,
    labels: np.ndarray,
    probabilities: np.ndarray,
    predictions: np.ndarray,
    *,
    replicates: int,
    seed: int,
    draws: np.ndarray | None = None,
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    row_patients = np.asarray(patient_ids, dtype=str)
    targets = np.asarray(labels, dtype=np.int64)
    scores = np.asarray(probabilities, dtype=np.float64)
    predicted = np.asarray(predictions, dtype=np.int64)
    if not (row_patients.shape == targets.shape == scores.shape == predicted.shape):
        raise BootstrapError("BOOTSTRAP_INPUT_SHAPE_MISMATCH")
    patients, generated = generate_patient_draws(row_patients, replicates, seed)
    draw_matrix = generated if draws is None else np.asarray(draws, dtype=np.int64)
    if draw_matrix.shape != (replicates, patients.size):
        raise BootstrapError("BOOTSTRAP_DRAW_SHAPE_MISMATCH")
    if np.any(draw_matrix < 0) or np.any(draw_matrix >= patients.size):
        raise BootstrapError("BOOTSTRAP_DRAW_INDEX_OUT_OF_RANGE")
    per_patient_f1 = patient_f1_values(row_patients, targets, predicted)
    rows: list[dict[str, Any]] = []
    for replicate_index, draw in enumerate(draw_matrix):
        expanded = expand_cluster_draw(row_patients, patients, draw)
        metrics = pooled_binary_metrics(
            targets[expanded], scores[expanded], predicted[expanded], row_patients[expanded],
            allow_undefined=True,
        )
        # Equal slot weighting with multiplicity; never deduplicate the sampled patient draw.
        metrics["patient_macro_F1"] = float(
            np.mean([per_patient_f1[patients[int(index)]] for index in draw])
        )
        rows.append(
            {
                "replicate_index": replicate_index,
                "sampled_patient_slots": int(draw.size),
                "unique_patient_count": int(np.unique(draw).size),
                **{name: metrics[name] for name in METRIC_NAMES},
            }
        )
    return draw_matrix, rows


def percentile_summary(
    point_metrics: dict[str, Any], replicate_rows: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    if len(replicate_rows) != 2000:
        raise BootstrapError("BOOTSTRAP_REPLICATES_MUST_EQUAL_2000")
    summary: dict[str, dict[str, Any]] = {}
    for name in METRIC_NAMES:
        values = np.asarray(
            [np.nan if row[name] is None else float(row[name]) for row in replicate_rows],
            dtype=np.float64,
        )
        finite = values[np.isfinite(values)]
        if finite.size == 0:
            raise BootstrapError(f"BOOTSTRAP_METRIC_DEGENERACY: {name}")
        summary[name] = {
            "point_estimate": float(point_metrics[name]),
            "ci_lower_95": float(np.quantile(finite, 0.025, method="linear")),
            "ci_upper_95": float(np.quantile(finite, 0.975, method="linear")),
            "valid_replicates": int(finite.size),
            "invalid_replicates": int(values.size - finite.size),
        }
    return summary
