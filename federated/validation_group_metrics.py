"""Frozen validation-patient AUPRC semantics for T027 FedProx selection."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import numpy as np
from sklearn.metrics import average_precision_score

METRIC_ID = "VALIDATION_PATIENT_MACRO_AUPRC_V1"
WORST_METRIC_ID = "VALIDATION_PATIENT_WORST_AUPRC_V1"


def validation_patient_metrics(
    labels: np.ndarray,
    probabilities: np.ndarray,
    participant_group_ids: np.ndarray,
    *,
    record_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    y = np.asarray(labels, dtype=np.int64)
    scores = np.asarray(probabilities, dtype=np.float64)
    groups = np.asarray(participant_group_ids, dtype=str)
    if y.shape != scores.shape or y.shape != groups.shape or y.ndim != 1:
        raise ValueError("validation group inputs must be aligned vectors")
    if not np.isfinite(scores).all() or not set(np.unique(y)).issubset({0, 1}):
        raise ValueError("invalid validation labels/probabilities")
    records = np.asarray(list(record_ids), dtype=str) if record_ids is not None else None
    if records is not None and records.shape != y.shape:
        raise ValueError("record IDs must align")
    rows: list[dict[str, Any]] = []
    for group in sorted(set(groups.tolist())):
        mask = groups == group
        positives = int(np.sum(y[mask] == 1))
        negatives = int(np.sum(y[mask] == 0))
        if positives == 0:
            raise RuntimeError(f"FEDPROX_SELECTION_METRIC_UNDEFINED: {group}")
        rows.append(
            {
                "participant_group_id": group,
                "record_ids": sorted(set(records[mask].tolist())) if records is not None else [],
                "windows": int(np.sum(mask)),
                "positives": positives,
                "negatives": negatives,
                "AUPRC": float(average_precision_score(y[mask], scores[mask])),
            }
        )
    values = [float(row["AUPRC"]) for row in rows]
    if not rows:
        raise RuntimeError("FEDPROX_SELECTION_METRIC_UNDEFINED: empty validation")
    return {
        "metric_id": METRIC_ID,
        "worst_metric_id": WORST_METRIC_ID,
        "evaluation_unit": "MITDB_VALIDATION_PARTICIPANT_GROUP",
        "patient_groups": len(rows),
        "per_group": rows,
        "macro_AUPRC": float(np.mean(values)),
        "worst_AUPRC": float(np.min(values)),
        "unweighted": True,
        "validation_patients_are_clients": False,
    }
