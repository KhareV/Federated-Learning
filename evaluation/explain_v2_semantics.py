"""EXPLAINABILITY_V2_COMPLETENESS_SEMANTICS_V2: completeness is DIAGNOSTIC METADATA.

The locked v2.2 contract requires the IG completeness/convergence delta to be recorded as
diagnostic metadata and imposes no numeric acceptance threshold. The absolute-or-relative 1e-3
rule used at METHOD_COMMIT was a prompt/V1-implementation heuristic; it is retained here only as
a descriptive historical label and can never gate anything. Attribution computation itself
(evaluation.explain_v2 / evaluation.explain) is untouched.
"""

from __future__ import annotations

from typing import Any

from evaluation.explain_v2 import completeness as _historical_rule

SEMANTICS_ID = "EXPLAINABILITY_V2_COMPLETENESS_SEMANTICS_V2"
HEURISTIC_ABSOLUTE = 1e-3
HEURISTIC_RELATIVE = 1e-3
NUMERICAL_GATE = "NONE"
LOCKED_STATUS = "DIAGNOSTIC_RECORDED"
EXCEEDS = "EXCEEDS_HISTORICAL_1E3_HEURISTIC"
WITHIN = "WITHIN_HISTORICAL_1E3_HEURISTIC"


def completeness_diagnostic(
    output: float, baseline_output: float, attribution_sum: float
) -> dict[str, Any]:
    """Always returns the residuals; never a pass/fail verdict that can gate V2G10."""
    base = _historical_rule(attribution_sum, output, baseline_output)
    within = bool(base["passed"])
    return {
        "completeness_output_difference": base["output_difference"],
        "completeness_signed_delta": base["signed_delta"],
        "completeness_absolute_delta": base["absolute_delta"],
        "completeness_relative_delta": base["relative_delta"],
        "historical_v1_style_1e3_heuristic": "PASS" if within else "EXCEEDS_HEURISTIC",
        "historical_heuristic_label": WITHIN if within else EXCEEDS,
        "locked_v2_2_explainability_status": LOCKED_STATUS,
        "numerical_completeness_gate": NUMERICAL_GATE,
    }


def gates_v2g10() -> bool:
    return False


__all__ = [
    "EXCEEDS", "LOCKED_STATUS", "NUMERICAL_GATE", "SEMANTICS_ID", "WITHIN",
    "completeness_diagnostic", "gates_v2g10",
]
