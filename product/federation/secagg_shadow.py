# ruff: noqa: E501
"""CAPSTONE SecAgg SHADOW integration (round 1 only).

Authoritative aggregation always stays PLAIN. The shadow reuses the unchanged
``federated.wearable_fl_secagg_shadow_v1.run_shadow`` (historical Flower SecAgg+ harness, frozen
SECAGG_CONFIG_V2 / WEARABLE_SIM_FL_SECAGG_COMPAT_V1 tolerances) over the round-1 client states and
reports a narrow PROTECTED_AGGREGATION_INTERFACE_ONLY result. A failed preflight or comparison raises;
tolerances are never widened and no privacy / anonymity / DP claim is made."""

from __future__ import annotations

from typing import Any

import numpy as np

CLAIM_SCOPE = "PROTECTED_AGGREGATION_INTERFACE_ONLY"
EXPECTED = {"clients": 8, "max_weight": 256.0, "plain_clear_update_count": 8,
            "protected_clear_update_count": 0}


class SecAggShadowFailure(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def floating_keys(state: dict[str, np.ndarray]) -> list[str]:
    return [k for k, v in state.items() if np.issubdtype(np.asarray(v).dtype, np.floating)]


def run_round1_shadow(global_state: dict[str, np.ndarray], deltas: dict[str, dict[str, np.ndarray]],
                      examples: dict[str, int]) -> dict[str, Any]:
    from federated.wearable_fl_secagg_shadow_v1 import (
        run_shadow,  # imported lazily: Flower is heavy
    )

    keys = floating_keys(global_state)
    global_floating = [np.array(global_state[k], copy=True) for k in keys]
    client_floating = {c: [np.asarray(global_state[k] + deltas[c][k], dtype=global_state[k].dtype)
                           for k in keys] for c in deltas}
    try:
        report = run_shadow(global_floating, client_floating, examples)
    except RuntimeError as error:
        raise SecAggShadowFailure(str(error)[:200]) from error
    ok = (report["status"] == "PASS" and len(deltas) == EXPECTED["clients"]
          and report["preflight"]["max_weight"] == EXPECTED["max_weight"]
          and report["plain_clear_update_count"] == EXPECTED["plain_clear_update_count"]
          and report["protected_clear_update_count"] == EXPECTED["protected_clear_update_count"]
          and report["protected_aggregate_available"])
    if not ok:
        raise SecAggShadowFailure("SECAGG_SHADOW_NOT_VERIFIED")
    return {**report, "claim_scope": CLAIM_SCOPE, "authoritative_aggregation": "PLAIN",
            "round": 1}
