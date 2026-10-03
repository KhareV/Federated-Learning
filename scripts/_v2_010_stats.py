"""V2-010 pure statistical core: paired-bootstrap delta/CI, the two predeclared zero-margin
runtime-acceptance guards, and the final runtime-acceptance decision rule. Every function here
operates on plain arrays/dicts only -- no file I/O, no model/guard access -- so it is fully
synthetic-testable before any V2-010 waveform access, per the phase's pre-access-freeze
requirement. Frozen at METHOD_COMMIT; never changed after any dataset is opened.
"""

from __future__ import annotations

from typing import Any

import numpy as np

FLOATING_TOLERANCE = 1e-12
SNR_LEVELS_DB = (24, 18, 12, 6, 0, -6)


class V2010StatsError(ValueError):
    """Raised for malformed statistical inputs."""


def paired_bootstrap_delta(
    v1_replicate_rows: list[dict[str, Any]],
    v2_replicate_rows: list[dict[str, Any]],
    metric_name: str,
) -> np.ndarray:
    """Per-replicate delta = V2[metric] - V1[metric], paired strictly by replicate_index
    (both tables must share the identical frozen draw matrix -- same length, same order)."""
    if len(v1_replicate_rows) != len(v2_replicate_rows):
        raise V2010StatsError("PAIRED_BOOTSTRAP_REPLICATE_COUNT_MISMATCH")
    deltas = []
    for v1_row, v2_row in zip(v1_replicate_rows, v2_replicate_rows, strict=True):
        if int(v1_row["replicate_index"]) != int(v2_row["replicate_index"]):
            raise V2010StatsError("PAIRED_BOOTSTRAP_REPLICATE_INDEX_MISALIGNED")
        v1_value = v1_row[metric_name]
        v2_value = v2_row[metric_name]
        if v1_value in (None, "") or v2_value in (None, ""):
            deltas.append(np.nan)
        else:
            deltas.append(float(v2_value) - float(v1_value))
    return np.asarray(deltas, dtype=np.float64)


def paired_bootstrap_summary(
    point_delta: float, deltas: np.ndarray
) -> dict[str, Any]:
    finite = deltas[np.isfinite(deltas)]
    if finite.size == 0:
        raise V2010StatsError("PAIRED_BOOTSTRAP_DEGENERATE_ALL_INVALID")
    return {
        "point_delta": float(point_delta),
        "ci_lower_95": float(np.quantile(finite, 0.025, method="linear")),
        "ci_upper_95": float(np.quantile(finite, 0.975, method="linear")),
        "valid_replicates": int(finite.size),
        "invalid_replicates": int(deltas.size - finite.size),
    }


def incart_auroc_runtime_guard_pass(
    ci_lower_95: float, tolerance: float = FLOATING_TOLERANCE
) -> bool:
    """INCART_AUROC_RUNTIME_GUARD_PASS iff the paired-bootstrap lower-95%-CI of
    AUROC_V2 - AUROC_V1 is >= 0.0, with a floating tolerance for roundoff only -- never a
    scientific margin."""
    return bool(ci_lower_95 >= -abs(tolerance))


def nstdb_no_collapse_pass(
    delta_auprc_by_snr: dict[int, float], tolerance: float = FLOATING_TOLERANCE
) -> bool:
    """NSTDB_NO_COLLAPSE_PASS iff, for every one of the six frozen SNR levels, pooled
    AUPRC_V2(SNR) - AUPRC_V1(SNR) >= 0.0 (floating tolerance for roundoff only). No SNR may
    be dropped."""
    observed = set(delta_auprc_by_snr)
    if observed != set(SNR_LEVELS_DB):
        raise V2010StatsError(f"NSTDB_SNR_SET_INCOMPLETE:{sorted(observed)}")
    return all(delta_auprc_by_snr[snr] >= -abs(tolerance) for snr in SNR_LEVELS_DB)


def runtime_acceptance_decision(
    *,
    method_integrity_pass: bool,
    incart_guard_pass: bool,
    nstdb_guard_pass: bool,
) -> str:
    """MODEL_V2_RUNTIME_ACCEPTED = ACCEPTED iff ALL three: V2-010 method/integrity checks
    pass, the INCART AUROC guard passes, and the NSTDB no-collapse guard passes. INTERNAL_TEST
    is descriptive-only and never participates in this decision. No subjective override."""
    accepted = bool(method_integrity_pass and incart_guard_pass and nstdb_guard_pass)
    return "ACCEPTED" if accepted else "NOT_ACCEPTED"


__all__ = [
    "FLOATING_TOLERANCE",
    "SNR_LEVELS_DB",
    "V2010StatsError",
    "incart_auroc_runtime_guard_pass",
    "nstdb_no_collapse_pass",
    "paired_bootstrap_delta",
    "paired_bootstrap_summary",
    "runtime_acceptance_decision",
]
