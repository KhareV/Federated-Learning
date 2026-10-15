"""SecAgg+ round-one shadow for HARDWARE_DEMO_MODEL_V1.

The authoritative aggregate remains the plain sample-count weighted aggregate.  This
module exercises Flower's actual SecAgg+ workflow over the same eight local model
states and compares the protected result with that reference.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from privacy.secagg_app import ClientPayload, run_flower_secaggplus, run_plain_reference
from privacy.server_visibility import require_visibility_contract

COMPAT_ID = "HARDWARE_DEMO_SECAGG_SHADOW_V1"
MAX_WEIGHT = 64.0
CLIPPING_RANGE = 8.0
ABS_TOLERANCE = 2.0e-4
REL_TOLERANCE = 2.0e-4


def run_shadow(client_states: dict[str, list[np.ndarray]], examples: dict[str, int]) -> dict[str, Any]:
    order = sorted(client_states)
    if len(order) != 8 or set(order) != set(examples):
        raise RuntimeError("HARDWARE_DEMO_SECAGG_REQUIRES_EIGHT_CLIENTS")
    if min(examples.values()) < 1 or max(examples.values()) >= MAX_WEIGHT:
        raise RuntimeError("HARDWARE_DEMO_SECAGG_WEIGHT_BOUND")
    values = np.concatenate([np.asarray(a, dtype=np.float64).ravel() for c in order for a in client_states[c]])
    if not np.isfinite(values).all() or np.max(np.abs(values)) >= CLIPPING_RANGE:
        raise RuntimeError("HARDWARE_DEMO_SECAGG_VALUE_BOUND")
    payloads = [ClientPayload(c, i + 1, tuple(client_states[c]), examples[c]) for i, c in enumerate(order)]
    initial = [np.zeros_like(a) for a in client_states[order[0]]]
    plain, plain_probe, _ = run_plain_reference(payloads, initial)
    protected, protected_probe, accounting, stage_calls = run_flower_secaggplus(
        payloads,
        initial,
        num_shares=5,
        reconstruction_threshold=4,
        max_weight=MAX_WEIGHT,
        clipping_range=CLIPPING_RANGE,
        quantization_range=2**22,
        modulus_range=2**32,
    )
    require_visibility_contract(plain_probe, protected_probe)
    ref = np.concatenate([np.asarray(a, dtype=np.float64).ravel() for a in plain])
    got = np.concatenate([np.asarray(a, dtype=np.float64).ravel() for a in protected])
    difference = got - ref
    maximum_absolute_difference = float(np.max(np.abs(difference)))
    relative_l2_difference = float(np.linalg.norm(difference) / max(np.linalg.norm(ref), 1e-30))
    passed = (
        maximum_absolute_difference <= ABS_TOLERANCE
        and relative_l2_difference <= REL_TOLERANCE
        and plain_probe.clear_individual_update_count == 8
        and protected_probe.clear_individual_update_count == 0
        and protected_probe.aggregate_visible
    )
    if not passed:
        raise RuntimeError("HARDWARE_DEMO_SECAGG_COMPARISON_FAILED")
    return {
        "compat_id": COMPAT_ID,
        "status": "PASS",
        "round": 1,
        "authoritative_aggregation": "PLAIN",
        "mode": "ROUND-1 SECAGG+ SHADOW",
        "maximum_absolute_difference": maximum_absolute_difference,
        "relative_l2_difference": relative_l2_difference,
        "tolerance": {"maximum_absolute_difference": ABS_TOLERANCE, "relative_l2_difference": REL_TOLERANCE},
        "plain_clear_update_count": plain_probe.clear_individual_update_count,
        "protected_clear_update_count": protected_probe.clear_individual_update_count,
        "protected_aggregate_available": protected_probe.aggregate_visible,
        "masked_vectors_visible": protected_probe.as_dict()["masked_vectors_visible"],
        "stage_calls": stage_calls,
        "payload_accounting": accounting,
        "claim_boundary": "PROTECTED_AGGREGATION_INTERFACE_ONLY; no anonymity, DP, or production-security claim",
    }
