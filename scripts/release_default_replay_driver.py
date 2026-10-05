"""V2-REL-001 replay driver: runs the repository's V2-013 replay orchestrator with the API launched
through the DEFAULT launcher (python -m scripts.run_nhm_default) and the frontend built with its
DEFAULT request identity (VITE_NHM_REQUEST_MODEL_ID unset). The research launcher is never used.
V2_013_OUT must be set before import."""

from __future__ import annotations

import contextlib
import json
import os
import signal
import subprocess
import sys
import types

import scripts._v2_013_lib as lib
import scripts.run_v2_013_replay as rep

ROOT = lib.ROOT


@contextlib.contextmanager
def launch_default(profile: str, *, port: int | None = None, timeout: float = 240.0):
    del profile  # the default launcher is the only launch path used here
    port = port or lib.free_port()
    process = subprocess.Popen(
        [sys.executable, "-m", "scripts.run_nhm_default", "--port", str(port)], cwd=ROOT,
        env=dict(os.environ), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        base = f"http://127.0.0.1:{port}"
        if not lib._wait(f"{base}/openapi.json", timeout):
            raise RuntimeError("RELEASE_DEFAULT_LAUNCH_FAILED")
        yield base, process.pid
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGTERM)
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def build_default_frontend() -> dict:
    env = {k: v for k, v in os.environ.items() if k != "VITE_NHM_REQUEST_MODEL_ID"}
    result = subprocess.run(["npm", "run", "build"], cwd=rep.FRONTEND, env=env, capture_output=True,
                            text=True, check=True)
    text = ""
    for path in (rep.FRONTEND / "build").rglob("*.js"):
        text += path.read_text(encoding="utf-8", errors="ignore")
    return {
        "build_exit_code": result.returncode,
        "request_model_id_build_config": "VITE_NHM_REQUEST_MODEL_ID UNSET (default build)",
        "v1_specific_strings_absent_from_built_bundle": {
            s: s not in text for s in rep.FORBIDDEN_V1_STRINGS},
        "model_neutral_strings_present_in_built_bundle": {
            s: s in text for s in rep.REQUIRED_GENERIC_STRINGS},
        "built_default_request_model_id": {
            "default_is_MODEL_V2_FINAL": "MODEL_V2_FINAL" in text,
            "no_hardcoded_MODEL_V1_request": "model_id:\"MODEL_V1\"" not in text
            and "model_id:'MODEL_V1'" not in text}}


def main(kind: str) -> None:
    lib.launch_api = launch_default
    rep._build_frontend = build_default_frontend
    if kind == "flatline":
        import simulation.flatline_scenario_c_v2_013 as scen

        rep.REPLAY_ID = "WEARABLE_SIM_V2_REPLAY_V2_FLATLINE"
        rep.BUNDLE = rep.ROOT / "frontend/static/replay/WEARABLE_SIM_V2_REPLAY_V2_FLATLINE.json"
        rep.prof = types.SimpleNamespace(
            LIVE_EXCERPT_PROFILE=scen.EXCERPT_FLATLINE_PROFILE,
            iter_observed_records=scen.iter_flatline_records)
    try:
        rep.main()
    except SystemExit as exit_info:
        print("replay orchestrator exit:", exit_info)
    print(json.dumps({"kind": kind, "out": str(lib.OUT)}))
