"""Run both hardware scenarios through real Chrome and a real Clerk test instance."""

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

from pymongo import MongoClient

from scripts.run_capstone_clerk_connected import build_frontend, build_services, parse_env_file, resolve_config
from scripts.run_capstone_clerk_connected_e2e import Browser, free_port
from scripts.run_capstone_faculty_demo import DemoOrchestrator
from scripts.capstone_demo_workspace import SENTINEL, Workspace

DRIVER = ROOT / "scripts/hardware_final_cdp_driver.mjs"


def stack(env: dict[str, str], workspace: Path, python: str) -> tuple[DemoOrchestrator, str]:
    ports = {"inference": 8001, "product": 8002, "frontend": 4173}
    cfg = resolve_config(env, ports["frontend"])
    ws = Workspace.create_fresh(workspace) if not (workspace / SENTINEL).exists() else Workspace.open_resume(workspace)
    services = build_services(ws, ports, cfg, env, python=python)
    services[1].argv = [python, "-m", "scripts.run_observatory_product", "--host", "127.0.0.1", "--port", str(ports["product"])]
    orchestrator = DemoOrchestrator(services, ready_timeout=240, say=lambda message: print(message, flush=True))
    if not orchestrator.start_and_wait_ready():
        raise RuntimeError(orchestrator.failed or "stack failed")
    return orchestrator, f"http://127.0.0.1:{ports['frontend']}"


def drive(mode: str, origin: str, users: Path, out: Path, shots: Path, logs: Path, env: dict[str, str], *, who: str = "A", expected: str | None = None) -> dict:
    profile = Path(tempfile.mkdtemp(prefix=f"nhm-hardware-{mode}-"))
    browser = Browser(profile, free_port())
    command = ["node", str(DRIVER), mode, str(browser.port), origin, str(users), str(out), str(shots), str(logs)]
    run_env = {**os.environ, **env, "NHM_TEST_PYTHON": str(ROOT / ".venv-studio311/bin/python"), "NHM_BROWSER_USER": who}
    if expected:
        run_env["NHM_EXPECT_SESSION"] = expected
    try:
        result = subprocess.run(command, cwd=ROOT, env=run_env, capture_output=True, text=True, timeout=1800)
    finally:
        browser.close(); shutil.rmtree(profile, ignore_errors=True)
    if result.returncode or not out.exists():
        raise RuntimeError(f"browser {mode} failed: {(result.stdout + result.stderr)[-1200:]}")
    return json.loads(out.read_text())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default=str(ROOT / ".env"))
    parser.add_argument("--users-file", required=True)
    parser.add_argument("--out", default=str(ROOT / "reports/hardware/final_demo/browser"))
    args = parser.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    env = {**parse_env_file(Path(args.env_file)), **os.environ}
    env["NHM_HARDWARE_MONGO_ENABLED"] = "true"
    env["NHM_HARDWARE_MONGO_DATABASE"] = "health_db"
    env["NHM_HARDWARE_MONGO_COLLECTION"] = "nhm_integration_test"
    cfg = resolve_config(env, 4173)
    python = str(ROOT / ".venv-studio311/bin/python")
    build_frontend(cfg, env)
    workspace = Path(tempfile.mkdtemp(prefix="nhm-hardware-browser-workspace-")) / "workspace"
    tags: list[str] = []
    first = second = owner = None
    try:
        running, origin = stack(env, workspace, python)
        try:
            first = drive("scenario-a", origin, Path(args.users_file), out / "scenario_a.json", out / "scenario_a_shots", out / "publisher_logs", env)
            tags.append(first["tag"])
        finally:
            running.shutdown()
        # A real backend restart against the same SQLite and artifact workspace.
        running, origin = stack(env, workspace, python)
        try:
            second = drive("scenario-b", origin, Path(args.users_file), out / "scenario_b.json", out / "scenario_b_shots", out / "publisher_logs", env, expected=first["session_id"])
            tags.append(second["tag"])
            owner = drive("owner-probe", origin, Path(args.users_file), out / "owner_probe.json", out / "owner_probe_shots", out / "publisher_logs", env, who="B", expected=first["session_id"])
        finally:
            running.shutdown()
        verdict = {
            "status": "PASS" if (
                first["waiting"]["state"] == "WAITING FOR DATA" and first["live"]["points"] > 0 and
                abs(first["live"]["latest_y"] - first["live"]["expected_y"]) < 1e-9 and first["live"]["latest_x"] == 1000 and
                first["stale"]["state"] == "STALE DATA" and first["recovered"]["state"] == "LIVE DATA RECEIVED" and
                first["stopped"]["state"] == "SESSION STOPPED" and second["prior_history_after_restart"] and
                second["first_stop"]["count"] == second["first_after_stop"]["count"] and second["separate_sessions"] and
                owner["detail_refused"] and owner["target_absent_from_demo_sources"]
            ) else "FAIL",
            "real_chrome": True, "real_clerk_test_users": 2, "actual_atlas_collection": "health_db.nhm_integration_test",
            "scenario_a_session": first["session_id"], "scenario_b_sessions": [second["first_session_id"], second["second_session_id"]],
            "backend_restart_between_scenarios": True, "owner_probe": owner,
            "screenshots": sorted(str(p.relative_to(out)) for p in out.rglob("*.png")),
        }
        (out / "browser_verdict.json").write_text(json.dumps(verdict, indent=2, sort_keys=True) + "\n")
        print(json.dumps({"status": verdict["status"], "evidence": str(out / "browser_verdict.json")}))
        return 0 if verdict["status"] == "PASS" else 1
    finally:
        uri = env.get("NHM_HARDWARE_MONGO_URI")
        if uri and tags:
            client = MongoClient(uri, serverSelectionTimeoutMS=5000)
            collection = client[env.get("NHM_HARDWARE_MONGO_DATABASE", "health_db")]["nhm_integration_test"]
            cleanup = {tag: collection.delete_many({"nhmTestRun": tag}).deleted_count for tag in tags}
            (out / "browser_atlas_cleanup.json").write_text(json.dumps({"deleted_by_tag": cleanup, "production_data_deleted": False}, indent=2, sort_keys=True) + "\n")
            client.close()


if __name__ == "__main__":
    raise SystemExit(main())
