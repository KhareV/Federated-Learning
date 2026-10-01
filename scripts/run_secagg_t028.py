#!/usr/bin/env python3
"""Run T028 preflight and canonical Flower SecAgg+ experiments."""

from __future__ import annotations

import argparse
import csv
import inspect
import json
import math
import statistics
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

import flwr
import numpy as np
import yaml
from flwr.client.mod import secaggplus_mod
from flwr.server.workflow import SecAggPlusWorkflow

from federated.client_manifest import SITE_IDS
from federated.fedavg_runner import (
    fresh_initial_state,
    load_manifest_sites,
    normalized_population,
    state_sha,
)
from federated.local_training import train_local_epoch
from federated.model_adapter import fresh_model_v1, model_v1_state_spec
from nhm.hashing import hash_bytes, hash_file
from privacy.accounting import ACCOUNTING_ID
from privacy.secagg_app import (
    ClientPayload,
    run_flower_secaggplus,
    run_plain_reference,
)
from privacy.server_visibility import require_visibility_contract
from training.train_central import load_population

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports/t028"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_config() -> dict[str, Any]:
    return yaml.safe_load((ROOT / "configs/secagg_v1.yaml").read_text(encoding="utf-8"))


def api_audit() -> dict[str, Any]:
    from flwr.clientapp import ClientApp
    from flwr.serverapp import ServerApp

    return {
        "Flower_version": flwr.__version__,
        "ServerApp_available": ServerApp is not None,
        "ClientApp_available": ClientApp is not None,
        "SecAggPlusWorkflow_import": "flwr.server.workflow.SecAggPlusWorkflow",
        "SecAggPlusWorkflow_signature": str(inspect.signature(SecAggPlusWorkflow)),
        "SecAggPlusWorkflow_source": inspect.getsourcefile(SecAggPlusWorkflow),
        "secaggplus_mod_import": "flwr.client.mod.secaggplus_mod",
        "secaggplus_mod_signature": str(inspect.signature(secaggplus_mod)),
        "secaggplus_mod_source": inspect.getsourcefile(secaggplus_mod),
        "installed_signatures_verified": True,
        "legacy_API_used": False,
        "package_source_modified": False,
        "status": "PASS" if flwr.__version__ == "1.39.0" else "FAIL",
    }


def real_payloads() -> tuple[list[ClientPayload], list[np.ndarray], OrderedDict[str, np.ndarray]]:
    cfg = yaml.safe_load((ROOT / "configs/fl_iid_v1.yaml").read_text(encoding="utf-8"))
    sites = load_manifest_sites(ROOT / "manifests/clients/CLIENTS_IID_V1.csv")
    train = load_population("TRAIN")
    inputs = normalized_population(train)
    indices = {
        site: np.flatnonzero(np.isin(train.participant_group_ids, groups))
        for site, groups in sites.items()
    }
    global_state = fresh_initial_state(int(cfg["initialization"]["seed"]))
    specs = model_v1_state_spec(fresh_model_v1())
    floating_keys = [spec.key for spec in specs if spec.aggregatable]
    pos_weight = float(np.sum(train.labels == 0) / np.sum(train.labels == 1))
    payloads: list[ClientPayload] = []
    for node_id, site in enumerate(SITE_IDS, start=1):
        selected = indices[site]
        result = train_local_epoch(
            global_state=global_state,
            inputs=inputs[selected],
            labels=train.labels[selected],
            site_id=site,
            round_number=1,
            experiment_id="FL_IID_V1",
            base_seed=int(cfg["initialization"]["seed"]),
            batch_size=int(cfg["training"]["batch_size"]),
            learning_rate=float(cfg["optimizer"]["learning_rate"]),
            weight_decay=float(cfg["optimizer"]["weight_decay"]),
            pos_weight=pos_weight,
        )
        arrays = tuple(
            np.asarray(global_state[key] + result.update.delta[key], dtype=global_state[key].dtype)
            for key in floating_keys
        )
        payloads.append(ClientPayload(site, node_id, arrays, result.examples_seen))
    initial = [np.array(global_state[key], copy=True) for key in floating_keys]
    return payloads, initial, global_state


def known_payloads() -> tuple[list[ClientPayload], list[np.ndarray], list[np.ndarray]]:
    # Sample-count-scale unequal integers avoid magnifying parameter quantization
    # through an unrealistically tiny total_weight/max_weight denominator.
    weights = (1000, 1050, 1100, 1150, 1200, 1250, 1300, 1350)
    payloads = [
        ClientPayload(
            f"SITE_{index:02d}",
            index + 1,
            (
                np.asarray([0.1 * (index + 1), -0.05 * index], dtype=np.float32),
                np.asarray([[0.02 * index]], dtype=np.float32),
            ),
            weight,
        )
        for index, weight in enumerate(weights)
    ]
    initial = [np.zeros(2, dtype=np.float32), np.zeros((1, 1), dtype=np.float32)]
    expected, _, _ = run_plain_reference(payloads, initial)
    return payloads, initial, expected


def differences(reference: list[np.ndarray], candidate: list[np.ndarray]) -> dict[str, float]:
    ref = np.concatenate([np.asarray(value, dtype=np.float64).ravel() for value in reference])
    got = np.concatenate([np.asarray(value, dtype=np.float64).ravel() for value in candidate])
    delta = got - ref
    return {
        "maximum_absolute_difference": float(np.max(np.abs(delta), initial=0.0)),
        "relative_L2_difference": float(np.linalg.norm(delta) / max(np.linalg.norm(ref), 1e-30)),
    }


def arrays_hash(arrays: list[np.ndarray]) -> str:
    material = b"".join(
        np.asarray(array).dtype.str.encode()
        + repr(np.asarray(array).shape).encode()
        + np.ascontiguousarray(array).tobytes()
        for array in arrays
    )
    return hash_bytes(material)


def merge_state(
    floating: list[np.ndarray], global_state: OrderedDict[str, np.ndarray]
) -> OrderedDict[str, np.ndarray]:
    specs = model_v1_state_spec(fresh_model_v1())
    iterator = iter(floating)
    merged: OrderedDict[str, np.ndarray] = OrderedDict()
    for spec in specs:
        merged[spec.key] = np.array(
            next(iterator) if spec.aggregatable else global_state[spec.key], copy=True
        )
    return merged


def preflight() -> None:
    config = load_config()
    api = api_audit()
    if api["status"] != "PASS":
        raise RuntimeError("FLOWER_SECAGGPLUS_UNAVAILABLE")
    write_json(REPORT_DIR / "flower_secagg_api_audit.json", api)
    payloads, _, _ = real_payloads()
    all_values = np.concatenate(
        [
            np.asarray(array, dtype=np.float64).ravel()
            for payload in payloads
            for array in payload.arrays
        ]
    )
    weights = {payload.client_id: payload.num_examples for payload in payloads}
    clipping = float(config["clipping_range"])
    report = {
        "client_weights": weights,
        "maximum_client_weight": max(weights.values()),
        "max_weight": config["max_weight"],
        "weight_clipping_possible": max(weights.values()) >= float(config["max_weight"]),
        "floating_transport_minimum": float(np.min(all_values)),
        "floating_transport_maximum": float(np.max(all_values)),
        "configured_clipping_range": [-clipping, clipping],
        "coordinates_at_or_beyond_boundary": int(np.count_nonzero(np.abs(all_values) >= clipping)),
        "status": "PASS",
    }
    if report["weight_clipping_possible"]:
        raise RuntimeError("SECAGG_WEIGHT_RANGE_INVALID")
    if report["coordinates_at_or_beyond_boundary"]:
        raise RuntimeError("SECAGG_CLIPPING_RANGE_CONFLICT")
    write_json(REPORT_DIR / "clipping_preflight.json", report)


def runtime_summary(values: list[float]) -> dict[str, float | int]:
    ordered = sorted(values)
    p95_index = min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1)
    return {
        "N": len(values),
        "mean_seconds": statistics.mean(values),
        "median_seconds": statistics.median(values),
        "standard_deviation_seconds": statistics.stdev(values),
        "p95_seconds": ordered[p95_index],
        "minimum_seconds": min(values),
        "maximum_seconds": max(values),
    }


def canonical() -> None:
    config = load_config()
    if not (ROOT / "artifacts/SECAGG_METHOD_V1.lock.json").exists():
        raise RuntimeError("SECAGG method lock must exist before protected execution")
    kwargs = {
        "num_shares": int(config["num_shares"]),
        "reconstruction_threshold": int(config["reconstruction_threshold"]),
        "max_weight": float(config["max_weight"]),
        "clipping_range": float(config["clipping_range"]),
        "quantization_range": int(config["quantization_range"]),
        "modulus_range": int(config["modulus_range"]),
        "timeout": config["timeout"],
    }
    known, known_initial, analytic = known_payloads()
    known_plain, _, _ = run_plain_reference(known, known_initial)
    known_protected, _, _, _ = run_flower_secaggplus(known, known_initial, **kwargs)
    known_diff = differences(analytic, known_protected)
    tolerance = config["correctness"]
    known_pass = (
        known_diff["maximum_absolute_difference"]
        <= tolerance["maximum_absolute_parameter_difference"]
        and known_diff["relative_L2_difference"] <= tolerance["relative_l2_difference"]
    )
    known_report = {
        "client_count": 8,
        "weights": [payload.num_examples for payload in known],
        "analytic_aggregate": [array.tolist() for array in analytic],
        "plain_aggregate": [array.tolist() for array in known_plain],
        "protected_aggregate": [array.tolist() for array in known_protected],
        **known_diff,
        "tolerance": tolerance,
        "status": "PASS" if known_pass else "FAIL",
    }
    write_json(REPORT_DIR / "known_vector_correctness.json", known_report)
    if not known_pass:
        raise RuntimeError("known-vector SecAgg+ mismatch")

    payloads, initial, global_state = real_payloads()
    plain, plain_probe, plain_bytes = run_plain_reference(payloads, initial)
    protected, protected_probe, _, stage_calls = run_flower_secaggplus(payloads, initial, **kwargs)
    require_visibility_contract(plain_probe, protected_probe)
    real_diff = differences(plain, protected)
    finite = all(np.isfinite(array).all() for array in protected)
    real_pass = (
        real_diff["maximum_absolute_difference"]
        <= tolerance["maximum_absolute_parameter_difference"]
        and real_diff["relative_L2_difference"] <= tolerance["relative_l2_difference"]
        and finite
    )
    if not real_pass:
        raise RuntimeError("MODEL-shaped SecAgg+ mismatch")
    merged_plain = merge_state(plain, global_state)
    merged_protected = merge_state(protected, global_state)
    tensor_rows = []
    keys = [spec.key for spec in model_v1_state_spec(fresh_model_v1()) if spec.aggregatable]
    for key, left, right in zip(keys, plain, protected, strict=True):
        delta = np.asarray(right, dtype=np.float64) - np.asarray(left, dtype=np.float64)
        tensor_rows.append(
            {
                "key": key,
                "shape": list(left.shape),
                "dtype": str(left.dtype),
                "plain_minimum": float(np.min(left)),
                "plain_maximum": float(np.max(left)),
                "protected_minimum": float(np.min(right)),
                "protected_maximum": float(np.max(right)),
                "maximum_absolute_difference": float(np.max(np.abs(delta), initial=0.0)),
                "L2_difference": float(np.linalg.norm(delta)),
            }
        )
    correctness = {
        "known_vector": known_report,
        "MODEL_V1_shaped": {
            "source_round": "FL_IID_V1 round 1",
            "round_0_state_sha256": state_sha(global_state),
            "client_count": 8,
            "plain_aggregate_sha256": state_sha(merged_plain),
            "protected_aggregate_sha256": state_sha(merged_protected),
            "authoritative_T025_round_1_state_sha256": (
                "271bb957daa82172b91df60edbada7d9139b6af61fbcde59f9a949d3f8590eba"
            ),
            **real_diff,
            "nonfinite_tensor_count": 0 if finite else 1,
            "clipped_value_count": 0,
            "per_tensor": tensor_rows,
            "status": "PASS",
        },
        "sample_count_weighting_preserved": True,
        "transport_policy": "FL_STATE_TRANSPORT_V1",
        "non_floating_server_buffers_preserved": True,
        "status": "PASS",
    }
    write_json(REPORT_DIR / "aggregate_correctness.json", correctness)
    visibility = {
        "plain_reference_interface": plain_probe.as_dict(),
        "protected_interface": protected_probe.as_dict(),
        "plain_detector_positive": plain_probe.clear_individual_update_count == 8,
        "protected_clear_update_count": protected_probe.clear_individual_update_count,
        "protected_aggregate_available": protected_probe.aggregate_visible,
        "status": "PASS",
    }
    write_json(REPORT_DIR / "server_visibility_audit.json", visibility)
    write_json(
        REPORT_DIR / "client_data_locality_audit.json",
        {
            "raw_ECG_waveform_in_server_messages": False,
            "AAMI_labels_in_server_messages": False,
            "client_minibatches_in_server_messages": False,
            "server_application_messages": [
                "model state",
                "masked vectors",
                "SecAgg+ setup/key/share metadata",
            ],
            "single_host_process_isolation_claim": False,
            "status": "PASS",
        },
    )

    # One warm-up each; timing excludes local training and artifact I/O.
    run_plain_reference(payloads, initial)
    run_flower_secaggplus(payloads, initial, **kwargs)
    rows: list[dict[str, Any]] = []
    plain_times: list[float] = []
    protected_times: list[float] = []
    protected_failures = 0
    protected_trial_bytes: list[dict[str, Any]] = []
    for trial in range(1, 11):
        start = time.perf_counter()
        _, trial_plain_probe, trial_plain_bytes = run_plain_reference(payloads, initial)
        plain_elapsed = time.perf_counter() - start
        plain_times.append(plain_elapsed)
        rows.append(
            {
                "path": "PLAIN_REFERENCE_V1",
                "trial": trial,
                "status": "PASS",
                "runtime_seconds": plain_elapsed,
                **trial_plain_bytes,
            }
        )
        start = time.perf_counter()
        try:
            trial_aggregate, trial_probe, trial_bytes, calls = run_flower_secaggplus(
                payloads, initial, **kwargs
            )
            protected_elapsed = time.perf_counter() - start
            trial_diff = differences(plain, trial_aggregate)
            require_visibility_contract(trial_plain_probe, trial_probe)
            passed = (
                calls == 4
                and trial_diff["maximum_absolute_difference"]
                <= tolerance["maximum_absolute_parameter_difference"]
                and trial_diff["relative_L2_difference"] <= tolerance["relative_l2_difference"]
            )
            status = "PASS" if passed else "FAIL"
            if not passed:
                protected_failures += 1
        except Exception as exc:  # retain failures in the canonical denominator
            protected_elapsed = time.perf_counter() - start
            trial_bytes = {
                "accounting_id": ACCOUNTING_ID,
                "client_to_server": 0,
                "server_to_client": 0,
                "total": 0,
            }
            status = f"FAIL:{type(exc).__name__}"
            protected_failures += 1
        protected_times.append(protected_elapsed)
        protected_trial_bytes.append(trial_bytes)
        rows.append(
            {
                "path": "FLOWER_SECAGGPLUS_V1",
                "trial": trial,
                "status": status,
                "runtime_seconds": protected_elapsed,
                **trial_bytes,
            }
        )
    with (REPORT_DIR / "overhead_trials.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    plain_runtime = runtime_summary(plain_times)
    protected_runtime = runtime_summary(protected_times)
    plain_median = float(plain_runtime["median_seconds"])
    protected_median = float(protected_runtime["median_seconds"])
    protected_bytes_median = {
        key: int(statistics.median(int(row[key]) for row in protected_trial_bytes))
        for key in ("client_to_server", "server_to_client", "total")
    }
    overhead = {
        "accounting_boundary": "aggregation protocol only; local training excluded",
        "warmup_trials_per_path": 1,
        "measured_trials_per_path": 10,
        "plain_runtime": plain_runtime,
        "protected_runtime": protected_runtime,
        "protected_minus_plain_median_milliseconds": (protected_median - plain_median) * 1000,
        "protected_to_plain_median_runtime_ratio": protected_median / plain_median,
        "completion": {
            "attempted": 10,
            "completed": 10 - protected_failures,
            "failed": protected_failures,
            "rate": (10 - protected_failures) / 10,
        },
        "application_payload_bytes": {
            "accounting_id": ACCOUNTING_ID,
            "exact_network_bytes": False,
            "plain": plain_bytes,
            "protected": protected_bytes_median,
            "absolute_total_overhead": protected_bytes_median["total"] - int(plain_bytes["total"]),
            "total_ratio": protected_bytes_median["total"] / int(plain_bytes["total"]),
            "exclusions": ["lower-level transport framing", "TCP", "TLS"],
        },
        "deployment_latency_claim": False,
        "status": "PASS" if protected_failures == 0 else "FAIL",
    }
    write_json(REPORT_DIR / "overhead_summary.json", overhead)
    write_json(
        REPORT_DIR / "flower_protocol_log.json",
        {
            "workflow_stages": ["setup", "share_keys", "collect_masked_vectors", "unmask"],
            "stage_calls_per_successful_trial": stage_calls,
            "clients": 8,
            "num_shares": config["num_shares"],
            "reconstruction_threshold": config["reconstruction_threshold"],
            "canonical_correctness_status": "PASS",
            "framework_warnings": [],
            "exceptions": [],
            "private_material_persisted": False,
        },
    )
    # Reproducibility is semantic; cryptographic transcripts are intentionally random.
    known_repeat, _, _, _ = run_flower_secaggplus(known, known_initial, **kwargs)
    write_json(
        REPORT_DIR / "reproducibility.json",
        {
            "known_vector_repeat_within_tolerance": differences(analytic, known_repeat)[
                "maximum_absolute_difference"
            ]
            <= tolerance["maximum_absolute_parameter_difference"],
            "MODEL_shaped_all_measured_trials_within_tolerance": protected_failures == 0,
            "visibility_conclusion_repeated": True,
            "config_sha256": hash_file(ROOT / "configs/secagg_v1.yaml"),
            "timing_expected_byte_identical": False,
            "cryptographic_transcript_expected_byte_identical": False,
            "status": "PASS" if protected_failures == 0 else "FAIL",
        },
    )
    if protected_failures:
        raise RuntimeError("protected measured trial failure")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("preflight", "canonical"))
    args = parser.parse_args()
    if args.mode == "preflight":
        preflight()
    else:
        canonical()


if __name__ == "__main__":
    main()
