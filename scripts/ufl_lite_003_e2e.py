# ruff: noqa: E501
"""UFL-LITE-003 canonical REAL-Clerk end-to-end orchestrator (records observations; defines no pass criteria -- the frozen UFLG2 evaluator does).
  python -m scripts.ufl_lite_003_e2e --env-file <env outside Git> --users-file <json outside Git> --out <evidence dir> --raw <scratch dir> [--label NAME]
Flow: Clerk-connected launcher (build) -> TEST_USER_A owner journey (LIVE_RUN, refresh, REPLAY, models, global view) -> TEST_USER_B isolation -> backend restart (same SQLite)
-> TEST_USER_A return (fresh Chrome profile). Evidence: sanitized observations + analyzer verdicts + secret audits. No token/cookie/secret/password is recorded."""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from scripts import ufl_lite_003_lib as an
from scripts import ufl_lite_lib as lib
from scripts.run_capstone_clerk_connected import parse_env_file
from scripts.run_capstone_clerk_connected_e2e import (
    JWT,
    ORIGIN,
    Browser,
    Stack,
    free_port,
    scan_tree,
)

ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "scripts/ufl_lite_003_cdp_driver.mjs"


def run_driver(mode: str, who: str, users: Path, raw: Path, name: str, *extra: str) -> dict[str, Any]:
    profile = Path(tempfile.mkdtemp(prefix=f"ufl3-profile-{name}-"))     # FRESH browser profile per run: no copied cookies/session
    port = free_port()
    browser = Browser(profile, port)
    out = raw / f"{name}.json"
    try:
        r = subprocess.run(["node", str(DRIVER), mode, str(port), ORIGIN, str(users), who, str(out), str(raw / f"shots_{name}"), *extra], cwd=ROOT, capture_output=True, text=True, timeout=3000)
    finally:
        browser.close()
        shutil.rmtree(profile, ignore_errors=True)
    if r.returncode != 0 or not out.exists():
        raise RuntimeError(f"DRIVER_FAILED:{name}:{(r.stdout + r.stderr)[-600:]}")
    return json.loads(out.read_text())


def main() -> int:
    ap = argparse.ArgumentParser()
    for n in ("--env-file", "--users-file", "--out", "--raw"):
        ap.add_argument(n, required=True)
    ap.add_argument("--label", default="CANONICAL")
    args = ap.parse_args()
    out_dir, raw, users = Path(args.out), Path(args.raw), Path(args.users_file)
    out_dir.mkdir(parents=True, exist_ok=True)
    raw.mkdir(parents=True, exist_ok=True)
    env = parse_env_file(Path(args.env_file))
    secret = env["CLERK_SECRET_KEY"]
    work = Path(tempfile.mkdtemp(prefix="ufl3-e2e-"))
    ws_path = work / "workspace"
    t0 = time.monotonic()

    def write(name: str, payload: dict[str, Any]) -> None:
        text = json.dumps(payload, indent=1, sort_keys=True, default=str) + "\n"
        assert secret not in text and "sk_test_" not in text and not JWT.search(text), f"SECRET_IN_EVIDENCE:{name}"
        (out_dir / name).write_text(text)

    stack = Stack(env, ws_path, work / "launcher1.out", build=True)
    startup = stack.start()
    stack2 = None
    try:
        a = run_driver("owner-live", "A", users, raw, "a_owner")
        b = run_driver("b-isolation", "B", users, raw, "b_isolation", a["liveRunId"])
        stopped1 = stack.stop()
        stack2 = Stack(env, ws_path, work / "launcher2.out", mode="resume")
        restart_startup = stack2.start()
        a2 = run_driver("a-return", "A", users, raw, "a_return", a["liveRunId"])
        stopped2 = stack2.stop()
    finally:
        for st in (stack, stack2):
            if st is not None and st.process is not None and st.process.poll() is None:
                st.stop()
    baseline = lib.load_baseline(ROOT)
    groups = an.analyze_all(a, b, a2, baseline)
    # ---- secret / persistence audits -----------------------------------------------------------------------------------
    sqlite_hits, tables, owner_persisted = [], {}, []
    dbp = ws_path / "product.sqlite3"
    if dbp.exists():
        conn = sqlite3.connect(dbp)
        for (name,) in conn.execute("select name from sqlite_master where type='table'"):
            rows = conn.execute(f'select * from "{name}"').fetchall()
            tables[name] = len(rows)
            blob = json.dumps(rows, default=str)
            if secret in blob or "sk_test_" in blob or JWT.search(blob):
                sqlite_hits.append(name)
            if "MY EDGE CLIENT" in blob or "AUTHENTICATED_OWNER" in blob or "owner_bound" in blob.lower():
                owner_persisted.append(name)
        conn.close()
    build_dir, ws_logs = ROOT / "frontend/build", ws_path / "logs"
    scans = {"workspace": scan_tree(work, secret), "workspace_logs": scan_tree(ws_logs, secret) if ws_logs.exists() else [], "frontend_build": scan_tree(build_dir, secret), "frontend_build_secret_prefix": scan_tree(build_dir, "sk" + "_test_"), "frontend_src": scan_tree(ROOT / "frontend/src", secret),
             "raw_driver_output": scan_tree(raw, secret), "repo_unignored": subprocess.run(["git", "grep", "-lF", "--untracked", "-e", secret], cwd=ROOT, capture_output=True, text=True).stdout.split(), "raw_jwt_shaped": [p.name for p in raw.glob("*.json") if JWT.search(p.read_text())]}
    clean_secrets = all(not v for v in scans.values()) and not sqlite_hits
    verdict = {g: {"checks": c, "all_pass": all(c.values())} for g, c in groups.items() if g != "clerk_network"}
    net = groups["clerk_network"]
    write("owner_e2e_observations.json", {"label": args.label, "A": a, "B": b, "A_return": a2})
    write("owner_e2e_analysis.json", {"label": args.label, "real_clerk_test_instance": True, "real_browser": "headless Google Chrome via CDP, fresh profile per run", "mocked_clerk": False, "demo_fallback": False, "manual_steps": "none (fully automated)", "groups": verdict,
                                      "all_pass": all(v["all_pass"] for v in verdict.values()) and net["clerk_hosts_contacted"] and net["no_console_errors"], "clerk_hosts_contacted": net["clerk_hosts_contacted"], "no_console_errors": net["no_console_errors"], "live_run_id": a["liveRunId"], "replay_run_id": a["replayRunId"],
                                      "startup_s_machine_specific": startup, "restart_startup_s_machine_specific": restart_startup, "stop_1": stopped1, "stop_2": stopped2, "elapsed_s_machine_specific": round(time.monotonic() - t0, 1)})
    write("secret_and_persistence_audit.json", {"label": args.label, "clean": clean_secrets, "scopes": {k: len(v) for k, v in scans.items()}, "sqlite_tables": tables, "sqlite_tables_with_secret_or_token": sqlite_hits, "owner_binding_persisted_in_sqlite": owner_persisted, "secret_value_recorded": False, "key_rotation_performed": False,
                                                "ws_url_token": any(s["urlHasToken"] for s in a["websockets"] + a.get("websockets", []))})
    shutil.rmtree(work, ignore_errors=True)
    print(json.dumps({"e2e": "DONE", "label": args.label, "all_pass": json.loads((out_dir / "owner_e2e_analysis.json").read_text())["all_pass"], "secrets_clean": clean_secrets, "failed": {g: [k for k, v in c["checks"].items() if not v] for g, c in verdict.items() if not c["all_pass"]}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
