"""CPU gateway latency, throughput, memory, and equivalence helpers."""

from __future__ import annotations

import math
import resource
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch

from deployment.runtime import GatewayModelRuntime


def configure_cpu_threads() -> None:
    torch.set_num_threads(1)
    try:
        torch.set_num_interop_threads(1)
    except RuntimeError:
        if torch.get_num_interop_threads() != 1:
            raise


def latency_summary(latencies_ns: list[int]) -> dict[str, float | int]:
    if len(latencies_ns) != 1000 or any(value <= 0 for value in latencies_ns):
        raise ValueError("canonical latency benchmark requires 1000 positive samples")
    values = np.asarray(latencies_ns, dtype=np.float64) / 1e6
    total_seconds = float(np.sum(latencies_ns) / 1e9)
    return {
        "N": 1000,
        "mean_ms": float(np.mean(values)),
        "p50_ms": float(np.percentile(values, 50)),
        "p95_ms": float(np.percentile(values, 95)),
        "p99_ms": float(np.percentile(values, 99)),
        "minimum_ms": float(np.min(values)),
        "maximum_ms": float(np.max(values)),
        "standard_deviation_ms": float(np.std(values, ddof=1)),
        "total_timed_seconds": total_seconds,
        "throughput_windows_per_second": 1000 / total_seconds,
    }


def run_latency(
    runtime: GatewayModelRuntime, windows: np.ndarray, window_ids: list[str]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if windows.shape != (1000, 1, 2500) or len(window_ids) != 1000:
        raise ValueError("benchmark input closure failure")
    for index in range(100):
        runtime.infer(windows[index % 1000 : index % 1000 + 1])
    rows: list[dict[str, Any]] = []
    for index, (window, window_id) in enumerate(zip(windows, window_ids, strict=True)):
        start = time.perf_counter_ns()
        result = runtime.infer(window[None, :, :])
        elapsed = time.perf_counter_ns() - start
        rows.append(
            {
                "index": index,
                "window_id": window_id,
                "latency_ns": elapsed,
                "latency_ms": elapsed / 1e6,
                "finite_output": math.isfinite(result.raw_logit),
                "above_threshold": result.above_threshold,
            }
        )
    return rows, latency_summary([int(row["latency_ns"]) for row in rows])


def max_rss_bytes() -> int:
    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    # macOS reports bytes; Linux reports KiB.
    return value if sys.platform == "darwin" else value * 1024


def memory_child(root: Path, artifact: Path, window_path: Path) -> dict[str, Any]:
    configure_cpu_threads()
    baseline = max_rss_bytes()
    runtime = GatewayModelRuntime(root, artifact)
    post_load = max_rss_bytes()
    window = np.load(window_path, allow_pickle=False).astype(np.float32, copy=False)
    runtime.infer(window)
    pre_inference = max_rss_bytes()
    runtime.infer(window)
    peak = max_rss_bytes()
    post = max_rss_bytes()
    return {
        "method": "fresh child process resource.getrusage(RUSAGE_SELF).ru_maxrss",
        "platform_unit_handling": "macOS ru_maxrss treated as bytes; Linux as KiB",
        "baseline_process_RSS_bytes": baseline,
        "post_model_load_RSS_bytes": post_load,
        "pre_inference_RSS_bytes": pre_inference,
        "peak_inference_RSS_bytes": peak,
        "post_inference_RSS_bytes": post,
        "peak_minus_pre_inference_bytes": peak - pre_inference,
        "peak_minus_baseline_bytes": peak - baseline,
    }
