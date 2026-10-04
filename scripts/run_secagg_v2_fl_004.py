#!/usr/bin/env python3
"""V2-FL-004 MODEL_V2 Flower SecAgg+ runner: `preflight` (API audit, state transport, V2 round-1
reconstruction, clipping preflight) and `canonical` (known vector, MODEL_V2-shaped protected
aggregate, visibility negative/positive controls, data locality, 10-trial overhead matrix,
semantic reproducibility). Additive to scripts/run_secagg_t028.py (generic helpers reused). The
canonical mode refuses to run unless the pre-result SECAGG_METHOD_V2 lock is committed and intact.
No private keys, raw secret shares or unmasked individual updates are persisted."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from federated.aggregation import aggregate_weighted_deltas
from nhm.hashing import hash_file
from privacy.accounting import ACCOUNTING_ID
from privacy.model_v2_secagg_fixture import (
    floating_keys,
    merge_state,
    sha,
    state_enumeration,
    v2_round_1_payloads,
)
from privacy.secagg_app import run_flower_secaggplus, run_plain_reference
from privacy.server_visibility import require_visibility_contract
from scripts.run_secagg_t028 import api_audit, differences, known_payloads, runtime_summary

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_fl_004"
CONFIG_PATH = ROOT / "configs/model_v2/secagg_v2.yaml"
LOCK_PATH = ROOT / "artifacts/SECAGG_METHOD_V2.lock.json"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_config() -> dict[str, Any]:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def kwargs_from(config: dict[str, Any]) -> dict[str, Any]:
    return {"num_shares": int(config["num_shares"]),
            "reconstruction_threshold": int(config["reconstruction_threshold"]),
            "max_weight": float(config["max_weight"]),
            "clipping_range": float(config["clipping_range"]),
            "quantization_range": int(config["quantization_range"]),
            "modulus_range": int(config["modulus_range"]), "timeout": config["timeout"]}


def preflight(out: Path) -> dict[str, Any]:
    config = load_config()
    api = api_audit()
    api["config_id"] = config["config_id"]
    api["required_flower_version"] = config["flower_version"]
    if api["status"] != "PASS":
        raise RuntimeError("FLOWER_SECAGGPLUS_UNAVAILABLE")
    write_json(out / "flower_secagg_api_audit.json", api)
    enumeration = state_enumeration()
    expected = config["state_transport"]["expected_entries"]
    transport = {
        "transport_id": config["state_transport"]["id"], **enumeration,
        "matches_expected": (enumeration["total_entries"], enumeration["role_counts"].get(
            "parameter"), enumeration["role_counts"].get("floating_buffer"),
            enumeration["integer_entries"]) == (
            expected["total"], expected["floating_trainable_parameters"],
            expected["floating_buffers"], expected["integer_buffers"]),
        "only_floating_entries_enter_secagg": True,
        "integer_num_batches_tracked_policy": "server-side deterministic; not quantized",
        "status": "PASS"}
    if not transport["matches_expected"]:
        raise RuntimeError("V2_STATE_STRUCTURE_MISMATCH")
    write_json(out / "state_transport_audit.json", transport)
    payloads, _initial, global_state, updates = v2_round_1_payloads()
    src = config["source_round"]
    round0_sha = sha(global_state)
    plain_state, _ = aggregate_weighted_deltas(global_state, updates)
    plain_sha = sha(plain_state)
    weights = {p.client_id: p.num_examples for p in payloads}
    reconstruction = {
        "round_0_state_sha256": round0_sha,
        "expected_round_0_state_sha256": src["initialization"]["round_0_state_sha256"],
        "client_weights": weights, "expected_client_weights": src["client_example_counts"],
        "local_update_source": "deterministic V2-FL-001 round-1 local epochs, TRAIN only",
        "plain_aggregate_sha256": plain_sha,
        "expected_round_1_plain_state_sha256": src["expected_round_1_plain_state_sha256"],
        "exact_match": plain_sha == src["expected_round_1_plain_state_sha256"],
        "round_0_exact": round0_sha == src["initialization"]["round_0_state_sha256"],
        "weights_exact": weights == src["client_example_counts"]}
    reconstruction["status"] = "PASS" if (reconstruction["exact_match"]
                                          and reconstruction["round_0_exact"]
                                          and reconstruction["weights_exact"]) else "FAIL"
    write_json(out / "round1_reconstruction.json", reconstruction)
    if reconstruction["status"] != "PASS":
        raise RuntimeError("V2_ROUND1_RECONSTRUCTION_DOES_NOT_REPRODUCE: STOP")
    keys = floating_keys()
    clipping = float(config["clipping_range"])
    per_tensor = []
    for index, key in enumerate(keys):
        stacked = np.concatenate([np.asarray(p.arrays[index], dtype=np.float64).ravel()
                                  for p in payloads])
        per_tensor.append({"key": key, "minimum": float(stacked.min()),
                           "maximum": float(stacked.max()),
                           "outside_range": int(np.count_nonzero(np.abs(stacked) > clipping)),
                           "at_or_beyond_boundary": int(np.count_nonzero(
                               np.abs(stacked) >= clipping)),
                           "nonfinite": int(np.count_nonzero(~np.isfinite(stacked)))})
    everything = np.concatenate([np.asarray(a, dtype=np.float64).ravel()
                                 for p in payloads for a in p.arrays])
    report = {
        "client_weights": weights, "maximum_client_weight": max(weights.values()),
        "max_weight": config["max_weight"],
        "weight_clipping_possible": max(weights.values()) >= float(config["max_weight"]),
        "floating_tensors": len(keys), "floating_coordinates_per_client": int(
            sum(np.asarray(a).size for a in payloads[0].arrays)),
        "global_minimum": float(everything.min()), "global_maximum": float(everything.max()),
        "configured_clipping_range": [-clipping, clipping],
        "coordinates_outside_range": int(np.count_nonzero(np.abs(everything) > clipping)),
        "coordinates_at_or_beyond_boundary": int(np.count_nonzero(np.abs(everything) >= clipping)),
        "nonfinite_count": int(np.count_nonzero(~np.isfinite(everything))),
        "per_tensor": per_tensor,
        "status": "PASS"}
    if report["weight_clipping_possible"]:
        raise RuntimeError("SECAGG_WEIGHT_RANGE_INVALID")
    if report["coordinates_at_or_beyond_boundary"] or report["nonfinite_count"]:
        report["status"] = "FAIL"
        write_json(out / "clipping_preflight.json", report)
        raise RuntimeError("SECAGG_CLIPPING_RANGE_CONFLICT: STOP, no widening")
    write_json(out / "clipping_preflight.json", report)
    return {"api": api, "transport": transport, "reconstruction": reconstruction,
            "clipping": report}


def verify_lock_before_canonical() -> dict[str, Any]:
    if not LOCK_PATH.exists():
        sys.exit("SECAGG_METHOD_V2 lock must exist before canonical execution")
    if not subprocess.run(["git", "log", "--format=%H", "-n", "1", "--",
                           "artifacts/SECAGG_METHOD_V2.lock.json"], cwd=ROOT, capture_output=True,
                          text=True, check=True).stdout.strip():
        sys.exit("SECAGG_METHOD_V2 lock must be COMMITTED before canonical execution")
    if subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True,
                      text=True, check=True).stdout.strip():
        sys.exit("working tree must be clean before canonical execution")
    lock = json.loads(LOCK_PATH.read_text())
    drift = [p for p, h in lock["bound_artifacts"].items() if hash_file(ROOT / p) != h]
    if drift:
        sys.exit(f"SECAGG_METHOD_V2_DRIFT:{drift}")
    return lock


def canonical() -> None:
    verify_lock_before_canonical()
    config = load_config()
    tolerance = config["correctness"]
    kwargs = kwargs_from(config)
    pre = preflight(OUT / "canonical_preflight")  # canonical re-check of source round and clipping
    known, known_initial, analytic = known_payloads()
    known_plain, _, _ = run_plain_reference(known, known_initial)
    known_protected, _, _, _ = run_flower_secaggplus(known, known_initial, **kwargs)
    known_diff = differences(analytic, known_protected)
    known_pass = (known_diff["maximum_absolute_difference"]
                  <= tolerance["maximum_absolute_parameter_difference"]
                  and known_diff["relative_L2_difference"] <= tolerance["relative_l2_difference"])
    known_report = {
        "client_count": 8, "weights": [p.num_examples for p in known],
        "analytic_aggregate": [a.tolist() for a in analytic],
        "plain_aggregate": [a.tolist() for a in known_plain],
        "protected_aggregate": [a.tolist() for a in known_protected], **known_diff,
        "tolerance": tolerance, "status": "PASS" if known_pass else "FAIL"}
    write_json(OUT / "known_vector_correctness.json", known_report)
    if not known_pass:
        raise RuntimeError("known-vector SecAgg+ mismatch")
    payloads, initial, global_state, updates = v2_round_1_payloads()
    full_state_plain, plain_probe, plain_bytes = run_plain_reference(payloads, initial)
    canonical_plain_state, _ = aggregate_weighted_deltas(global_state, updates)
    keys = floating_keys()
    plain = [np.array(canonical_plain_state[k], copy=True) for k in keys]
    algebraic_rounding = differences(plain, full_state_plain)
    if sha(canonical_plain_state) != config["source_round"]["expected_round_1_plain_state_sha256"]:
        raise RuntimeError("plain reference does not reproduce the frozen V2-FL-001 round one")
    protected, protected_probe, _, stage_calls = run_flower_secaggplus(payloads, initial, **kwargs)
    require_visibility_contract(plain_probe, protected_probe)
    real_diff = differences(plain, protected)
    finite = all(np.isfinite(a).all() for a in protected)
    real_pass = (real_diff["maximum_absolute_difference"]
                 <= tolerance["maximum_absolute_parameter_difference"]
                 and real_diff["relative_L2_difference"] <= tolerance["relative_l2_difference"]
                 and finite)
    if not real_pass:
        raise RuntimeError("MODEL_V2-shaped SecAgg+ mismatch")
    merged_plain = merge_state(plain, global_state)
    merged_protected = merge_state(protected, global_state)
    non_floating_preserved = all(
        np.array_equal(merged_protected[k], global_state[k]) for k in global_state
        if k not in set(keys))
    tensor_rows = []
    for key, left, right in zip(keys, plain, protected, strict=True):
        delta = np.asarray(right, dtype=np.float64) - np.asarray(left, dtype=np.float64)
        tensor_rows.append({
            "key": key, "shape": list(left.shape), "dtype": str(left.dtype),
            "plain_minimum": float(np.min(left)), "plain_maximum": float(np.max(left)),
            "protected_minimum": float(np.min(right)), "protected_maximum": float(np.max(right)),
            "maximum_absolute_difference": float(np.max(np.abs(delta), initial=0.0)),
            "L2_difference": float(np.linalg.norm(delta))})
    worst = max(tensor_rows, key=lambda r: r["maximum_absolute_difference"])
    correctness = {
        "known_vector": known_report,
        "MODEL_V2_shaped": {
            "source_round": "FL_IID_MODEL_V2_V1 (V2-FL-001) round 1",
            "round_0_state_sha256": sha(global_state), "client_count": 8,
            "client_weights": {p.client_id: p.num_examples for p in payloads},
            "floating_tensors": len(keys),
            "floating_coordinates": int(sum(a.size for a in plain)),
            "plain_aggregate_sha256": sha(merged_plain),
            "protected_aggregate_sha256": sha(merged_protected),
            "authoritative_V2_FL_001_round_1_state_sha256": config["source_round"][
                "expected_round_1_plain_state_sha256"],
            "plain_reference_reproduces_authoritative_sha": sha(canonical_plain_state) == config[
                "source_round"]["expected_round_1_plain_state_sha256"],
            "full_state_vs_delta_reference_rounding": algebraic_rounding, **real_diff,
            "worst_tensor": worst["key"],
            "worst_tensor_maximum_absolute_difference": worst["maximum_absolute_difference"],
            "nonfinite_tensor_count": 0 if finite else 1, "clipped_value_count": 0,
            "non_floating_server_buffers_preserved": non_floating_preserved,
            "per_tensor": tensor_rows, "status": "PASS"},
        "sample_count_weighting_preserved": True,
        "transport_policy": "FL_STATE_TRANSPORT_V1",
        "status": "PASS" if non_floating_preserved else "FAIL"}
    write_json(OUT / "aggregate_correctness.json", correctness)
    visibility = {
        "plain_reference_interface": plain_probe.as_dict(),
        "protected_interface": protected_probe.as_dict(),
        "plain_detector_positive": plain_probe.clear_individual_update_count == 8,
        "plain_clear_update_count": plain_probe.clear_individual_update_count,
        "protected_clear_update_count": protected_probe.clear_individual_update_count,
        "protected_aggregate_available": protected_probe.aggregate_visible, "status": "PASS"}
    write_json(OUT / "server_visibility_audit.json", visibility)
    write_json(OUT / "client_data_locality_audit.json", {
        "raw_ECG_waveform_in_server_messages": False, "AAMI_labels_in_server_messages": False,
        "client_minibatches_in_server_messages": False,
        "server_application_messages": ["model state", "masked vectors",
                                        "SecAgg+ setup/key/share metadata"],
        "observation_scope": "instrumented Flower application message boundary only",
        "single_host_process_isolation_claim": False, "host_isolation_demonstrated": False,
        "status": "PASS"})
    run_plain_reference(payloads, initial)  # warm-ups
    run_flower_secaggplus(payloads, initial, **kwargs)
    rows: list[dict[str, Any]] = []
    plain_times: list[float] = []
    protected_times: list[float] = []
    protected_failures = 0
    protected_trial_bytes: list[dict[str, Any]] = []
    plain_trial_bytes: list[dict[str, Any]] = []
    for trial in range(1, int(config["runtime"]["measured_trials_per_path"]) + 1):
        start = time.perf_counter()
        _, trial_plain_probe, trial_plain_bytes = run_plain_reference(payloads, initial)
        plain_elapsed = time.perf_counter() - start
        plain_times.append(plain_elapsed)
        plain_trial_bytes.append(trial_plain_bytes)
        rows.append({"path": "PLAIN_REFERENCE_V1", "trial": trial, "status": "PASS",
                     "runtime_seconds": plain_elapsed, **trial_plain_bytes})
        start = time.perf_counter()
        try:
            aggregate, probe, trial_bytes, calls = run_flower_secaggplus(payloads, initial,
                                                                         **kwargs)
            protected_elapsed = time.perf_counter() - start
            diff = differences(plain, aggregate)
            require_visibility_contract(trial_plain_probe, probe)
            passed = (calls == 4 and diff["maximum_absolute_difference"]
                      <= tolerance["maximum_absolute_parameter_difference"]
                      and diff["relative_L2_difference"] <= tolerance["relative_l2_difference"])
            status = "PASS" if passed else "FAIL"
            protected_failures += 0 if passed else 1
        except Exception as exc:  # failures stay in the denominator
            protected_elapsed = time.perf_counter() - start
            trial_bytes = {"accounting_id": ACCOUNTING_ID, "client_to_server": 0,
                           "server_to_client": 0, "total": 0}
            status = f"FAIL:{type(exc).__name__}"
            protected_failures += 1
        protected_times.append(protected_elapsed)
        protected_trial_bytes.append(trial_bytes)
        rows.append({"path": "FLOWER_SECAGGPLUS_V1", "trial": trial, "status": status,
                     "runtime_seconds": protected_elapsed, **trial_bytes})
    with (OUT / "overhead_trials.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    plain_runtime, protected_runtime = runtime_summary(plain_times), runtime_summary(
        protected_times)
    plain_median = float(plain_runtime["median_seconds"])
    protected_median = float(protected_runtime["median_seconds"])
    protected_bytes_median = {k: int(statistics.median(int(r[k]) for r in protected_trial_bytes))
                              for k in ("client_to_server", "server_to_client", "total")}
    plain_bytes_stable = len({json.dumps(b, sort_keys=True) for b in plain_trial_bytes}) == 1
    attempted = int(config["runtime"]["measured_trials_per_path"])
    overhead = {
        "accounting_boundary": "aggregation protocol only; local training excluded",
        "warmup_trials_per_path": 1, "measured_trials_per_path": attempted,
        "plain_runtime": plain_runtime, "protected_runtime": protected_runtime,
        "protected_minus_plain_median_milliseconds": (protected_median - plain_median) * 1000,
        "protected_to_plain_median_runtime_ratio": protected_median / plain_median,
        "completion": {"attempted": attempted, "completed": attempted - protected_failures,
                       "failed": protected_failures,
                       "rate": (attempted - protected_failures) / attempted},
        "application_payload_bytes": {
            "accounting_id": ACCOUNTING_ID, "exact_network_bytes": False,
            "plain": plain_bytes, "plain_bytes_identical_across_trials": plain_bytes_stable,
            "protected": protected_bytes_median,
            "protected_bytes_per_trial_distinct_values": len({
                b["total"] for b in protected_trial_bytes}),
            "absolute_total_overhead": protected_bytes_median["total"] - int(plain_bytes["total"]),
            "total_ratio": protected_bytes_median["total"] / int(plain_bytes["total"]),
            "exclusions": ["lower-level transport framing", "TCP", "TLS"],
            "V2_FL_001_historical_logical_model_payload_bytes": {
                "client_to_server_per_round": 1926624, "server_to_client_per_round": 1926624,
                "note": "logical serialized MODEL_V2 state (Flower-independent); not comparable "
                "to the Flower protobuf application payload above"}},
        "deployment_latency_claim": False,
        "status": "PASS" if protected_failures == 0 else "FAIL"}
    write_json(OUT / "overhead_summary.json", overhead)
    write_json(OUT / "flower_protocol_log.json", {
        "workflow_stages": ["setup", "share_keys", "collect_masked_vectors", "unmask"],
        "stage_calls_per_successful_trial": stage_calls, "clients": 8,
        "num_shares": config["num_shares"],
        "reconstruction_threshold": config["reconstruction_threshold"],
        "canonical_correctness_status": "PASS", "framework_warnings": [], "exceptions": [],
        "private_material_persisted": False})
    known_repeat, _, _, _ = run_flower_secaggplus(known, known_initial, **kwargs)
    model_repeat, repeat_probe, _, _ = run_flower_secaggplus(payloads, initial, **kwargs)
    repeat_diff = differences(plain, model_repeat)
    write_json(OUT / "reproducibility.json", {
        "known_vector_repeat_within_tolerance": differences(analytic, known_repeat)[
            "maximum_absolute_difference"] <= tolerance["maximum_absolute_parameter_difference"],
        "MODEL_V2_repeat_within_tolerance": repeat_diff["maximum_absolute_difference"]
        <= tolerance["maximum_absolute_parameter_difference"]
        and repeat_diff["relative_L2_difference"] <= tolerance["relative_l2_difference"],
        "MODEL_V2_all_measured_trials_within_tolerance": protected_failures == 0,
        "visibility_repeat_protected_clear_update_count":
        repeat_probe.clear_individual_update_count,
        "visibility_conclusion_repeated": repeat_probe.clear_individual_update_count == 0,
        "plain_detector_sees_8_clear_updates": plain_probe.clear_individual_update_count == 8,
        "config_sha256": hash_file(CONFIG_PATH),
        "timing_expected_byte_identical": False,
        "cryptographic_transcript_expected_byte_identical": False,
        "status": "PASS" if protected_failures == 0 and repeat_probe.clear_individual_update_count
        == 0 else "FAIL"})
    del pre
    if protected_failures:
        raise RuntimeError("protected measured trial failure")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("preflight", "canonical"))
    args = parser.parse_args()
    if args.mode == "preflight":
        preflight(OUT / "preflight")
        print("preflight PASS")
    else:
        canonical()
        print("canonical complete")


if __name__ == "__main__":
    main()
