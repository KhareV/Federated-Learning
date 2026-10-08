# ruff: noqa: E501
"""Binary classification metrics for the synthetic engineering lane. Every metric that is not mathematically defined returns None with a reason.

AUPRC is scikit-learn ``average_precision_score`` (step-wise, non-interpolated: sum over thresholds of (R_n - R_{n-1}) * P_n).
The decision rule is fixed in the protocol: positive iff raw sigmoid probability >= 0.5 (no calibration, no tuning)."""

from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.metrics import (
    average_precision_score,
    precision_recall_curve,
    roc_auc_score,
    roc_curve,
)

THRESHOLD = 0.5
PRIMARY = ("AUPRC", "AUROC", "F1", "accuracy", "precision", "recall", "specificity", "balanced_accuracy")


def _ratio(numerator: float, denominator: float) -> float | None:
    return float(numerator / denominator) if denominator else None


def bce(labels: np.ndarray, logits: np.ndarray) -> float:
    """Mean unweighted binary cross-entropy from raw logits (numerically stable)."""
    z, y = np.asarray(logits, dtype=np.float64), np.asarray(labels, dtype=np.float64)
    return float(np.mean(np.maximum(z, 0) - z * y + np.log1p(np.exp(-np.abs(z)))))


def classification_metrics(labels: np.ndarray, logits: np.ndarray) -> dict[str, Any]:
    y = np.asarray(labels).astype(int).reshape(-1)
    z = np.asarray(logits, dtype=np.float64).reshape(-1)
    if y.shape != z.shape or y.size == 0 or not np.isfinite(z).all() or not np.isin(y, (0, 1)).all():
        raise ValueError("METRIC_INPUT_INVALID")
    p = 1.0 / (1.0 + np.exp(-z))
    pred = (p >= THRESHOLD).astype(int)
    tp, fp = int(np.sum((y == 1) & (pred == 1))), int(np.sum((y == 0) & (pred == 1)))
    tn, fn = int(np.sum((y == 0) & (pred == 0))), int(np.sum((y == 1) & (pred == 0)))
    positives, negatives = tp + fn, tn + fp
    both = positives > 0 and negatives > 0
    recall, specificity = _ratio(tp, positives), _ratio(tn, negatives)
    undefined: dict[str, str] = {}
    out: dict[str, Any] = {
        "windows": int(y.size), "positives": positives, "negatives": negatives, "prevalence": float(positives / y.size),
        "TP": tp, "FP": fp, "TN": tn, "FN": fn,
        "AUPRC": float(average_precision_score(y, p)) if both else None, "AUROC": float(roc_auc_score(y, p)) if both else None,
        "F1": _ratio(2 * tp, 2 * tp + fp + fn), "accuracy": float((tp + tn) / y.size), "precision": _ratio(tp, tp + fp),
        "recall": recall, "specificity": specificity,
        "balanced_accuracy": float((recall + specificity) / 2) if recall is not None and specificity is not None else None,
        "false_positive_rate": _ratio(fp, negatives), "false_negative_rate": _ratio(fn, positives), "negative_predictive_value": _ratio(tn, tn + fn),
        "BCE": bce(y, z), "threshold": THRESHOLD,
    }
    reasons = {"AUPRC": "needs both classes", "AUROC": "needs both classes", "F1": "no positive windows and no positive predictions (2TP+FP+FN = 0)",
               "precision": "no positive predictions (TP+FP = 0)", "recall": "no positive windows", "specificity": "no negative windows",
               "balanced_accuracy": "recall or specificity undefined", "false_positive_rate": "no negative windows", "false_negative_rate": "no positive windows",
               "negative_predictive_value": "no negative predictions (TN+FN = 0)"}
    for key, reason in reasons.items():
        if out[key] is None:
            undefined[key] = reason
    out["undefined"] = undefined
    return out


def participant_macro_f1(participants: np.ndarray, labels: np.ndarray, logits: np.ndarray) -> dict[str, Any]:
    """Mean of per-participant F1 over participants whose F1 is defined; the count of excluded participants is reported."""
    values: dict[str, float | None] = {}
    for pid in sorted(set(np.asarray(participants).tolist())):
        mask = np.asarray(participants) == pid
        values[str(pid)] = classification_metrics(np.asarray(labels)[mask], np.asarray(logits)[mask])["F1"]
    defined = [v for v in values.values() if v is not None]
    return {"value": float(np.mean(defined)) if defined else None, "participants_defined": len(defined), "participants_undefined": len(values) - len(defined), "per_participant": values}


def curves(labels: np.ndarray, logits: np.ndarray) -> dict[str, Any] | None:
    y = np.asarray(labels).astype(int)
    if len(set(y.tolist())) < 2:
        return None
    p = 1.0 / (1.0 + np.exp(-np.asarray(logits, dtype=np.float64)))
    precision, recall, _ = precision_recall_curve(y, p)
    fpr, tpr, _ = roc_curve(y, p)
    return {"pr": [[float(r), float(q)] for r, q in zip(recall, precision, strict=True)], "roc": [[float(a), float(b)] for a, b in zip(fpr, tpr, strict=True)]}


def cluster_bootstrap(participants: np.ndarray, labels: np.ndarray, logits: np.ndarray, *, replicates: int, seed: int, metrics: tuple[str, ...] = ("AUPRC", "AUROC", "F1", "accuracy", "balanced_accuracy")) -> dict[str, Any]:
    """Participant-cluster percentile bootstrap (multiplicity preserved: a participant drawn k times contributes k copies). Degenerate replicates are counted, never redrawn."""
    ids = sorted(set(np.asarray(participants).tolist()))
    index = {pid: np.flatnonzero(np.asarray(participants) == pid) for pid in ids}
    rng = np.random.default_rng(seed)
    draws: dict[str, list[float]] = {m: [] for m in metrics}
    invalid = {m: 0 for m in metrics}
    for _ in range(replicates):
        chosen = rng.choice(len(ids), size=len(ids), replace=True)
        rows = np.concatenate([index[ids[i]] for i in chosen])
        result = classification_metrics(np.asarray(labels)[rows], np.asarray(logits)[rows])
        for m in metrics:
            if result[m] is None:
                invalid[m] += 1
            else:
                draws[m].append(result[m])
    out: dict[str, Any] = {"clusters": len(ids), "replicates": replicates, "seed": seed, "rng": "numpy PCG64 default_rng", "method": "participant-cluster percentile bootstrap, nominal 95%"}
    for m in metrics:
        values = np.asarray(draws[m])
        out[m] = {"lower": float(np.percentile(values, 2.5)) if values.size else None, "upper": float(np.percentile(values, 97.5)) if values.size else None,
                  "valid_replicates": int(values.size), "invalid_replicates": invalid[m]}
    return out
