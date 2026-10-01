#!/usr/bin/env python3
"""C034 one-command software demo supervisor.

Starts the complete LOCAL software demonstration -- the real production FastAPI backend and
the existing /frontend SvelteKit app (production build + preview, never a second frontend
implementation) -- and prints the exact recorded-replay URL. No GitHub Actions, no cloud, no
physical hardware. Terminates both children cleanly on Ctrl-C or exit.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"


def _verify_locks() -> dict[str, str]:
    from scripts.verify_api_runtime_t032 import verify as verify_api_runtime
    from scripts.verify_dashboard_ui_c034 import verify as verify_dashboard_ui_c034

    # NOTE(bootstrap): the E2E_REPLAY_SOFTWARE_V1_1 successor lock binds THIS audit's own
    # output file, so it cannot be verified by the very run that produces it. It is verified
    # separately, immediately after, by `make replay-verify-c034` / CI gate reuse.
    return {
        "api_runtime_v1": verify_api_runtime()["status"],
        "dashboard_ui_v1_1": verify_dashboard_ui_c034()["status"],
    }


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _wait_for_http(url: str, *, timeout_seconds: float) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2.0) as response:
                if response.status < 500:
                    return True
        except Exception:
            time.sleep(0.2)
    return False


@contextlib.contextmanager
def _child_process(cmd: list[str], *, cwd: Path, env: dict[str, str] | None = None):
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    process = subprocess.Popen(
        cmd,
        cwd=cwd,
        env=full_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        yield process
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def run(*, speed: int, backend_timeout: float, frontend_timeout: float) -> dict[str, object]:
    lock_status = _verify_locks()
    if any(status != "PASS" for status in lock_status.values()):
        raise RuntimeError(f"C034_DEMO_LOCK_VERIFICATION_FAILED:{lock_status}")

    backend_port = _free_port()
    frontend_port = _free_port()

    env = os.environ.copy()
    env["PYTHONPATH"] = "src:."

    result: dict[str, object] = {
        "lock_status": lock_status,
        "backend_port": backend_port,
        "frontend_port": frontend_port,
    }

    backend_cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "api.app:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(backend_port),
    ]
    with _child_process(backend_cmd, cwd=ROOT, env={"PYTHONPATH": "src:."}):
        backend_ready = _wait_for_http(
            f"http://127.0.0.1:{backend_port}/openapi.json", timeout_seconds=backend_timeout
        )
        result["backend_ready"] = backend_ready
        if not backend_ready:
            raise RuntimeError("C034_DEMO_BACKEND_FAILED_TO_START")

        subprocess.run(
            ["npm", "run", "build"], cwd=FRONTEND, check=True, capture_output=True, text=True
        )

        preview_cmd = [
            "npm",
            "run",
            "preview",
            "--",
            "--host",
            "127.0.0.1",
            "--port",
            str(frontend_port),
            "--strictPort",
        ]
        with _child_process(
            preview_cmd, cwd=FRONTEND, env={"NHM_API_PORT": str(backend_port)}
        ):
            frontend_ready = _wait_for_http(
                f"http://127.0.0.1:{frontend_port}/", timeout_seconds=frontend_timeout
            )
            result["frontend_ready"] = frontend_ready
            if not frontend_ready:
                raise RuntimeError("C034_DEMO_FRONTEND_FAILED_TO_START")

            replay_url = (
                f"http://127.0.0.1:{frontend_port}/monitoring"
                f"?mode=replay&replay=PUBLIC_ECG_REPLAY_V1&speed={speed}"
            )
            result["recorded_replay_url"] = replay_url
            replay_route_reachable = _wait_for_http(replay_url, timeout_seconds=10.0)
            result["replay_route_reachable"] = replay_route_reachable

            print(json.dumps(result, indent=2, sort_keys=True))
            print(f"\nRecorded replay URL: {replay_url}\n")

            if os.environ.get("C034_DEMO_HOLD_OPEN") == "1":
                print("Press Ctrl-C to stop (backend + frontend).")
                try:
                    while True:
                        time.sleep(1)
                except KeyboardInterrupt:
                    pass

    result["status"] = "PASS" if result.get("frontend_ready") else "FAIL"
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--speed", type=int, default=0, choices=[0, 1])
    parser.add_argument("--backend-timeout", type=float, default=30.0)
    parser.add_argument("--frontend-timeout", type=float, default=60.0)
    parser.add_argument("--audit-out", default=None)
    args = parser.parse_args()

    result = run(
        speed=args.speed,
        backend_timeout=args.backend_timeout,
        frontend_timeout=args.frontend_timeout,
    )
    if args.audit_out:
        Path(args.audit_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.audit_out).write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
