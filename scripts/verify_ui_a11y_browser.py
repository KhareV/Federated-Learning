"""Non-hardware accessibility / semantics / console / network audit in real Chrome with a real Clerk test user.

No hardware source is enabled, no telemetry is written and nothing is seeded: the stack runs with the MongoDB hardware source switched off.
  python -m scripts.verify_ui_a11y_browser --users-file <users.json> --out <dir> [--viewports desktop,phone] [--routes '["/app"]']
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from scripts.capstone_demo_workspace import SENTINEL, Workspace  # noqa: E402
from scripts.run_capstone_clerk_connected import build_frontend, build_services, parse_env_file, resolve_config  # noqa: E402
from scripts.run_capstone_clerk_connected_e2e import Browser, free_port  # noqa: E402
from scripts.run_capstone_faculty_demo import DemoOrchestrator  # noqa: E402

DRIVER = ROOT / "scripts/ui_a11y_driver.mjs"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default=str(ROOT / ".env"))
    parser.add_argument("--users-file", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--viewports", default="desktop,phone")
    parser.add_argument("--routes", default=None, help="JSON list overriding the route set")
    parser.add_argument("--tab-max", type=int, default=90)
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    env = {**parse_env_file(Path(args.env_file)), **os.environ}
    env["NHM_HARDWARE_MONGO_ENABLED"] = "false"          # hardware is out of scope for this audit: no source, no polling, no writes
    cfg = resolve_config(env, 4173)
    python = str(ROOT / ".venv-studio311/bin/python")
    build_frontend(cfg, env)
    workspace = Path(tempfile.mkdtemp(prefix="nhm-a11y-workspace-")) / "workspace"
    ports = {"inference": 8001, "product": 8002, "frontend": 4173}
    ws = Workspace.create_fresh(workspace) if not (workspace / SENTINEL).exists() else Workspace.open_resume(workspace)
    services = build_services(ws, ports, cfg, env, python=python)
    services[1].argv = [python, "-m", "scripts.run_observatory_product", "--host", "127.0.0.1", "--port", str(ports["product"])]
    orchestrator = DemoOrchestrator(services, ready_timeout=240, say=lambda message: print(message, flush=True))
    if not orchestrator.start_and_wait_ready():
        raise RuntimeError(orchestrator.failed or "stack failed")
    profile = Path(tempfile.mkdtemp(prefix="nhm-a11y-profile-"))
    browser = Browser(profile, free_port())
    raw = out / "a11y.json"
    run_env = {**os.environ, "NHM_A11Y_VIEWPORTS": args.viewports, "NHM_A11Y_TABMAX": str(args.tab_max)}
    if args.routes:
        run_env["NHM_A11Y_ROUTES"] = args.routes
    try:
        result = subprocess.run(["node", str(DRIVER), str(browser.port), "http://127.0.0.1:4173", args.users_file, str(raw)], cwd=ROOT, env=run_env, capture_output=True, text=True, timeout=3000)
    finally:
        browser.close()
        shutil.rmtree(profile, ignore_errors=True)
        orchestrator.shutdown()
    if result.returncode or not raw.exists():
        print((result.stdout + result.stderr)[-1500:])
        return 1
    report = json.loads(raw.read_text())["report"]
    print(json.dumps({"status": "A11Y_AUDIT_DONE", "entries": len(report), "tool_errors": sum(1 for e in report if "error" in e)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
