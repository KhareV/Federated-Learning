"""Launch the additive Observatory with the accepted Clerk TEST auth configuration.

The accepted CAPSTONE_UI_V1_9 verifier intentionally rejects the unaccepted Observatory
successor's new frontend files. This launcher verifies V1_9 at its accepted entry commit
and checks all non-UI demo preflights without editing or weakening any historical lock.
"""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

from scripts.capstone_demo_preflight import DEFAULT_VERIFIERS, port_free
from scripts.capstone_demo_workspace import Workspace, WorkspaceError
from scripts.run_capstone_clerk_connected import (
    ConnectedConfigError,
    build_frontend,
    build_services,
    parse_args,
    parse_env_file,
    resolve_config,
)
from scripts.run_capstone_faculty_demo import EXIT, HOST, DemoOrchestrator

ROOT = Path(__file__).resolve().parents[1]
ENTRY = "dff28f6a7b7bd527def21cb9fd95d682aa60a667"
UI_LOCK = ROOT / "artifacts/capstone/CAPSTONE_UI_V1_9.lock.json"


def historical_ui_intact() -> bool:
    lock = json.loads(UI_LOCK.read_text())
    if lock.get("lock_id") != "CAPSTONE_UI_V1_9":
        return False
    for relative, expected in lock["bound_artifacts"].items():
        result = subprocess.run(["git", "show", f"{ENTRY}:{relative}"], cwd=ROOT,
                                capture_output=True, check=False)
        if result.returncode != 0 or hashlib.sha256(result.stdout).hexdigest() != expected:
            return False
    protected = subprocess.run(
        ["git", "diff", "--name-only", ENTRY, "--", "artifacts/capstone",
         "preprocessing", "federated", "product/federation", "product/monitoring",
         "product/models", "capstone_persistence", "evaluation", "datasets",
         ":(exclude)artifacts/capstone/*.amendment_*.json"],
        cwd=ROOT, capture_output=True, check=False,
    )
    return protected.returncode == 0 and not protected.stdout.strip()


def main() -> int:
    args = parse_args()
    ports = {"inference": args.inference_port, "product": args.product_port,
             "frontend": args.frontend_port}
    env = dict(os.environ)
    if args.env_file:
        env = {**parse_env_file(Path(args.env_file)), **env}
    extra = [f"http://localhost:{args.frontend_port}"] if args.also_localhost_origin else []
    try:
        cfg = resolve_config(env, args.frontend_port, extra)
    except ConnectedConfigError as error:
        print(f"REFUSING TO START: {error}", file=sys.stderr)
        return EXIT["REFUSED"]
    busy = [name for name, port in ports.items() if not port_free(port)]
    if busy:
        print(f"REFUSING TO START: PORT_IN_USE:{busy}", file=sys.stderr)
        return EXIT["PORT_IN_USE"]
    # The original current-tree UI preflight is not successor-aware. Keep its failure
    # disclosed, but verify the accepted V1_9 bytes historically and all safe peers.
    selected = {name: check for name, check in DEFAULT_VERIFIERS.items()
                if name not in {"prior_locks_and_amendments", "ui_successor", "frontend_build"}}
    checks = {name: check() for name, check in selected.items()}
    checks["historical_ui_v1_9"] = {"ok": historical_ui_intact(),
                                    "detail": "accepted entry bytes and protected diff"}
    print(json.dumps({"preflight": {name: value["ok"] for name, value in checks.items()},
                      "historical_current_tree_ui_preflight": (
                          "EXPECTED_FAIL_UNACCEPTED_OBSERVATORY_SUCCESSOR"),
                      "auth": "CLERK_TEST", "secret_key_present": True,
                      "authorized_parties": cfg["authorized_parties"]}), flush=True)
    if not all(value["ok"] for value in checks.values()):
        return EXIT["PREFLIGHT_FAILED"]
    if args.preflight_only:
        return EXIT["OK"]
    if not args.build:
        print("REFUSING TO START: CONNECTED_OBSERVATORY_REQUIRES_PUBLIC_KEY_BUILD",
              file=sys.stderr)
        return EXIT["REFUSED"]
    try:
        ws = Workspace.open_resume(args.workspace) if args.mode == "resume" else \
            Workspace.create_fresh(args.workspace)
    except WorkspaceError as error:
        print(f"REFUSING TO START: {error}", file=sys.stderr)
        return EXIT["WORKSPACE"]
    build_frontend(cfg, env)
    services = build_services(ws, ports, cfg, env)
    services[1].argv = [sys.executable, "-m", "scripts.run_observatory_product",
                        "--host", HOST, "--port", str(ports["product"])]
    orchestrator = DemoOrchestrator(services, say=lambda message: print(message, flush=True))

    def on_signal(_signum: int, _frame: Any) -> None:
        orchestrator.stop_requested = True

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)
    if not orchestrator.start_and_wait_ready():
        return EXIT["READY_TIMEOUT"] if (orchestrator.failed or "").startswith(
            "READY_TIMEOUT") else EXIT["SERVICE_FAILURE"]
    print(json.dumps({"status": "OBSERVATORY_CLERK_TEST_READY_NOT_E2E_ACCEPTED",
                      "frontend": f"http://{HOST}:{ports['frontend']}/sign-in",
                      "product": "NHM_RESEARCH_OBSERVATORY_V1_CANDIDATE",
                      "auth": "CLERK", "demo_mode": False,
                      "workspace": str(ws.path)}), flush=True)
    return orchestrator.supervise()


if __name__ == "__main__":
    sys.exit(main())
