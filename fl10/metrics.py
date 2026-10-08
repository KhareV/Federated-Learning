# ruff: noqa: E501
"""Complete metric engine. Starts from final_showcase.metrics (authoritative AUPRC/AUROC/confusion/BCE/threshold logic) and ADDS only the missing quantities.
Undefined values are None with a reason, never zero."""

from __future__ import annotations

from typing import Any

import numpy as np

from final_showcase import metrics as base

THRESHOLD = base.THRESHOLD
HIST_BINS = 20                                   # predeclared: 20 equal-width probability bins on [0, 1]
QUANTILES = (0.05, 0.25, 0.5, 0.75, 0.95)       # predeclared
PAIRED_METRICS = ("AUPRC", "AUROC", "F1", "accuracy", "balanced_accuracy", "recall", "specificity", "precision", "BCE", "Brier")


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.asarray(z, dtype=np.float64)))


def _ratio(n: float, d: float) -> float | None:
    return float(n / d) if d else None


def full_metrics(labels: np.ndarray, logits: np.ndarray) -> dict[str, Any]:
    y = np.asarray(labels).astype(int).reshape(-1)
    z = np.asarray(logits, dtype=np.float64).reshape(-1)
    out = base.classification_metrics(y, z)
    p = _sigmoid(z)
    tp, fp, tn, fn = out["TP"], out["FP"], out["TN"], out["FN"]
    undefined = dict(out["undefined"])
    out["false_discovery_rate"] = _ratio(fp, tp + fp)
    out["false_omission_rate"] = _ratio(fn, tn + fn)
    denom = float(np.sqrt(float(tp + fp) * float(tp + fn) * float(tn + fp) * float(tn + fn)))
    out["MCC"] = float((tp * tn - fp * fn) / denom) if denom else None
    for key, reason in (("false_discovery_rate", "no predicted positives"), ("false_omission_rate", "no predicted negatives"), ("MCC", "a marginal total is zero")):
        if out[key] is None:
            undefined[key] = reason
    out["Brier"] = float(np.mean((p - y) ** 2))
    out["mean_predicted_probability"] = float(p.mean())
    out["mean_score_positive_class"] = float(p[y == 1].mean()) if (y == 1).any() else None
    out["mean_score_negative_class"] = float(p[y == 0].mean()) if (y == 0).any() else None
    out["score_min"], out["score_max"] = float(p.min()), float(p.max())
    out["score_quantiles"] = {str(q): float(np.quantile(p, q)) for q in QUANTILES}
    out["total_predictions"] = int(y.size)
    out["predicted_positives"], out["predicted_negatives"] = tp + fp, tn + fn
    edges = np.linspace(0.0, 1.0, HIST_BINS + 1)
    out["histogram"] = {"edges": [float(e) for e in edges], "positive": np.histogram(p[y == 1], bins=edges)[0].tolist(), "negative": np.histogram(p[y == 0], bins=edges)[0].tolist()}
    out["undefined"] = undefined
    return out


def participant_metrics(owners: np.ndarray, labels: np.ndarray, logits: np.ndarray) -> dict[str, Any]:
    rows = {}
    for pid in sorted(set(np.asarray(owners).tolist())):
        m = np.asarray(owners) == pid
        rows[str(pid)] = full_metrics(np.asarray(labels)[m], np.asarray(logits)[m])
    macro = base.participant_macro_f1(owners, labels, logits)
    return {"per_participant": rows, "participant_macro_F1": macro["value"], "participants_defined": macro["participants_defined"], "participants_undefined": macro["participants_undefined"]}


def _pm(y: np.ndarray, z: np.ndarray) -> dict[str, float | None]:
    r = base.classification_metrics(y, z)
    r["Brier"] = float(np.mean((_sigmoid(z) - y) ** 2))
    return {m: r[m] for m in PAIRED_METRICS}


def paired_cluster_bootstrap(owners: np.ndarray, labels: np.ndarray, logits_a: np.ndarray, logits_b: np.ndarray, *, replicates: int, seed: int) -> dict[str, Any]:
    """Paired participant-cluster percentile bootstrap: ONE cluster draw per replicate, applied to both states (A = comparator, B = endpoint); difference = B - A.
    Replicates where a metric is undefined for either state are counted as invalid and are not redrawn."""
    owners = np.asarray(owners)
    ids = sorted(set(owners.tolist()))
    index = {i: np.flatnonzero(owners == i) for i in ids}
    rng = np.random.default_rng(seed)
    y = np.asarray(labels).astype(int)
    draws = {m: {"A": [], "B": [], "D": []} for m in PAIRED_METRICS}
    invalid = dict.fromkeys(PAIRED_METRICS, 0)
    for _ in range(replicates):
        chosen = rng.choice(len(ids), size=len(ids), replace=True)
        rows = np.concatenate([index[ids[i]] for i in chosen])
        ma, mb = _pm(y[rows], logits_a[rows]), _pm(y[rows], logits_b[rows])
        for m in PAIRED_METRICS:
            if ma[m] is None or mb[m] is None:
                invalid[m] += 1
            else:
                draws[m]["A"].append(ma[m])
                draws[m]["B"].append(mb[m])
                draws[m]["D"].append(mb[m] - ma[m])
    point_a, point_b = _pm(y, np.asarray(logits_a)), _pm(y, np.asarray(logits_b))

    def interval(values: list[float]) -> dict[str, Any]:
        v = np.asarray(values)
        return {"lower": float(np.percentile(v, 2.5)) if v.size else None, "upper": float(np.percentile(v, 97.5)) if v.size else None, "valid_replicates": int(v.size)}

    out: dict[str, Any] = {"clusters": len(ids), "replicates": replicates, "seed": seed, "rng": "numpy PCG64 default_rng", "method": "paired participant-cluster percentile bootstrap, nominal 95%, difference = B - A",
                           "multiplicity": "NONE - 10 metrics are reported; no multiplicity adjustment and no significance claim", "metrics": {}}
    for m in PAIRED_METRICS:
        pa, pb = point_a[m], point_b[m]
        out["metrics"][m] = {"A_point": pa, "B_point": pb, "difference_point": (pb - pa) if pa is not None and pb is not None else None, "A_interval": interval(draws[m]["A"]),
                             "B_interval": interval(draws[m]["B"]), "difference_interval": interval(draws[m]["D"]), "invalid_replicates": invalid[m]}
    return out
