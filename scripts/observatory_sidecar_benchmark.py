# ruff: noqa: E501
"""OBS-DIAG-001 federation sidecar overhead benchmark (one machine, one process per trial; observations only).
Configurations (same synthetic cohort, protocol, machine, code path; only the Observatory observers differ):
  OFF               acceptance sidecar disabled, no per-batch capture
  SIDECAR           direct coordinator-acceptance sidecar enabled (the V1 default)
  SIDECAR_BATCH     sidecar + opt-in per-batch capture
Each trial starts a fresh backend subprocess, runs one complete 8-client / 3-round FedAvg LIVE_RUN over HTTP, and records wall-clock from the start request
to the first COMPLETED poll and the server process peak RSS (os.wait4 ru_maxrss). Trials are interleaved. Outcome equality is verified for every trial.
  python -m scripts.observatory_sidecar_benchmark --out reports/observatory/obs_diag_001/sidecar_benchmark.json --trials 5"""

from __future__ import annotations

import argparse
import json
import os
import platform
import signal
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
H = {"X-Demo-User": "bench_user"}
CONFIGS = {"OFF": {"NHM_OBSERVATORY_ACCEPTANCE_SIDECAR": "0", "NHM_OBSERVATORY_BATCH_CAPTURE": "0"},
           "SIDECAR": {"NHM_OBSERVATORY_ACCEPTANCE_SIDECAR": "1", "NHM_OBSERVATORY_BATCH_CAPTURE": "0"},
           "SIDECAR_BATCH": {"NHM_OBSERVATORY_ACCEPTANCE_SIDECAR": "1", "NHM_OBSERVATORY_BATCH_CAPTURE": "1"}}
BODY = {"run_type": "LIVE_RUN", "algorithm": "FEDAVG", "secagg_mode": "PLAIN", "planned_rounds": 3, "scenario_id": "FL_SINGLE_RUN"}


def trial(name: str, port: int) -> dict:
    work = Path(tempfile.mkdtemp(prefix=f"obsdiag-bench-{name}-"))
    env = {**os.environ, "PYTHONPATH": "src:.", "NHM_PRODUCT_AUTH_MODE": "DEMO", "NHM_PRODUCT_DEMO_AUTH_ACK": "I_UNDERSTAND_THIS_IS_NOT_CLERK",
           "NHM_PRODUCT_DB_PATH": str(work / "p.sqlite3"), "NHM_FEDERATION_ARTIFACT_ROOT": str(work / "fed"), "NHM_FL_CANDIDATE_ROOT": str(work / "cand"),
           "NHM_FEDERATION_AUTO_RESUME": "0", **CONFIGS[name]}
    proc = subprocess.Popen([sys.executable, "-m", "scripts.run_observatory_product", "--port", str(port)], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}/product/v1"
    try:
        for _ in range(180):
            try:
                if httpx.get(f"{base}/system", headers=H, timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.5)
        run_id = httpx.post(f"{base}/federation/runs", headers=H, json=BODY, timeout=60).json()["run_id"]
        started = time.perf_counter()
        httpx.post(f"{base}/federation/runs/{run_id}/start", headers=H, timeout=60)
        while True:
            status = httpx.get(f"{base}/federation/runs/{run_id}", headers=H, timeout=30).json()["status"]
            if status in {"COMPLETED", "FAILED"}:
                break
            time.sleep(0.1)
        seconds = time.perf_counter() - started
        models = httpx.get(f"{base}/models", headers=H, timeout=30).json()["capstone_fl_candidates"][0]
        rounds = httpx.get(f"{base}/federation/runs/{run_id}/rounds", headers=H, timeout=30).json()
        contribution = httpx.get(f"{base}/observatory/federation/runs/{run_id}/contributions", headers=H, timeout=30).json()
        outcome = {"status": status, "candidate_digest": models["state_digest"], "governance": models["governance_status"], "sandbox": models["sandbox_status"], "deployed": models["production_deployed"],
                   "accepted_updates": sum(r["accepted_update_count"] for r in rounds), "accepted_examples": [r["accepted_example_total"] for r in contribution["rounds"]],
                   "update_digests": [[c["update_digest"] for c in r["clients"]] for r in contribution["rounds"]], "committed": [r["committed_state_digest"] for r in contribution["rounds"]]}
    finally:
        proc.send_signal(signal.SIGINT)
        _, _, usage = os.wait4(proc.pid, 0)
    rss = usage.ru_maxrss / (1 if sys.platform == "darwin" else 1024)     # macOS reports bytes, Linux kilobytes
    return {"config": name, "run_wall_seconds": seconds, "server_peak_rss_mb": round(rss / 1_048_576, 1), "outcome": outcome}


def summary(values: list[float]) -> dict:
    return {"n": len(values), "median": statistics.median(values), "mean": statistics.fmean(values), "min": min(values), "max": max(values), "stdev": statistics.stdev(values) if len(values) > 1 else 0.0}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--trials", type=int, default=5)
    ap.add_argument("--port", type=int, default=8061)
    args = ap.parse_args()
    results: list[dict] = []
    names = list(CONFIGS)
    for index in range(args.trials):
        order = names[index % 3:] + names[:index % 3]          # rotate so no configuration is always first
        for name in order:
            results.append(trial(name, args.port))
    by = {n: [r for r in results if r["config"] == n] for n in names}
    reference = by["OFF"][0]["outcome"]
    equal = all(r["outcome"] == reference for r in results)
    report = {"status": "PASS" if equal and all(r["outcome"]["status"] == "COMPLETED" and r["outcome"]["accepted_updates"] == 24 for r in results) else "FAIL",
              "all_trials_identical_outcome": equal, "trials_per_config": args.trials, "protocol": BODY,
              "machine": f"{platform.system()} {platform.machine()} Python {platform.python_version()}, one machine, loopback HTTP, one backend process per trial",
              "wall_seconds": {n: summary([r["run_wall_seconds"] for r in by[n]]) for n in names}, "server_peak_rss_mb": {n: summary([r["server_peak_rss_mb"] for r in by[n]]) for n in names},
              "median_overhead_vs_off_pct": {n: round((statistics.median([r["run_wall_seconds"] for r in by[n]]) / statistics.median([r["run_wall_seconds"] for r in by["OFF"]]) - 1) * 100, 2) for n in names if n != "OFF"},
              "reference_outcome": {k: reference[k] for k in ("candidate_digest", "governance", "sandbox", "deployed", "accepted_updates", "accepted_examples")},
              "trials": [{k: v for k, v in r.items() if k != "outcome"} | {"status": r["outcome"]["status"]} for r in results],
              "limitations": ["One machine and loopback HTTP: these numbers say nothing about network or distributed-deployment performance.", "Wall-clock includes the 100 ms poll granularity; peak RSS covers the whole backend process (imports, runtime, run), so small differences are within noise.",
                              "Synthetic cohort and engineering protocol only; no scientific or latency claim for any deployment."]}
    Path(args.out).write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps({"status": report["status"], "overhead_pct": report["median_overhead_vs_off_pct"], "wall_median": {n: round(report["wall_seconds"][n]["median"], 2) for n in names}, "rss_median": {n: report["server_peak_rss_mb"][n]["median"] for n in names}}))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
