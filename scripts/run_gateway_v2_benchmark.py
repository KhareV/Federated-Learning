#!/usr/bin/env python3
"""V2-012 CPU resource benchmark (frozen method): 3 repetitions, each in a fresh subprocess
(100 warm-up calls excluded, then exactly 1000 measured batch-1 calls on the synthetic parity
corpus), interleaved with the frozen GATEWAY_ARTIFACT_V1 under the identical process policy for
a descriptive same-host engineering comparison. Aggregation (median of 3 / max RSS) is
predeclared in configs/model_v2/gateway_artifact_v2.yaml; the fastest run is never chosen.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

from deployment import gateway_v2 as gw
from deployment.benchmark import configure_cpu_threads, max_rss_bytes, memory_child
from deployment.runtime import GatewayModelRuntime
from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_012"
V1_ARTIFACT = ROOT / "artifacts/deployment/MODEL_V1_GATEWAY_FP32.ts"
V1_LOCK = ROOT / "artifacts/GATEWAY_ARTIFACT_V1.lock.json"


def _spawn(*args: str) -> dict:
    result = subprocess.run([sys.executable, str(Path(__file__).resolve()), *args], cwd=ROOT,
                            check=True, capture_output=True, text=True,
                            env={**os.environ, "PYTHONPATH": "src:."})
    return json.loads(result.stdout)


def child_latency(gateway: str, repetition: int) -> None:
    configure_cpu_threads()
    windows = gw.load_parity_corpus(ROOT)
    runtime = (gw.GatewayV2Runtime(ROOT, verify="export_audit") if gateway == "v2"
               else GatewayModelRuntime(ROOT, V1_ARTIFACT))
    latencies = gw.run_timed_loop(runtime, windows)
    summary = gw.percentile_summary(latencies)
    print(json.dumps({
        "gateway": gateway, "repetition": repetition, "warmup_count": gw.WARMUP,
        "measured_count": len(latencies), "latencies_ns": latencies, **summary,
        "benchmark_process_peak_RSS_bytes": max_rss_bytes(),
        "intraop_threads": __import__("torch").get_num_threads(),
        "interop_threads": __import__("torch").get_num_interop_threads(),
    }))


def child_memory(gateway: str, window_path: Path) -> None:
    out = (gw.memory_child_v2(ROOT, window_path) if gateway == "v2"
           else memory_child(ROOT, V1_ARTIFACT, window_path))
    print(json.dumps(out, sort_keys=True))


def _stats(run: dict) -> dict:
    keys = ("gateway", "repetition", "warmup_count", "measured_count", "mean_ms", "p50_ms",
            "p95_ms", "p99_ms", "minimum_ms", "maximum_ms", "standard_deviation_ms",
            "total_timed_seconds", "throughput_windows_per_second",
            "benchmark_process_peak_RSS_bytes")
    return {k: run[k] for k in keys}


def canonical() -> None:
    configure_cpu_threads()
    cfg_path = ROOT / "configs/model_v2/gateway_artifact_v2.yaml"
    if not (OUT / "synthetic_corpus_parity_summary.json").exists():
        raise RuntimeError("V2_012_PARITY_MUST_PRECEDE_BENCHMARK")
    if hash_file(V1_ARTIFACT) != json.loads(V1_LOCK.read_text())["bound_artifacts"][
            "artifacts/deployment/MODEL_V1_GATEWAY_FP32.ts"]:
        raise RuntimeError("V2_012_V1_GATEWAY_ARTIFACT_NOT_FROZEN_HASH")
    runs = []
    for repetition in range(1, gw.REPETITIONS + 1):
        for gateway in ("v2", "v1"):  # interleaved, fresh subprocess each
            runs.append(_spawn("child-latency", "--gateway", gateway,
                               "--repetition", str(repetition)))
    v2_runs = [r for r in runs if r["gateway"] == "v2"]
    v1_runs = [r for r in runs if r["gateway"] == "v1"]

    with (OUT / "benchmark_runs.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(_stats(runs[0])), lineterminator="\n")
        writer.writeheader()
        writer.writerows(_stats(r) for r in runs)
    with (OUT / "benchmark_latency_samples.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["gateway", "repetition", "index", "latency_ns"])
        for r in runs:
            for index, value in enumerate(r["latencies_ns"]):
                writer.writerow([r["gateway"], r["repetition"], index, value])

    host = gw.host_identity()
    run_rows = [_stats(r) for r in v2_runs]
    canonical_agg = gw.aggregate_runs(run_rows)
    (OUT / "benchmark_summary.json").write_text(json.dumps({
        "artifact_sha256": hash_file(ROOT / gw.ARTIFACT_PATH),
        "config_sha256": hash_file(cfg_path),
        "runs": run_rows,
        "canonical": canonical_agg,
        "run_level_p50_ms": [r["p50_ms"] for r in run_rows],
        "run_level_p95_ms": [r["p95_ms"] for r in run_rows],
        "run_level_throughput": [r["throughput_windows_per_second"] for r in run_rows],
        "timing_boundary": "gateway model plus CAL_V2 wrapper inference call",
        "excluded": ["model load", "artifact verification", "warm-up", "CAL file parse"],
        "inputs": "first 1000 windows of GATEWAY_PARITY_CORPUS_V2_V1 (synthetic)",
        "batch_size": 1, "threads": {"intraop": 1, "interop": 1},
        "throughput_scope": "single-process model-inference throughput; not multi-user API "
        "throughput",
        "performance_target_invented": False,
        "host": host, "status": "PASS",
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    windows = gw.load_parity_corpus(ROOT)
    memory = {"v2": [], "v1": []}
    with tempfile.TemporaryDirectory() as tmp:
        window_path = Path(tmp) / "window.npy"
        np.save(window_path, windows[0:1])
        for _ in range(gw.REPETITIONS):
            for gateway in ("v2", "v1"):
                memory[gateway].append(_spawn("child-memory", "--gateway", gateway,
                                              "--window", str(window_path)))
    (OUT / "memory_benchmark.json").write_text(json.dumps({
        "semantics": "peak/high-water process RSS during benchmark process",
        "not": ["instantaneous RAM", "device RAM", "MCU RAM"],
        "method": "fresh subprocess resource.getrusage(RUSAGE_SELF).ru_maxrss",
        "platform_unit_handling": "macOS ru_maxrss treated as bytes; Linux as KiB",
        "benchmark_process_peak_RSS_bytes_per_run": [r["benchmark_process_peak_RSS_bytes"]
                                                     for r in run_rows],
        "canonical_peak_high_water_process_RSS_bytes": canonical_agg[
            "peak_high_water_process_RSS_bytes"],
        "single_window_child_runs_v2": memory["v2"],
        "status": "PASS",
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    v1_cfg = json.loads((ROOT / "reports/t029/model_size.json").read_text())
    v1_rows = [_stats(r) for r in v1_runs]
    v1_agg = gw.aggregate_runs(v1_rows)
    export_audit = json.loads((OUT / "export_audit.json").read_text())
    (OUT / "matched_v1_v2_gateway_benchmark.json").write_text(json.dumps({
        "policy": "engineering-only, descriptive, same host and process policy, interleaved fresh "
        "subprocesses on the same synthetic inputs; not used for model choice; no MODEL_V1 "
        "scientific evaluation was rerun",
        "v1_available": True,
        "v1_artifact_sha256_matches_frozen_lock": True,
        "v1_artifact_bytes": V1_ARTIFACT.stat().st_size,
        "v2_artifact_bytes": export_audit["artifact_bytes"],
        "v1_trainable_parameters": v1_cfg["trainable_parameter_count"],
        "v2_trainable_parameters": export_audit["trainable_parameter_count"],
        "v1_runs": v1_rows, "v2_runs": run_rows,
        "v1_canonical": v1_agg, "v2_canonical": canonical_agg,
        "v1_single_window_child_runs": memory["v1"],
        "ratios_v2_over_v1": {
            "artifact_bytes": export_audit["artifact_bytes"] / V1_ARTIFACT.stat().st_size,
            "p50": canonical_agg["canonical_p50_ms"] / v1_agg["canonical_p50_ms"],
            "p95": canonical_agg["canonical_p95_ms"] / v1_agg["canonical_p95_ms"],
            "throughput": canonical_agg["canonical_throughput_windows_per_second"]
            / v1_agg["canonical_throughput_windows_per_second"],
            "peak_rss": canonical_agg["peak_high_water_process_RSS_bytes"]
            / v1_agg["peak_high_water_process_RSS_bytes"],
        },
        "caveats": [
            "same-host, same-process-policy engineering benchmark only",
            "V2 wrapper applies CAL_V2 through the canonical helpers while the frozen V1 runtime "
            "uses inline math; both are inside the timed boundary",
            "V1 historical T029 numbers (reports/t029) were measured on INTERNAL_TEST windows in a "
            "different session; this comparison is contemporaneous",
        ],
        "host": host, "status": "PASS",
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"v2_canonical": canonical_agg}, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("canonical", "child-latency", "child-memory"))
    parser.add_argument("--gateway", choices=("v1", "v2"))
    parser.add_argument("--repetition", type=int, default=0)
    parser.add_argument("--window", type=Path)
    args = parser.parse_args()
    if args.mode == "child-latency":
        child_latency(args.gateway, args.repetition)
    elif args.mode == "child-memory":
        child_memory(args.gateway, args.window)
    else:
        canonical()


if __name__ == "__main__":
    main()
