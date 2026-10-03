"""V2-007 pure statistical core: metric pooling, patient-cluster bootstrap replication,
finalist-comparison rule (Section 23), and promotion rule (Section 24/41/42).

Pure functions only -- no file I/O, no waveform access -- so they can be synthetically
unit-tested with hand-crafted inputs BEFORE the first V2-007 fit (per Section 26's
requirement that all decision-rule code exist and pass tests before any neural fit), and
reused unchanged by the real aggregate/bootstrap/decide scripts once predictions exist.
scripts/generate_v2_007_evidence.py's independent reverification deliberately does NOT import
this module -- it reimplements the same formulas from scratch to avoid self-grading.
"""

from __future__ import annotations

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score

PROMOTION_AUPRC_THRESHOLD = 0.646


def pooled_metrics(labels: np.ndarray, probabilities: np.ndarray) -> tuple[float, float | None]:
    labels = np.asarray(labels)
    probabilities = np.asarray(probabilities)
    auprc = float(average_precision_score(labels, probabilities))
    auroc = (
        float(roc_auc_score(labels, probabilities)) if len(np.unique(labels)) == 2 else None
    )
    return auprc, auroc


def three_seed_stats(values: dict[int, float]) -> dict:
    if len(values) != 3:
        raise ValueError(f"three_seed_stats requires exactly 3 seed values, got {len(values)}")
    arr = np.array(list(values.values()), dtype=np.float64)
    return {
        "mean": float(np.mean(arr)),
        "sd": float(np.std(arr, ddof=1)),
        "min": float(np.min(arr)),
    }


def bootstrap_replicate_pooled(
    draw_row: np.ndarray,
    group_order: list[str],
    labels_by_group: dict[str, np.ndarray],
    probs_by_group: dict[str, np.ndarray],
) -> tuple[np.ndarray, np.ndarray]:
    """One bootstrap replicate: draw_row holds group-INDICES (into group_order), with
    repetition/multiplicity preserved (never deduplicated into a set). Returns the pooled
    (labels, probabilities) arrays formed by concatenating each sampled group's rows once per
    occurrence."""
    label_chunks = []
    prob_chunks = []
    for idx in draw_row:
        group = group_order[int(idx)]
        label_chunks.append(labels_by_group[group])
        prob_chunks.append(probs_by_group[group])
    return np.concatenate(label_chunks), np.concatenate(prob_chunks)


def bootstrap_auprc_distribution(
    draws: np.ndarray,
    group_order: list[str],
    labels_by_group: dict[str, np.ndarray],
    probs_by_group: dict[str, np.ndarray],
) -> np.ndarray:
    """Returns one AUPRC value per replicate (shape (B,)); degenerate replicates (a single
    class present in the pooled sample) are recorded as NaN, never redrawn."""
    b = draws.shape[0]
    out = np.full(b, np.nan, dtype=np.float64)
    for i in range(b):
        labels, probs = bootstrap_replicate_pooled(
            draws[i], group_order, labels_by_group, probs_by_group
        )
        if len(np.unique(labels)) < 2:
            continue
        out[i] = float(average_precision_score(labels, probs))
    return out


def three_seed_mean_replicate_distribution(
    per_seed_distributions: dict[int, np.ndarray],
) -> np.ndarray:
    """Element-wise mean, within each replicate index, of the three seed-level AUPRC
    distributions. NaN in any seed at a given replicate propagates to NaN (never silently
    dropped/imputed)."""
    if len(per_seed_distributions) != 3:
        raise ValueError("requires exactly 3 seed-level distributions")
    stacked = np.stack(list(per_seed_distributions.values()), axis=0)
    return np.mean(stacked, axis=0)


def percentile_ci(
    values: np.ndarray, *, lower: float = 0.025, upper: float = 0.975
) -> dict:
    values = np.asarray(values, dtype=np.float64)
    valid = values[~np.isnan(values)]
    lo = float(np.percentile(valid, lower * 100, method="linear")) if len(valid) else float("nan")
    hi = float(np.percentile(valid, upper * 100, method="linear")) if len(valid) else float("nan")
    return {
        "lower": lo,
        "upper": hi,
        "valid_count": len(valid),
        "invalid_count": int(len(values) - len(valid)),
    }


def sample_sd_ddof1(values: np.ndarray) -> float:
    valid = np.asarray(values, dtype=np.float64)
    valid = valid[~np.isnan(valid)]
    return float(np.std(valid, ddof=1))


def finalist_comparison(
    *,
    a_three_seed_mean: float,
    b_three_seed_mean: float,
    a_rep_mean_distribution: np.ndarray,
    b_rep_mean_distribution: np.ndarray,
    a_params: int,
    b_params: int,
    a_seed_sd: float,
    b_seed_sd: float,
    a_config_id: str,
    b_config_id: str,
) -> dict:
    """V2-007 Section 23 finalist-comparison rule, frozen before results exist."""
    delta_b_minus_a = b_three_seed_mean - a_three_seed_mean
    delta_rep = b_rep_mean_distribution - a_rep_mean_distribution
    se = sample_sd_ddof1(delta_rep)
    within_one_se = abs(delta_b_minus_a) <= se

    tie_break_path = None
    if within_one_se:
        if a_params < b_params:
            selected, tie_break_path = "A", "fewer_trainable_parameters"
        elif b_params < a_params:
            selected, tie_break_path = "B", "fewer_trainable_parameters"
        elif a_seed_sd < b_seed_sd:
            selected, tie_break_path = "A", "lower_three_seed_AUPRC_sample_SD"
        elif b_seed_sd < a_seed_sd:
            selected, tie_break_path = "B", "lower_three_seed_AUPRC_sample_SD"
        elif a_config_id <= b_config_id:
            selected, tie_break_path = "A", "lexicographically_smaller_config_id"
        else:
            selected, tie_break_path = "B", "lexicographically_smaller_config_id"
    else:
        selected = "B" if b_three_seed_mean > a_three_seed_mean else "A"

    return {
        "delta_b_minus_a": delta_b_minus_a,
        "bootstrap_se": se,
        "within_one_se": within_one_se,
        "tie_break_path": tie_break_path,
        "selected": selected,
    }


def promotion_decision(
    *,
    selected_three_seed_mean_auprc: float,
    release_delta_ci: dict,
    three_seed_delta_ci: dict,
) -> dict:
    """V2-007 Section 24/42 promotion rule, frozen before results exist."""
    criterion_a = selected_three_seed_mean_auprc > PROMOTION_AUPRC_THRESHOLD
    criterion_b1 = release_delta_ci["lower"] > 0
    criterion_b2 = three_seed_delta_ci["lower"] > 0
    promotion_eligible = criterion_a and criterion_b1 and criterion_b2

    if promotion_eligible:
        decision = "MODEL_V2_PROMOTION_ELIGIBLE"
    elif not criterion_a and criterion_b1 and criterion_b2:
        decision = "MODEL_V2_NOT_PROMOTED_AUPRC_THRESHOLD"
    elif criterion_a and not criterion_b1 and criterion_b2:
        decision = "MODEL_V2_NOT_PROMOTED_RELEASE_CI"
    elif criterion_a and criterion_b1 and not criterion_b2:
        decision = "MODEL_V2_NOT_PROMOTED_THREE_SEED_CI"
    else:
        decision = "MODEL_V2_NOT_PROMOTED_MULTIPLE_CRITERIA"

    return {
        "criterion_a_mean_auprc_gt_0_646": criterion_a,
        "criterion_b1_release_delta_lower_ci_gt_0": criterion_b1,
        "criterion_b2_three_seed_mean_delta_lower_ci_gt_0": criterion_b2,
        "promotion_eligible": promotion_eligible,
        "decision": decision,
    }


__all__ = [
    "PROMOTION_AUPRC_THRESHOLD",
    "bootstrap_auprc_distribution",
    "bootstrap_replicate_pooled",
    "finalist_comparison",
    "percentile_ci",
    "pooled_metrics",
    "promotion_decision",
    "sample_sd_ddof1",
    "three_seed_mean_replicate_distribution",
    "three_seed_stats",
]
