# ruff: noqa: E501
"""CAPSTONE_DEMO_ORCHESTRATOR_V1 -- the ONE governed faculty-demo launcher.

    python -m scripts.run_capstone_faculty_demo --acknowledge-demo-auth [--build] [--prewarm-federation]

Manages exactly the three existing services (it reimplements no product logic):
  A  released inference   python -m scripts.run_nhm_default --profile default     127.0.0.1:8001
  B  product backend      python -m scripts.run_capstone_product_v1_3             127.0.0.1:8002
  C  production frontend  npm run preview (after npm run build)                   127.0.0.1:4173
Responsibilities: preflight, isolated workspace, environment, launch, readiness probing, optional truthful
prewarm, status output, supervision (any child death stops the whole stack), graceful shutdown in reverse
dependency order. It never installs packages, never kills foreign processes and never exposes rollback-v1.
SIMULATION TIMING: ACCELERATED FOR PRESENTATION (pacing only).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import signal
import subprocess
import sys
import time
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from scripts.capstone_demo_preflight import (
    BUILD_STAMP,
    frontend_source_digest,
    port_free,
    run_preflight,
)
from scripts.capstone_demo_workspace import Workspace, WorkspaceError, scan_logs_for_secrets

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
HOST = "127.0.0.1"
DEFAULT_PORTS = {"inference": 8001, "product": 8002, "frontend": 4173}
DEMO_USER_ID = "demo:faculty"
READY_TIMEOUT_S = 300.0
EXIT = {"OK": 0, "REFUSED": 2, "SERVICE_FAILURE": 3, "PORT_IN_USE": 4, "PREFLIGHT_FAILED": 5, "WORKSPACE": 6, "READY_TIMEOUT": 7}


@dataclass
class ServiceSpec:
    name: str
    argv: list[str]
    env: dict[str, str]
    cwd: Path
    log: Path
    ready: Callable[[], tuple[bool, str]]
    port: int | None = None
    process: subprocess.Popen[Any] | None = field(default=None, repr=False)
    pgid: int | None = None


def demo_ack() -> str:
    from product.contracts import load_contract

    return str(load_contract("auth_policy")["demo_provider"]["acknowledgement_value"])


# ---- readiness probes (real processes only) ---------------------------------------------------------------
def probe_inference(port: int) -> tuple[bool, str]:
    try:
        title = httpx.get(f"http://{HOST}:{port}/openapi.json", timeout=2.0).json()["info"]["title"]
    except (httpx.HTTPError, ValueError, KeyError):
        return False, "not ready"
    return ("SOFTWARE_SYSTEM_V2 default binding" in title), title


def probe_product(port: int) -> tuple[bool, str]:
    try:
        r = httpx.get(f"http://{HOST}:{port}/product/v1/system", timeout=2.0)
        body = r.json()
    except (httpx.HTTPError, ValueError):
        return False, "not ready"
    want = {"product_api_implementation": "CAPSTONE_PRODUCT_API_V1_3", "product_api_version": "PRODUCT_API_V2", "software_system": "SOFTWARE_SYSTEM_V2",
            "model_id": "MODEL_V2_FINAL", "persistence_mode": "SQLITE", "auth_provider": "DEMO", "demo_mode": True,
            "federation_runtime": "ENABLED_ENGINEERING", "hardware_mode": "SIMULATED_ONLY"}
    bad = {k: body.get(k) for k, v in want.items() if body.get(k) != v}
    return (r.status_code == 200 and not bad), json.dumps(bad) if bad else body["product_api_implementation"]


def probe_frontend(port: int) -> tuple[bool, str]:
    try:
        return httpx.get(f"http://{HOST}:{port}/sign-in", timeout=2.0).status_code == 200, "sign-in"
    except httpx.HTTPError:
        return False, "not ready"


def build_services(ws: Workspace, ports: dict[str, int], python: str = sys.executable) -> list[ServiceSpec]:
    base_env = {**os.environ, "PYTHONPATH": "src:."}
    inference_url = f"http://{HOST}:{ports['inference']}"
    product_env = {**base_env, "NHM_PRODUCT_AUTH_MODE": "DEMO", "NHM_PRODUCT_DEMO_AUTH_ACK": demo_ack(), "NHM_PRODUCT_DEMO_USER_ID": DEMO_USER_ID,
                   "NHM_PRODUCT_DB_PATH": str(ws.db), "NHM_FEDERATION_ARTIFACT_ROOT": str(ws.federation), "NHM_FL_CANDIDATE_ROOT": str(ws.candidates),
                   "NHM_PRODUCT_INFERENCE_URL": inference_url, "NHM_PRODUCT_TIMING_MODE": "ACCELERATED"}
    for secret in ("CLERK_SECRET_KEY", "CLERK_JWT_KEY", "CLERK_PUBLISHABLE_KEY"):
        product_env.pop(secret, None)  # the demo never initialises or contacts Clerk
    return [
        ServiceSpec("inference", [python, "-m", "scripts.run_nhm_default", "--profile", "default", "--host", HOST, "--port", str(ports["inference"])],
                    base_env, ROOT, ws.logs / "inference.log", lambda: probe_inference(ports["inference"]), ports["inference"]),
        ServiceSpec("product", [python, "-m", "scripts.run_capstone_product_v1_3", "--host", HOST, "--port", str(ports["product"])],
                    product_env, ROOT, ws.logs / "product.log", lambda: probe_product(ports["product"]), ports["product"]),
        ServiceSpec("frontend", ["npm", "run", "preview", "--", "--port", str(ports["frontend"]), "--strictPort", "--host", HOST],
                    {**base_env, "NHM_PRODUCT_API_PORT": str(ports["product"])}, FRONTEND, ws.logs / "frontend.log", lambda: probe_frontend(ports["frontend"]), ports["frontend"]),
    ]


class DemoOrchestrator:
    def __init__(self, services: list[ServiceSpec], *, say: Callable[[str], None] = print, ready_timeout: float = READY_TIMEOUT_S, poll_s: float = 0.5) -> None:
        self.services, self.say, self.ready_timeout, self.poll_s = services, say, ready_timeout, poll_s
        self.failed: str | None = None
        self.stop_requested = False
        self.launched_pids: dict[str, int] = {}

    # ---- launch ------------------------------------------------------------------------------------------
    def launch(self, spec: ServiceSpec) -> None:
        log = spec.log.open("ab")
        spec.process = subprocess.Popen(spec.argv, cwd=spec.cwd, env=spec.env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        spec.pgid = spec.process.pid  # own process group: only OUR child tree is ever signalled
        self.launched_pids[spec.name] = spec.process.pid
        self.say(f"started {spec.name} pid={spec.process.pid}")

    def start_and_wait_ready(self) -> bool:
        """Start in dependency order, probing each. False (stack already stopped) on any failure or timeout."""
        for spec in self.services:
            self.launch(spec)
        deadline = time.monotonic() + self.ready_timeout
        pending = {s.name for s in self.services}
        while pending:
            for spec in self.services:
                if spec.name not in pending:
                    continue
                if spec.process is not None and spec.process.poll() is not None:
                    self.failed = spec.name
                    self.say(f"SERVICE_FAILURE:{spec.name}")
                    self.shutdown()
                    return False
                ok, _detail = spec.ready()
                if ok:
                    pending.discard(spec.name)
                    self.say(f"{spec.name} ready")
            if pending and time.monotonic() > deadline:
                self.failed = "READY_TIMEOUT:" + ",".join(sorted(pending))
                self.say(f"READY_TIMEOUT:{sorted(pending)}")
                self.shutdown()
                return False
            if pending:
                time.sleep(self.poll_s)
        return True  # all probes passed: only now may READY be printed

    # ---- supervision / shutdown ----------------------------------------------------------------------------
    def supervise(self, stop: Callable[[], bool] = lambda: False) -> int:
        while not (self.stop_requested or stop()):
            for spec in self.services:
                if spec.process is not None and spec.process.poll() is not None:
                    self.failed = spec.name
                    self.say(f"SERVICE_FAILURE:{spec.name}")
                    self.shutdown()
                    return EXIT["SERVICE_FAILURE"]
            time.sleep(self.poll_s)
        self.shutdown()
        return EXIT["OK"]

    def _signal_group(self, spec: ServiceSpec, sig: int) -> None:
        if spec.pgid is None:
            return
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(spec.pgid, sig)  # the group we created; never an unrelated pid

    def shutdown(self, grace_s: float = 20.0) -> dict[str, Any]:
        """Reverse dependency order: frontend, product, inference. Escalate only our own children."""
        report: dict[str, Any] = {}
        for spec in reversed(self.services):
            if spec.process is None:
                continue
            self._signal_group(spec, signal.SIGTERM)
            try:
                spec.process.wait(timeout=grace_s)
                report[spec.name] = "terminated"
            except subprocess.TimeoutExpired:
                self._signal_group(spec, signal.SIGKILL)
                spec.process.wait(timeout=5)
                report[spec.name] = "killed_after_grace"
            self._signal_group(spec, signal.SIGKILL)  # reap stragglers of OUR group (e.g. npm's node child)
        self.say("stack stopped")
        return report

    def orphans(self) -> list[str]:
        """Launched process groups still alive (checks only what this launcher started)."""
        alive = []
        for spec in self.services:
            if spec.pgid is None:
                continue
            try:
                os.killpg(spec.pgid, 0)
                alive.append(spec.name)
            except ProcessLookupError:
                pass
        return alive


def ready_block(ports: dict[str, int], ws: Workspace) -> str:
    return "\n".join([
        "NHM FACULTY DEMO READY", "",
        f"Frontend:   http://{HOST}:{ports['frontend']}/sign-in", "Inference:  SOFTWARE_SYSTEM_V2 / MODEL_V2_FINAL",
        "Product:    CAPSTONE_PRODUCT_API_V1_3", "Auth:       OFFLINE DEMO (not Clerk)", "Hardware:   SIMULATED ONLY", "FL:         ENGINEERING FEDERATION (8 logical synthetic clients, one laptop)",
        "Timing:     SIMULATION TIMING: ACCELERATED FOR PRESENTATION (pacing only; not real-time)", f"Workspace:  {ws.path}", "Stop:       Ctrl+C"])


def prewarm_federation(product_port: int, say: Callable[[str], None] = print) -> dict[str, Any]:
    """Truthful optional prewarm: one safe existing READ builds the eight deterministic logical client datasets.
    0 training, 0 submit, 0 aggregation, 0 SecAgg, 0 candidates, 0 runs; side effects are audited before/after."""
    base = f"http://{HOST}:{product_port}/product/v1"

    def counts() -> dict[str, Any]:
        overview = httpx.get(f"{base}/federation", timeout=30).json()
        runs = httpx.get(f"{base}/federation/runs", timeout=30).json()
        models = httpx.get(f"{base}/models", timeout=30).json()
        return {"federation_runs": len(runs), "candidates": len(models["capstone_fl_candidates"]), "candidate_count_overview": overview["candidate_count"],
                "released_default": models["released_default_model_id"], "active_live_run": overview["active_live_run"]}

    before = counts()
    say("PREPARING 8 SYNTHETIC FEDERATED CLIENT DATASETS (read-only preparation; this may take several seconds)")
    started = time.monotonic()
    clients = httpx.get(f"{base}/federation/clients", timeout=300).json()
    elapsed = round(time.monotonic() - started, 3)
    after = counts()
    return {"enabled": True, "clients": len(clients), "elapsed_s_engineering_telemetry_only": elapsed, "before": before, "after": after,
            "training_calls": 0, "federation_runs_created": after["federation_runs"] - before["federation_runs"],
            "candidates_created": after["candidates"] - before["candidates"], "released_binding_changed": after["released_default"] != before["released_default"],
            "side_effect_free": before == after}


def build_frontend(say: Callable[[str], None] = print) -> float:
    started = time.monotonic()
    say("building the existing frontend (npm run build)")
    result = subprocess.run(["npm", "run", "build"], cwd=FRONTEND, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError("FRONTEND_BUILD_FAILED:" + (result.stdout + result.stderr)[-300:])
    (ROOT / BUILD_STAMP).write_text(json.dumps({"frontend_source_sha256": frontend_source_digest()}) + "\n")
    return round(time.monotonic() - started, 3)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="NHM faculty demo launcher (offline, one laptop)")
    p.add_argument("--acknowledge-demo-auth", action="store_true", help="explicitly accept OFFLINE DEMO identity (NOT Clerk)")
    p.add_argument("--workspace", help="demo workspace directory OUTSIDE the repository (default: a fresh temporary directory)")
    p.add_argument("--mode", choices=("fresh", "resume"), default="fresh")
    p.add_argument("--reset", action="store_true", help="safely delete the validated demo workspace, then start fresh")
    p.add_argument("--reset-only", action="store_true", help="safely delete the validated demo workspace and exit")
    p.add_argument("--inference-port", type=int, default=DEFAULT_PORTS["inference"])
    p.add_argument("--product-port", type=int, default=DEFAULT_PORTS["product"])
    p.add_argument("--frontend-port", type=int, default=DEFAULT_PORTS["frontend"])
    p.add_argument("--build", action="store_true", help="run `npm run build` before serving")
    p.add_argument("--prewarm-federation", action="store_true")
    p.add_argument("--open-browser", action="store_true")
    p.add_argument("--preflight-only", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    ports = {"inference": args.inference_port, "product": args.product_port, "frontend": args.frontend_port}
    if args.reset_only:
        if not args.workspace:
            print("REFUSING: --reset-only needs --workspace", file=sys.stderr)
            return EXIT["REFUSED"]
        try:
            Workspace.reset(args.workspace)
        except WorkspaceError as error:
            print(f"REFUSING TO RESET: {error}", file=sys.stderr)
            return EXIT["WORKSPACE"]
        print("workspace reset")
        return EXIT["OK"]
    if not args.acknowledge_demo_auth:
        print("REFUSING TO START: DEMO_AUTH_ACKNOWLEDGEMENT_REQUIRED (pass --acknowledge-demo-auth; the demo uses an OFFLINE DEMO identity, not Clerk)", file=sys.stderr)
        return EXIT["REFUSED"]
    busy = [f"PORT_IN_USE:{name}:{port}" for name, port in ports.items() if not port_free(port)]
    if busy:  # fail BEFORE touching anything; never kill the occupant
        print("REFUSING TO START: " + " ".join(busy), file=sys.stderr)
        return EXIT["PORT_IN_USE"]
    try:
        if args.reset and args.workspace:
            Workspace.reset(args.workspace)
        if args.preflight_only:  # validate only; never leave a workspace behind
            ws = None
            if args.mode == "resume":
                Workspace.open_resume(args.workspace or "")
        else:
            ws = Workspace.open_resume(args.workspace) if args.mode == "resume" else Workspace.create_fresh(args.workspace)
    except WorkspaceError as error:
        print(f"REFUSING TO START: {error}", file=sys.stderr)
        return EXIT["WORKSPACE"]
    pre = run_preflight(ports=ports, acknowledged=True, workspace_ok=True, workspace_detail=str(ws.path) if ws else "preflight-only: no workspace created", skip_build_check=args.build)
    print(json.dumps({"preflight": {k: v["ok"] for k, v in pre["checks"].items()}}))
    if not pre["passed"]:
        for name, c in pre["checks"].items():
            if not c["ok"]:
                print(f"PREFLIGHT_FAILED:{name}:{c['detail']}", file=sys.stderr)
        return EXIT["PREFLIGHT_FAILED"]
    if args.preflight_only:
        return EXIT["OK"]
    assert ws is not None
    if args.build:
        build_frontend()
    orch = DemoOrchestrator(build_services(ws, ports), say=lambda m: print(m, flush=True))

    def on_signal(signum: int, _frame: Any) -> None:
        orch.stop_requested = True

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)
    if not orch.start_and_wait_ready():
        return EXIT["READY_TIMEOUT"] if (orch.failed or "").startswith("READY_TIMEOUT") else EXIT["SERVICE_FAILURE"]
    status: dict[str, Any] = {"ports": ports, "workspace": str(ws.path), "pids": orch.launched_pids, "auth": "DEMO", "timing": "ACCELERATED"}
    if args.prewarm_federation:
        status["prewarm"] = prewarm_federation(ports["product"])
    (ws.path / "status.json").write_text(json.dumps(status, indent=1, sort_keys=True) + "\n")
    print(ready_block(ports, ws), flush=True)
    if args.open_browser:
        webbrowser.open(f"http://{HOST}:{ports['frontend']}/sign-in")
    code = orch.supervise()
    secrets = scan_logs_for_secrets(ws.logs)
    (ws.path / "shutdown.json").write_text(json.dumps({"exit_code": code, "orphans": orch.orphans(), "secret_scan": secrets}, indent=1) + "\n")
    return code


if __name__ == "__main__":
    sys.exit(main())
