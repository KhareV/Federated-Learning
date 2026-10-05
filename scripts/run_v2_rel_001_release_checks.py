#!/usr/bin/env python3
"""V2-REL-001 release checks that need real processes. Every sub-command writes ONE JSON evidence
file to --out and exits non-zero on FAIL. No scientific metric, no real dataset.

  default-replay   V2 simulated-wearable replay (original + exact-zero flatline) through the DEFAULT
                   launcher (python -m scripts.run_nhm_default) + the real default-built frontend
  rollback-replay  small deterministic V1 replay through the explicit rollback profile (2 processes)
  isolation        default and rollback processes side by side; no state/identity cross-over
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
V2013_DIGEST_PREFIX = "7ef39ae9"


def _write(out: str, data: dict[str, Any]) -> None:
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"check": path.stem, "status": data["status"]}))
    if data["status"] != "PASS":
        sys.exit(1)


@contextlib.contextmanager
def launch(profile: str, *, timeout: float = 240.0):
    """Start the documented launcher (python -m scripts.run_nhm_default) in a FRESH process."""
    import scripts._v2_013_lib as lib

    port = lib.free_port()
    cmd = [sys.executable, "-m", "scripts.run_nhm_default", "--profile", profile, "--port",
           str(port)]
    process = subprocess.Popen(cmd, cwd=ROOT, env=dict(os.environ), stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True)
    try:
        base = f"http://127.0.0.1:{port}"
        if not lib._wait(f"{base}/openapi.json", timeout):
            raise RuntimeError(f"RELEASE_LAUNCH_FAILED:{profile}")
        yield base, process.pid
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGTERM)
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def _body(event: dict[str, Any], session: str, model_id: str | None = None) -> dict[str, Any]:
    return {"contract_version": "API_SCHEMA_V1", "session_id": session,
            "timestamp_us": event["timestamp_us"], "ecg": event["ecg"],
            "ecg_quality": event["ecg_quality"], "ppg_context": event["ppg_context"],
            "model_id": model_id or event["model_id"]}


def default_replay(out: str) -> None:
    out_dir = Path(out).parent / "default_replay_raw"
    out_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, Any] = {}
    for kind in ("v2013", "flatline"):
        target = out_dir / kind
        target.mkdir(parents=True, exist_ok=True)
        script = (
            "import os,sys,types\n"
            f"os.environ['V2_013_OUT']={str(target)!r}\n"
            "import scripts.release_default_replay_driver as d\n"
            f"d.main({kind!r})\n")
        proc = subprocess.run([sys.executable, "-c", script], cwd=ROOT, capture_output=True,
                              text=True)
        results[kind] = {"exit_code": proc.returncode, "stdout_tail": proc.stdout[-400:],
                         "stderr_tail": proc.stderr[-600:]}
        sys.stdout.write(f"[{proc.returncode}] default replay {kind}\n")
    from scripts import v2_014_clone_checks as checks

    comparisons = {}
    for kind in ("v2013", "flatline"):
        file = str(Path(out).parent / f"default_replay_compare_{kind}.json")
        with contextlib.suppress(SystemExit):
            checks.check_replay_compare(file, kind, str(out_dir / kind))
        path = Path(file)
        comparisons[kind] = json.loads(path.read_text()) if path.exists() else {"status": "FAIL"}
    e2e = {}
    path = out_dir / "v2013" / "frontend_e2e_evidence.json"
    if path.exists():
        data = json.loads(path.read_text())
        e2e = {"status": data["status"], "identities_rendered": data["identities_rendered"],
               "waveform": data["waveform"], "build": data["frontend_build"],
               "runs": [{"monitoring_route_http_status": r["monitoring_route_http_status"]}
                        for r in data["runs"]]}
    tiles = json.dumps(e2e.get("identities_rendered", {}))
    ok = (all(r["exit_code"] == 0 for r in results.values())
          and all(c.get("status") == "PASS" for c in comparisons.values())
          and e2e.get("status") == "PASS" and "MODEL_V2_FINAL" in tiles and "CAL_V2" in tiles
          and e2e.get("build", {}).get("built_default_request_model_id", {}).get(
              "default_is_MODEL_V2_FINAL") is True)
    _write(out, {"launch_path": "python -m scripts.run_nhm_default (default profile)",
                 "research_launcher_used": False, "runs": results, "comparisons": comparisons,
                 "frontend_e2e": e2e, "scientific_metrics": False, "real_waveform_dataset": False,
                 "status": "PASS" if ok else "FAIL"})


def rollback_replay(out: str) -> None:
    events = sorted(json.loads((ROOT / "frontend/static/replay/PUBLIC_ECG_REPLAY_V1.json"
                                ).read_text())["events"], key=lambda e: e["sequence_index"])
    runs = []
    for index in (1, 2):
        rows = []
        with launch("rollback-v1") as (base, pid), httpx.Client() as client:
            for event in events:
                response = client.post(f"{base}/v1/infer-window",
                                       json=_body(event, f"rb-{index}"), timeout=60.0)
                body = response.json()
                rows.append({"window_id": event["window_id"], "http_status": response.status_code,
                             "model_id": body.get("model_id"),
                             "calibration_id": body.get("calibration_id"),
                             "monitoring_state": body.get("monitoring_state"),
                             "preprocess_version": body.get("preprocess_version"),
                             "alert_policy_id": body.get("alert_policy_id"),
                             "raw_probability": body.get("raw_probability")})
            openapi = client.get(f"{base}/openapi.json").json()
        runs.append({"pid": pid, "rows": rows, "title": openapi["info"]["title"]})
    ok_rows = [r for r in runs[0]["rows"] if r["http_status"] == 200]
    ids = {(r["model_id"], r["calibration_id"], r["preprocess_version"], r["alert_policy_id"])
           for r in ok_rows}
    identical = runs[0]["rows"] == runs[1]["rows"]
    ok = (identical and runs[0]["pid"] != runs[1]["pid"] and ok_rows
          and ids == {("MODEL_V1", "CAL_V1", "PREPROC_V1", "ALERT_POLICY_V1")}
          and all(r["http_status"] in (200, 422) for r in runs[0]["rows"]))
    _write(out, {"launch_path": "python -m scripts.run_nhm_default --profile rollback-v1",
                 "windows": len(events), "http_statuses": sorted({
                     r["http_status"] for r in runs[0]["rows"]}),
                 "identities": sorted(map(list, ids)),
                 "states": [r["monitoring_state"] for r in runs[0]["rows"]],
                 "two_fresh_processes_identical": identical, "gateway": "GATEWAY_ARTIFACT_V1",
                 "new_v1_science": False, "status": "PASS" if ok else "FAIL"})


def isolation(out: str) -> None:
    v2 = sorted(json.loads((ROOT / "frontend/static/replay/WEARABLE_SIM_V2_REPLAY_V1.json"
                            ).read_text())["events"], key=lambda e: e["sequence_index"])
    v1 = sorted(json.loads((ROOT / "frontend/static/replay/PUBLIC_ECG_REPLAY_V1.json").read_text()
                           )["events"], key=lambda e: e["sequence_index"])
    with launch("default") as (a, pid_a), launch("rollback-v1") as (b, pid_b), httpx.Client() as c:
        first_a = c.post(f"{a}/v1/infer-window", json=_body(v2[0], "shared", "MODEL_V2_FINAL"))
        first_b = c.post(f"{b}/v1/infer-window", json=_body(v1[0], "shared", "MODEL_V1"))
        replay_a = c.post(f"{a}/v1/infer-window", json=_body(v2[0], "shared", "MODEL_V2_FINAL"))
        later_b = c.post(f"{b}/v1/infer-window", json=_body(v1[1], "shared", "MODEL_V1"))
        cross_a = c.post(f"{a}/v1/infer-window", json=_body(v2[1], "shared2", "MODEL_V1"))
        cross_b = c.post(f"{b}/v1/infer-window", json=_body(v1[1], "shared2", "MODEL_V2_FINAL"))
    checks = {
        "different_processes": pid_a != pid_b,
        "default_identity": first_a.status_code in (200, 422) and (
            first_a.status_code == 422 or (first_a.json()["model_id"] == "MODEL_V2_FINAL"
            and first_a.json()["calibration_id"] == "CAL_V2")),
        "rollback_identity": first_b.status_code in (200, 422) and (
            first_b.status_code == 422 or (first_b.json()["model_id"] == "MODEL_V1"
            and first_b.json()["calibration_id"] == "CAL_V1")),
        "default_session_state_independent_nonmonotonic": replay_a.status_code == 400
        and replay_a.json()["error_type"] == "NON_MONOTONIC_TIMESTAMP",
        "rollback_session_unaffected_by_default_session": later_b.status_code in (200, 422),
        "default_rejects_v1_model_id": cross_a.status_code == 400
        and cross_a.json()["error_type"] == "UNSUPPORTED_MODEL_ID",
        "rollback_rejects_v2_model_id": cross_b.status_code == 400
        and cross_b.json()["error_type"] == "UNSUPPORTED_MODEL_ID"}
    _write(out, {"checks": checks, "status": "PASS" if all(checks.values()) else "FAIL"})


def frontend(out: str) -> None:
    """Frontend unit tests, svelte-check and the DEFAULT production build (no env override)."""
    import re

    fe = ROOT / "frontend"
    env = {k: v for k, v in os.environ.items() if k != "VITE_NHM_REQUEST_MODEL_ID"}
    steps = {name: subprocess.run(cmd, cwd=fe, env=env, capture_output=True, text=True)
             for name, cmd in (("test", ["npm", "test"]), ("check", ["npm", "run", "check"]),
                               ("build", ["npm", "run", "build"]))}
    tests = re.search(r"Tests\s+(\d+) passed(?: \| (\d+) skipped)?", steps["test"].stdout)
    errors = re.search(r"svelte-check found (\d+) errors and (\d+) warnings",
                       steps["check"].stdout + steps["check"].stderr) or re.search(
        r"COMPLETED \d+ FILES (\d+) ERRORS (\d+) WARNINGS",
        steps["check"].stdout + steps["check"].stderr)
    built = "".join(p.read_text(encoding="utf-8", errors="ignore")
                    for p in (fe / "build").rglob("*.js"))
    data = {"vitest_exit": steps["test"].returncode,
            "vitest_tests_passed": int(tests.group(1)) if tests else None,
            "vitest_tests_skipped": int(tests.group(2) or 0) if tests else None,
            "svelte_check_exit": steps["check"].returncode,
            "svelte_check_errors": int(errors.group(1)) if errors else None,
            "svelte_check_warnings": int(errors.group(2)) if errors else None,
            "build_exit": steps["build"].returncode,
            "default_build_requests_MODEL_V2_FINAL": "MODEL_V2_FINAL" in built,
            "no_hardcoded_MODEL_V1_request": "model_id:\"MODEL_V1\"" not in built,
            "request_env_override_used": False}
    ok = (data["vitest_exit"] == 0 and data["svelte_check_exit"] == 0
          and data["svelte_check_errors"] == 0 and data["build_exit"] == 0
          and data["default_build_requests_MODEL_V2_FINAL"]
          and data["no_hardcoded_MODEL_V1_request"])
    _write(out, {**data, "status": "PASS" if ok else "FAIL"})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("check", choices=("default-replay", "rollback-replay", "isolation",
                                           "frontend"))
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    {"default-replay": default_replay, "rollback-replay": rollback_replay,
     "isolation": isolation, "frontend": frontend}[args.check](args.out)


if __name__ == "__main__":
    main()
