# ruff: noqa: E501
"""Audit: the Observatory's reconstructed model input equals what the released runtime feeds MODEL_V2_FINAL.

For several windows of a real owned monitoring session (real inference service, DEMO identity, isolated temp DB):
  1. persisted raw/calibrated probabilities come from the product backend's actual inference call;
  2. the SAME canonical window is re-derived locally and passed through the real ResearchRuntimeV2 (per-window z-score -> gateway -> CAL_V2);
  3. outputs must agree to 1e-5, and the reconstructed tensor digest must equal the locally computed one.
Records observations only: python -m scripts.observatory_gateway_parity --out reports/observatory/gateway_parity_audit.json"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
import numpy as np

from api.runtime_v2 import ResearchRuntimeV2
from preprocessing.windowing import NORMALIZATION_EPSILON, normalize_window_zscore
from product.devices.scenarios import load_scenarios
from product.observatory.pipeline import canonical_emitted_window

ROOT = Path(__file__).resolve().parents[1]
H = {"X-Demo-User": "parity_user"}


def wait(url: str, timeout: float = 120) -> None:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            if httpx.get(url, headers=H, timeout=3).status_code == 200:
                return
        except httpx.HTTPError:
            time.sleep(1)
    raise RuntimeError(f"NOT_READY:{url}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--windows", type=int, default=4)
    args = ap.parse_args()
    work = Path(tempfile.mkdtemp(prefix="obs-parity-"))
    env = {**os.environ, "PYTHONPATH": "src:.", "NHM_PRODUCT_AUTH_MODE": "DEMO", "NHM_PRODUCT_DEMO_AUTH_ACK": "I_UNDERSTAND_THIS_IS_NOT_CLERK",
           "NHM_PRODUCT_DB_PATH": str(work / "p.sqlite3"), "NHM_FEDERATION_ARTIFACT_ROOT": str(work / "fed"), "NHM_FL_CANDIDATE_ROOT": str(work / "cand"),
           "NHM_PRODUCT_INFERENCE_URL": "http://127.0.0.1:8031"}
    infer = subprocess.Popen([sys.executable, "-m", "scripts.run_nhm_default", "--profile", "default", "--host", "127.0.0.1", "--port", "8031"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    api = subprocess.Popen([sys.executable, "-m", "scripts.run_observatory_product", "--port", "8032"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        base = "http://127.0.0.1:8032/product/v1"
        wait(f"{base}/system")
        end = time.monotonic() + 180
        while time.monotonic() < end:   # the inference service exposes only POST /v1/infer-window: wait for its port
            with socket.socket() as probe:
                probe.settimeout(1)
                if probe.connect_ex(("127.0.0.1", 8031)) == 0:
                    break
            time.sleep(1)
        else:
            raise RuntimeError("INFERENCE_SERVICE_NOT_READY")
        scenario = "NORMAL_MONITORING"
        d = httpx.post(f"{base}/devices/simulated", headers=H, json={"scenario_id": scenario}, timeout=30).json()["device_id"]
        for step in ("scan", "connect"):
            httpx.post(f"{base}/devices/{d}/{step}", headers=H, timeout=30)
        sid = httpx.post(f"{base}/sessions", headers=H, json={"device_id": d, "scenario_id": scenario}, timeout=30).json()["session_id"]
        httpx.post(f"{base}/sessions/{sid}/start", headers=H, timeout=30)
        for _ in range(240):
            state = httpx.get(f"{base}/sessions/{sid}", headers=H, timeout=30).json()["state"]
            if state in {"COMPLETED", "FAILED"}:
                break
            time.sleep(1)
        runtime = ResearchRuntimeV2(verify="full")
        spec = load_scenarios()[scenario]
        rows = []
        for index in range(args.windows):
            response = httpx.get(f"{base}/observatory/sessions/{sid}/windows/{index}", headers=H, timeout=120)
            if response.status_code != 200:
                raise RuntimeError(f"TRACE_REQUEST_FAILED:{response.status_code}:{response.text[:300]}:{state}")
            trace = response.json()
            persisted = trace.get("persisted_inference")
            window = canonical_emitted_window(spec, index)
            samples = np.asarray(window["ecg"]["samples"], dtype=np.float64)
            normalized = normalize_window_zscore(samples, epsilon=NORMALIZATION_EPSILON).astype(np.float32).reshape(1, 2500)
            local_digest = hashlib.sha256(np.ascontiguousarray(normalized).tobytes()).hexdigest()
            outcome = runtime.infer(list(samples))
            row = {"window_index": index, "quality": trace["quality_state"], "tensor_digest_matches_trace": local_digest == trace["normalization"]["tensor_sha256"],
                   "persisted_present": persisted is not None}
            if persisted and persisted.get("raw_probability") is not None:
                row.update({"persisted_raw_probability": persisted["raw_probability"], "runtime_raw_probability": outcome.raw_probability,
                            "raw_abs_diff": abs(persisted["raw_probability"] - outcome.raw_probability),
                            "persisted_calibrated": persisted["source_domain_calibrated_probability"], "runtime_calibrated": outcome.source_domain_calibrated_probability,
                            "calibrated_abs_diff": abs(persisted["source_domain_calibrated_probability"] - outcome.source_domain_calibrated_probability),
                            "model_id": persisted["model_id"]})
            rows.append(row)
        compared = [r for r in rows if "raw_abs_diff" in r]
        report = {"status": "PASS" if compared and all(r["raw_abs_diff"] < 1e-5 and r["calibrated_abs_diff"] < 1e-5 and r["tensor_digest_matches_trace"] for r in compared) else "FAIL",
                  "scenario": scenario, "session_state": state, "windows_compared": len(compared), "rows": rows,
                  "note": "The persisted result comes from the product backend calling the inference service; the local result calls ResearchRuntimeV2 directly on the independently re-derived canonical window. Agreement shows the reconstructed model input is the runtime's input; it is not a new scientific evaluation."}
        Path(args.out).write_text(json.dumps(report, indent=1) + "\n")
        print(json.dumps({k: report[k] for k in ("status", "windows_compared")}))
        return 0 if report["status"] == "PASS" else 1
    finally:
        for proc in (api, infer):
            proc.send_signal(signal.SIGINT)
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
