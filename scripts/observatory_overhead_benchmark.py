# ruff: noqa: E501
"""Measured diagnostic overhead of the Observatory capture (monitoring side). Observations only.
  python -m scripts.observatory_overhead_benchmark --out reports/observatory/overhead_benchmark.json [--repeats 5]
Compares the canonical WearableStreamRuntime ingesting a full frozen scenario with and without the armed LiveWindowCapture observer, on the same machine in the same process. Federation sidecar cost is not benchmarked here."""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import time
from pathlib import Path

from product.devices.scenarios import load_scenarios
from product.observatory.live_capture import LiveWindowCapture
from simulation.profile_v2013 import iter_observed_records
from simulation.stream_runtime_v2013 import CHUNK_RECORDS, WearableStreamRuntime


def run(scenario, capture: bool) -> tuple[float, int]:
    runtime = WearableStreamRuntime(session_id="BENCH", model_id="MODEL_V2_FINAL", replay_id="BENCH")
    if capture:
        LiveWindowCapture(runtime, scenario_id=scenario.scenario_id, session_id="BENCH", window_index=3)
    emitted, batch = 0, []
    start = time.perf_counter()
    for record in iter_observed_records(scenario.profile()):
        batch.append(record)
        if len(batch) == CHUNK_RECORDS:
            emitted += len(runtime.ingest(batch))
            batch = []
    if batch:
        emitted += len(runtime.ingest(batch))
    return time.perf_counter() - start, emitted


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--repeats", type=int, default=5)
    args = ap.parse_args()
    scenario = load_scenarios()["NORMAL_MONITORING"]
    run(scenario, False)   # warm-up
    plain, observed, windows = [], [], 0
    for _ in range(args.repeats):
        seconds, windows = run(scenario, False)
        plain.append(seconds)
        seconds, observed_windows = run(scenario, True)
        observed.append(seconds)
        assert observed_windows == windows, "capture changed the number of emitted windows"
    report = {"scenario": scenario.scenario_id, "source_duration_s": scenario.duration_s, "windows_emitted": windows, "repeats": args.repeats,
              "plain_seconds": plain, "with_capture_seconds": observed,
              "median_plain_s": statistics.median(plain), "median_with_capture_s": statistics.median(observed),
              "median_overhead_pct": round((statistics.median(observed) / statistics.median(plain) - 1) * 100, 2),
              "machine": f"{platform.system()} {platform.machine()} Python {platform.python_version()}",
              "note": "Wall-clock of canonical ingestion of simulated source; capture is opt-in and bounded to one window. Not a latency claim for any deployment."}
    Path(args.out).write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps({k: report[k] for k in ("median_plain_s", "median_with_capture_s", "median_overhead_pct")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
