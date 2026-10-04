"""WEARABLE_SIM_FL_SECAGG_COMPAT_V1: one-round Flower SecAgg+ shadow over the synthetic round-1
client states, reusing the historical harness (privacy/*) and SECAGG_CONFIG_V2 parameters."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import yaml

from privacy.secagg_app import ClientPayload, run_flower_secaggplus, run_plain_reference
from privacy.server_visibility import require_visibility_contract

ROOT = Path(__file__).resolve().parents[1]
PARAMETER_KEYS = ("flower_version", "clients", "num_shares", "reconstruction_threshold",
                  "clipping_range", "quantization_range", "modulus_range",
                  "timeout", "correctness")


def derive_max_weight(max_client_examples_seen: int) -> float:
    """next_power_of_two(2 * max_client_examples_seen) -- structural counts only."""
    value = 1
    while value < 2 * max_client_examples_seen:
        value *= 2
    return float(value)


def load_compat() -> dict[str, Any]:
    compat = yaml.safe_load(
        (ROOT / "configs/model_v2/wearable_sim_fl_secagg_compat_v1.yaml").read_text())
    base = yaml.safe_load((ROOT / "configs/model_v2/secagg_v2.yaml").read_text())
    base["clients"], base["flower_version"] = 8, "1.39.0"
    for key in PARAMETER_KEYS:
        if key in base and compat[key] != base[key]:
            raise RuntimeError(f"SECAGG_COMPAT_PARAMETER_DRIFT:{key}")
    override = compat["max_weight_override"]
    if (compat["max_weight"] != override["derived_value"]
            or override["inherited_value"] != base["max_weight"]
            or derive_max_weight(override["max_client_examples_seen"]) != compat["max_weight"]):
        raise RuntimeError("SECAGG_COMPAT_MAX_WEIGHT_RULE_VIOLATION")
    for key in ("plain_clear_update_count_required", "protected_clear_update_count_required"):
        if compat["visibility"][key] != base["visibility"][key]:
            raise RuntimeError(f"SECAGG_COMPAT_PARAMETER_DRIFT:visibility.{key}")
    return compat


def run_shadow(global_floating: list[np.ndarray], client_floating: dict[str, list[np.ndarray]],
               examples: dict[str, int]) -> dict[str, Any]:
    compat = load_compat()
    order = sorted(client_floating)
    clip = float(compat["clipping_range"])
    all_values = np.concatenate([np.asarray(a, dtype=np.float64).ravel()
                                 for c in order for a in client_floating[c]])
    preflight = {
        "examples_seen": {c: examples[c] for c in order},
        "max_examples": max(examples.values()), "max_weight": compat["max_weight"],
        "max_weight_rule_input_matches_cohort": max(examples.values())
        == compat["max_weight_override"]["max_client_examples_seen"],
        "weight_headroom_ratio": compat["max_weight"] / max(examples.values()),
        "weight_clipping_possible": max(examples.values()) >= float(compat["max_weight"]),
        "weights_below_max_weight": max(examples.values()) < float(compat["max_weight"]),
        "floating_coordinates_per_client": int(sum(a.size for a in client_floating[order[0]])),
        "global_minimum": float(all_values.min()), "global_maximum": float(all_values.max()),
        "coordinates_outside_range": int(np.count_nonzero(np.abs(all_values) > clip)),
        "coordinates_at_or_beyond_boundary": int(np.count_nonzero(np.abs(all_values) >= clip)),
        "nonfinite_count": int(np.count_nonzero(~np.isfinite(all_values)))}
    if (not preflight["weights_below_max_weight"]
            or not preflight["max_weight_rule_input_matches_cohort"]
            or preflight["coordinates_at_or_beyond_boundary"]
            or preflight["nonfinite_count"]):
        raise RuntimeError("SECAGG_SHADOW_PREFLIGHT_VIOLATION: STOP, no widening")
    payloads = [ClientPayload(c, node, tuple(client_floating[c]), examples[c])
                for node, c in enumerate(order, start=1)]
    plain, plain_probe, _ = run_plain_reference(payloads, global_floating)
    kwargs = {k: (float(compat[k]) if k in ("max_weight", "clipping_range") else compat[k])
              for k in ("num_shares", "reconstruction_threshold", "max_weight", "clipping_range",
                        "quantization_range", "modulus_range", "timeout")}
    protected, protected_probe, _, stage_calls = run_flower_secaggplus(
        payloads, global_floating, **kwargs)
    require_visibility_contract(plain_probe, protected_probe)
    ref = np.concatenate([np.asarray(a, dtype=np.float64).ravel() for a in plain])
    got = np.concatenate([np.asarray(a, dtype=np.float64).ravel() for a in protected])
    delta = got - ref
    max_abs = float(np.max(np.abs(delta)))
    rel_l2 = float(np.linalg.norm(delta) / max(np.linalg.norm(ref), 1e-30))
    tol = compat["correctness"]
    passed = (max_abs <= tol["maximum_absolute_parameter_difference"]
              and rel_l2 <= tol["relative_l2_difference"]
              and plain_probe.clear_individual_update_count == 8
              and protected_probe.clear_individual_update_count == 0
              and protected_probe.aggregate_visible and bool(np.isfinite(got).all()))
    return {
        "compat_id": compat["compat_id"], "preflight": preflight,
        "maximum_absolute_difference": max_abs, "relative_L2_difference": rel_l2,
        "plain_clear_update_count": plain_probe.clear_individual_update_count,
        "protected_clear_update_count": protected_probe.clear_individual_update_count,
        "protected_aggregate_available": protected_probe.aggregate_visible,
        "masked_vectors_visible": protected_probe.as_dict()["masked_vectors_visible"],
        "stage_calls": stage_calls, "tolerance": tol, "status": "PASS" if passed else "FAIL"}
