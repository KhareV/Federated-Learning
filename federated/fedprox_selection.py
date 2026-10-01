"""Predeclared deterministic FedProx mu selection."""

from __future__ import annotations

from typing import Any

CANDIDATES = (0.001, 0.01, 0.1)
GUARDRAIL_DEGRADATION = 0.05


def select_mu(rows: list[dict[str, Any]], baseline_worst: float) -> dict[str, Any]:
    if tuple(float(row["mu"]) for row in rows) != CANDIDATES:
        raise ValueError("FedProx candidate set/order mismatch")
    threshold = baseline_worst - GUARDRAIL_DEGRADATION
    evaluated = []
    for row in rows:
        item = dict(row)
        item["worst_guardrail_threshold"] = threshold
        worst = float(row["validation_patient_worst_AUPRC"])
        item["guardrail_pass"] = worst > threshold or abs(worst - threshold) <= 1e-12
        evaluated.append(item)
    eligible = [row for row in evaluated if row["guardrail_pass"]]
    if not eligible:
        raise RuntimeError("FEDPROX_NO_ACCEPTABLE_MU")
    ranked = sorted(
        eligible,
        key=lambda row: (
            -round(float(row["validation_patient_macro_AUPRC"]), 12),
            -float(row["validation_patient_worst_AUPRC"]),
            -float(row["best_global_validation_AUPRC"]),
            float(row["mu"]),
        ),
    )
    return {
        "guardrail_absolute_degradation": GUARDRAIL_DEGRADATION,
        "guardrail_threshold": threshold,
        "eligible_candidates": [float(row["mu"]) for row in ranked],
        "ranking": [float(row["mu"]) for row in ranked],
        "selected_mu": float(ranked[0]["mu"]),
        "evaluated_candidates": evaluated,
        "primary_metric": "VALIDATION_PATIENT_MACRO_AUPRC_V1",
        "tie_policy": ["higher_worst", "higher_global", "smaller_mu"],
    }
