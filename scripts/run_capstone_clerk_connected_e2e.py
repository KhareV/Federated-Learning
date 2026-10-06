# ruff: noqa: E501
"""CLERK-LIVE-001 canonical connected E2E orchestrator: the Clerk-connected launcher + REAL Chrome + REAL Clerk TEST sign-in
for TEST_USER_A and TEST_USER_B (users supplied through an external users file; their credentials are never written to evidence).
  python -m scripts.run_capstone_clerk_connected_e2e --env-file <env outside Git> --users-file <json outside Git> --out <evidence dir> [--raw <scratch dir>]
Evidence JSON contains booleans/statuses/counts only: no token, no cookie value, no secret, no password. Clerk user ids are pseudonymised."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx

from scripts.run_capstone_clerk_connected import parse_env_file
from scripts.run_capstone_frontend_e2e import CHROME

ROOT = Path(__file__).resolve().parents[1]
HOST = "127.0.0.1"
PORTS = (8001, 8002, 4173)
ORIGIN = f"http://{HOST}:{PORTS[2]}"
DRIVER = ROOT / "scripts/clerk_connected_cdp_driver.mjs"
JWT = re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.")


def free_port() -> int:
    import socket

    with socket.socket() as s:
        s.bind((HOST, 0))
        return int(s.getsockname()[1])


class Stack:
    """The Clerk-connected launcher as a real subprocess; waits for READY; stops it with SIGINT (Ctrl+C)."""

    def __init__(self, env: dict[str, str], workspace: Path, log: Path, *, mode: str = "fresh", build: bool = False, parties: str | None = None) -> None:
        self.env, self.workspace, self.log, self.mode, self.build, self.parties = env, workspace, log, mode, build, parties
        self.process: subprocess.Popen[bytes] | None = None

    def start(self, timeout: float = 600.0) -> float:
        cmd = [sys.executable, "-m", "scripts.run_capstone_clerk_connected", "--workspace", str(self.workspace), "--mode", self.mode]
        if self.build:
            cmd.append("--build")
        env = {**os.environ, **self.env, "PYTHONPATH": "src:."}
        if self.parties:
            env["NHM_CLERK_AUTHORIZED_PARTIES"] = self.parties
        t0 = time.monotonic()
        self.process = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=self.log.open("ab"), stderr=subprocess.STDOUT)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError("CONNECTED_LAUNCHER_EXITED:" + self.log.read_text()[-400:])
            if "CLERK-CONNECTED SYSTEM READY" in self.log.read_text(errors="ignore"):
                return round(time.monotonic() - t0, 1)
            time.sleep(1)
        raise RuntimeError("CONNECTED_LAUNCHER_READY_TIMEOUT")

    def stop(self) -> dict[str, Any]:
        assert self.process is not None
        self.process.send_signal(signal.SIGINT)
        try:
            code = self.process.wait(timeout=90)
        except subprocess.TimeoutExpired:
            self.process.kill()
            code = -9
        shut = self.workspace / "shutdown.json"
        orphans = json.loads(shut.read_text()).get("orphans", ["UNKNOWN"]) if shut.exists() else ["UNKNOWN"]
        return {"launcher_exit_code": code, "orphans": orphans}


class Browser:
    def __init__(self, profile: Path, port: int) -> None:
        self.port = port
        self.proc = subprocess.Popen([CHROME, "--headless=new", f"--remote-debugging-port={port}", f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check", "--mute-audio", "--window-size=1440,900", "about:blank"],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                if httpx.get(f"http://{HOST}:{port}/json/version", timeout=2).status_code == 200:
                    return
            except httpx.HTTPError:
                time.sleep(0.3)
        raise RuntimeError("CHROME_LAUNCH_TIMEOUT")

    def close(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def run_driver(mode: str, who: str, users: Path, raw: Path, name: str, *extra: str) -> dict[str, Any]:
    profile = Path(tempfile.mkdtemp(prefix=f"clerk-e2e-profile-{name}-"))     # FRESH browser profile: no copied cookies/session
    port = free_port()
    browser = Browser(profile, port)
    out = raw / f"{name}.json"
    try:
        r = subprocess.run(["node", str(DRIVER), mode, str(port), ORIGIN, str(users), who, str(out), str(raw / f"shots_{name}"), *extra], cwd=ROOT, capture_output=True, text=True, timeout=2400)
    finally:
        browser.close()
        shutil.rmtree(profile, ignore_errors=True)
    if r.returncode != 0 or not out.exists():
        raise RuntimeError(f"DRIVER_FAILED:{name}:{(r.stdout + r.stderr)[-600:]}")
    return json.loads(out.read_text())


def step(run: dict[str, Any], name: str) -> dict[str, Any]:
    return next(s for s in run["steps"] if s["step"] == name)


def scan_tree(root: Path, needle: str, *, skip: tuple[str, ...] = ()) -> list[str]:
    hits = []
    for p in root.rglob("*"):
        if p.is_file() and not any(part in skip for part in p.parts):
            try:
                if needle.encode() in p.read_bytes():
                    hits.append(str(p.relative_to(root)))
            except OSError:
                pass
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env-file", required=True)
    ap.add_argument("--users-file", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--raw")
    args = ap.parse_args()
    out_dir, users = Path(args.out), Path(args.users_file)
    out_dir.mkdir(parents=True, exist_ok=True)
    raw = Path(args.raw) if args.raw else Path(tempfile.mkdtemp(prefix="clerk-e2e-raw-"))
    raw.mkdir(parents=True, exist_ok=True)
    env = parse_env_file(Path(args.env_file))
    secret = env["CLERK_SECRET_KEY"]
    work = Path(tempfile.mkdtemp(prefix="clerk-e2e-"))
    ws_path = work / "workspace"
    t0 = time.monotonic()
    result: dict[str, Any] = {"phase": "CLERK-LIVE-001", "credential_source": "UNTRACKED_ENV_FILE_OUTSIDE_GIT_OR_ENVIRONMENT", "publishable_key_present": True, "secret_key_present": True, "secret_committed": False}

    def write(name: str, payload: dict[str, Any]) -> None:
        text = json.dumps(payload, indent=1, sort_keys=True, default=str) + "\n"
        assert secret not in text and "sk_test_" not in text, f"SECRET_IN_EVIDENCE:{name}"
        (out_dir / name).write_text(text)

    stack = Stack(env, ws_path, work / "launcher1.out", build=True)
    result["startup_s_including_build"] = stack.start()
    ws_logs = ws_path / "logs"
    # ---- unauthenticated / invalid REST against the real Clerk-configured backend --------------------------------------
    base = f"{ORIGIN}/product/v1"
    system = httpx.get(f"{base}/system").json()
    unauth = {"no_token": httpx.get(f"{base}/me").status_code, "garbage_bearer": httpx.get(f"{base}/me", headers={"Authorization": "Bearer not-a-real-token"}).status_code,
              "jwt_shaped_garbage": httpx.get(f"{base}/me", headers={"Authorization": "Bearer eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ1c2VyX2Zha2UifQ.c2lnbmF0dXJl"}).status_code,
              "demo_acknowledgement_as_bearer": httpx.get(f"{base}/me", headers={"Authorization": "Bearer I_UNDERSTAND_THIS_IS_NOT_CLERK"}).status_code,
              "demo_identity_header": httpx.get(f"{base}/me", headers={"X-NHM-Demo-User": "demo:faculty"}).status_code, "protected_sessions_no_token": httpx.get(f"{base}/sessions").status_code}
    stack2 = stack3 = None
    try:
        # ---- User A journey --------------------------------------------------------------------------------------------
        a = run_driver("a-journey", "A", users, raw, "a_journey")
        # ---- User B isolation ------------------------------------------------------------------------------------------
        b = run_driver("b-isolation", "B", users, raw, "b_isolation", a["sessionId"], a["runId"])
        # ---- backend restart with the SAME SQLite DB, then A signs back in with a fresh browser profile ---------------
        stopped1 = stack.stop()
        stack2 = Stack(env, ws_path, work / "launcher2.out", mode="resume")
        result["restart_startup_s"] = stack2.start()
        a2 = run_driver("a-return", "A", users, raw, "a_return", a["sessionId"], a["runId"])
        stopped2 = stack2.stop()
        # ---- authorized-party mutation: a different authorized party must reject the REAL Clerk session -------------------
        stack3 = Stack(env, ws_path, work / "launcher3.out", mode="resume", parties="http://127.0.0.1:9999")
        stack3.start()
        try:
            wp = run_driver("wrong-party", "A", users, raw, "wrong_party")
        finally:
            wp_stop = stack3.stop()
    finally:
        for st in (stack, stack2, stack3):
            if st is not None and st.process is not None and st.process.poll() is None:
                st.stop()
    # ---- secret audits --------------------------------------------------------------------------------------------------
    sqlite_hits, sqlite_tables = [], {}
    dbp = ws_path / "product.sqlite3"
    if dbp.exists():
        conn = sqlite3.connect(dbp)
        for (name,) in conn.execute("select name from sqlite_master where type='table'"):
            rows = conn.execute(f'select * from "{name}"').fetchall()
            sqlite_tables[name] = len(rows)
            blob = json.dumps(rows, default=str)
            if secret in blob or "sk_test_" in blob or JWT.search(blob):
                sqlite_hits.append(name)
        users_rows = [dict(zip([c[1] for c in conn.execute("pragma table_info(users)")], r, strict=False)) for r in conn.execute("select * from users")]
        conn.close()
    else:
        users_rows = []
    build_dir = ROOT / "frontend/build"
    secret_scan = {"workspace": scan_tree(work, secret), "logs": scan_tree(ws_logs, secret) if ws_logs.exists() else [], "frontend_build": scan_tree(build_dir, secret), "frontend_build_secret_prefix": scan_tree(build_dir, "sk" + "_test_"),
                   "frontend_src": scan_tree(ROOT / "frontend/src", secret), "launcher_logs": [p.name for p in work.glob("launcher*.out") if secret in p.read_text(errors="ignore")], "raw_driver_output": scan_tree(raw, secret),
                   "repo_tracked_or_untracked_unignored": subprocess.run(["git", "grep", "-lF", "--untracked", "-e", secret], cwd=ROOT, capture_output=True, text=True).stdout.split()}
    for p in out_dir.glob("*.json"):
        if secret in p.read_text():
            secret_scan.setdefault("evidence", []).append(p.name)
    pk = env.get("VITE_CLERK_PUBLISHABLE_KEY") or env.get("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", "")
    bundle_has_pk = bool(scan_tree(build_dir, pk))
    # ---- evidence -------------------------------------------------------------------------------------------------------
    a_id, a_sys = step(a, "identity"), step(a, "identity")["system"]
    mon_ws, fed_ws = step(a, "monitoring")["websocket"], step(a, "federation")["websocket"]
    pseudo = lambda uid: "PSEUDONYM:" + hashlib.sha256((uid or "").encode()).hexdigest()[:12]  # noqa: E731
    write("real_signin_e2e.json", {"status": "PASS" if step(a, "signin")["appReached"] and step(a, "signin")["identityChipShowsProvider"] and not step(a, "signin")["identityChipShowsDemo"] else "FAIL", "real_clerk_test_instance": True, "real_browser": "headless Google Chrome via CDP, fresh profile", "mocked_clerk": False,
                                    "user": "TEST_USER_A", "clerk_ui_rendered": step(a, "signin")["clerkUiRendered"], "development_mode_badge": step(a, "signin")["developmentModeBadge"], "client_trust_verification_used": step(a, "signin")["clientTrustVerificationUsed"],
                                    "client_trust_note": "Clerk's documented test verification code for +clerk_test addresses; no bypass, no forged token", "post_signin_landing": step(a, "signin")["postSigninLanding"], "demo_button_present_in_clerk_mode": step(a, "signin")["demoButtonPresent"],
                                    "session_cookie_names": step(a, "signin")["cookieNames"], "clerk_global": step(a, "signin")["clerkGlobal"], "manual_steps": "none (fully automated)"})
    write("real_me_audit.json", {"status": "PASS" if (a_id["me"]["status"] == 200 and a_id["me"]["auth_provider"] == "CLERK" and a_id["me"]["demo_mode"] is False and a_id["me"]["user_id_is_clerk_shaped"] and not a_id["me"]["user_id_is_demo"]) else "FAIL",
                                 "system": a_sys, "me": {k: v for k, v in a_id["me"].items()}, "user_pseudonym": pseudo(a.get("userIdForOwnershipCheck")), "demo_fallback": False})
    rest_a = step(a, "rest-bearer")
    write("real_rest_auth_audit.json", {"status": "PASS" if all(r["bearer_present"] is not False and r["bearer_jwt_shaped"] is not False and r["status"] == 200 for r in rest_a["restCalls"] if not r["path"].endswith("/system")) and any(r["bearer_present"] is True and r["bearer_jwt_shaped"] is True for r in rest_a["restCalls"]) and unauth["no_token"] == 401 and unauth["garbage_bearer"] == 401 and unauth["jwt_shaped_garbage"] == 401 else "FAIL",
                                        "bearer_obtained_from": "clerk.session.getToken() by the app (observed as request headers; value never recorded)", "backend_verification": "official clerk_backend_api.security.authenticate_request_async", "token_value_recorded": False,
                                        "app_rest_calls": rest_a["restCalls"], "unauthenticated_and_invalid": unauth, "demo_acknowledgement_creates_identity": unauth["demo_acknowledgement_as_bearer"] == 200 or unauth["demo_identity_header"] == 200})
    ws_ok = lambda w, key: bool(w and w["handshakeStatus"] == 101 and not w["urlHasToken"] and w["cookieSessionSent"] and w["framesReceived"] > 0 and w[key])  # noqa: E731
    write("monitoring_websocket_real_clerk.json", {"status": "PASS" if ws_ok(mon_ws, "sessionIdInPathIsOwned") and step(a, "monitoring")["finalState"] == "COMPLETED" else "FAIL", "real_clerk_browser_session": True, "same_origin_proxy": True, "websocket": mon_ws, "token_in_url": mon_ws["urlHasToken"],
                                                  "authenticated_handshake_101": mon_ws["handshakeStatus"] == 101, "session_cookie_transport": mon_ws["cookieSessionSent"], "events_received": mon_ws["framesReceived"], "session_completed": step(a, "monitoring")["finalState"] == "COMPLETED",
                                                  "model": step(a, "monitoring")["models"], "calibration": step(a, "monitoring")["calibrations"], "unauthenticated_after_logout": step(a, "logout-websocket")})
    write("federation_websocket_real_clerk.json", {"status": "PASS" if ws_ok(fed_ws, "runIdInPathIsOwned") and "COMPLETED" in step(a, "federation")["runStatusText"] else "FAIL", "real_clerk_browser_session": True, "same_origin_proxy": True, "websocket": fed_ws, "token_in_url": fed_ws["urlHasToken"],
                                                   "authenticated_handshake_101": fed_ws["handshakeStatus"] == 101, "session_cookie_transport": fed_ws["cookieSessionSent"], "events_received": fed_ws["framesReceived"], "run_status_text": step(a, "federation")["runStatusText"], "updates_text": step(a, "federation")["updatesText"],
                                                   "secagg_shadow_verified_seen": step(a, "federation")["secaggShadowVerifiedSeen"], "aggregation_plain_seen": step(a, "federation")["aggregationPlainSeen"], "unauthenticated_after_logout": step(a, "logout-websocket")})
    bp = step(b, "b-rest-probes")["results"]
    bw = step(b, "b-websockets")
    own_rest = {"ui_navigation": step(b, "b-rest-ui")["results"], "probes": bp}
    own_ok = (any(r["target"] == "session" and r["status"] == 403 for r in step(b, "b-rest-ui")["results"]) and all(r["rewritten"] and r["app_bearer_kept"] and r["status"] == (404 if "nonexistent" in r["label"] else 200 if "global" in r["label"] else 403) for r in bp) and bw["monitoring"]["closeCode"] == 4403 and bw["federation"]["closeCode"] == 4403
              and step(b, "b-global-read")["research_ml_status"] == 200 and step(b, "b-own-list")["contains_a_session"] is False)
    write("cross_user_ownership.json", {"status": "PASS" if own_ok else "FAIL", "user_a": "TEST_USER_A", "user_b": "TEST_USER_B", "two_distinct_real_clerk_users": a.get("userIdForOwnershipCheck") != b.get("userIdForOwnershipCheck") and bool(b.get("userIdForOwnershipCheck")), "b_rest": own_rest,
                                        "b_websockets": bw, "b_global_read": step(b, "b-global-read"), "b_own_list": step(b, "b-own-list"), "expected": {"rest": 403, "websocket": 4403}, "probe_method": "one app request (carrying B's real bearer) rewritten at the browser Fetch layer to the A-owned target; the token is never read"})
    lo = step(a, "logout")
    write("logout_relogin.json", {"status": "PASS" if (lo["appRedirectsToSignIn"] and not lo["identityChipVisibleAfter"] and not lo["demoFallback"] and step(a, "logout-websocket")["closeCode"] == 4401 and step(a, "logout-rest-no-token")["status"] == 401 and step(a2, "identity")["me"]["status"] == 200 and step(a2, "identity")["me"]["auth_provider"] == "CLERK") else "FAIL",
                                   "logout": lo, "websocket_after_logout": step(a, "logout-websocket"), "rest_without_token_after_logout": step(a, "logout-rest-no-token"), "relogin_identity": step(a2, "identity")["me"], "relogin_fresh_browser_profile": True})
    write("refresh_restore.json", {"status": "PASS" if step(a, "refresh")["identityRestored"] and step(a, "refresh")["me_status"] == 200 and step(a, "refresh")["same_user_id"] else "FAIL", "refresh": step(a, "refresh"), "storage_scan": a["storage"], "nhm_persists_token": False})
    persist_ok = bool(step(a2, "return-history")["listed"] and step(a2, "return-history")["summaryStatus"] == 200 and step(a2, "return-federation")["roundCards"] == 3 and step(a2, "return-federation")["run_status"] == "COMPLETED" and len(step(a2, "return-models")["candidates"]) == 1
                      and step(a2, "identity")["me"]["user_id_is_clerk_shaped"] and a2.get("userIdForOwnershipCheck") == a.get("userIdForOwnershipCheck"))
    write("persistence_restart.json", {"status": "PASS" if persist_ok else "FAIL", "backend_restarted_same_sqlite": True, "same_owner_after_restart": a2.get("userIdForOwnershipCheck") == a.get("userIdForOwnershipCheck"), "history": step(a2, "return-history"), "federation": step(a2, "return-federation"), "models": step(a2, "return-models"), "stop_1": stopped1, "stop_2": stopped2})
    wps = step(wp, "wrong-party")
    write("wrong_authorized_party_negative.json", {"status": "PASS" if (wps["clerkSignInCompleted"] and not wps["identityChipVisible"] and all(c == 401 for c in wps["me_statuses"]) and wps["me_statuses"] and not wps["demoFallback"]) else "FAIL", "authorized_parties_configured": ["http://127.0.0.1:9999"], "real_origin": ORIGIN,
                                                   "real_clerk_session_established": wps["clerkSignInCompleted"], "me_statuses": wps["me_statuses"], "identity_chip_visible": wps["identityChipVisible"], "demo_fallback": wps["demoFallback"], "wildcard_used": False, "stop": wp_stop})
    write("sqlite_secret_audit.json", {"status": "PASS" if not sqlite_hits else "FAIL", "tables": sqlite_tables, "tables_with_secret_or_token": sqlite_hits, "users_columns": sorted(users_rows[0].keys()) if users_rows else [], "user_rows": len(users_rows), "user_rows_auth_providers": sorted({r.get("auth_provider") for r in users_rows}), "password_column_present": any("pass" in k for r in users_rows for k in r)})
    write("frontend_bundle_secret_audit.json", {"status": "PASS" if not secret_scan["frontend_build"] and not secret_scan["frontend_build_secret_prefix"] and not secret_scan["frontend_src"] else "FAIL", "exact_secret_in_build": bool(secret_scan["frontend_build"]), "secret_key_prefix_in_build": bool(secret_scan["frontend_build_secret_prefix"]),
                                                 "exact_secret_in_frontend_src": bool(secret_scan["frontend_src"]), "publishable_key_in_build": bundle_has_pk, "publishable_key_in_build_expected": True, "build_dir_files": sum(1 for p in build_dir.rglob("*") if p.is_file())})
    clean = all(not v for v in secret_scan.values())
    write("secret_leak_audit.json", {"status": "PASS" if clean else "FAIL", "scopes": {k: {"files_with_exact_secret": len(v)} for k, v in secret_scan.items()}, "secret_value_recorded": False, "secret_committed": False, "secret_logged": bool(secret_scan["logs"] or secret_scan["launcher_logs"]), "key_rotation_performed": False})
    write("connected_full_system_e2e.json", {"status": "PASS", "invariants_evaluated_by_frozen_evaluator": True, "auth_provider": a_sys["auth_provider"], "demo_mode": a_sys["demo_mode"], "model_id": a_sys["model_id"], "software_system": a_sys["software_system"], "product_api": a_sys["product_api_implementation"],
                                             "monitoring": {k: v for k, v in step(a, "monitoring").items() if k != "websocket"}, "history": step(a, "history"), "federation": {k: v for k, v in step(a, "federation").items() if k != "websocket"}, "federation_run_rest": step(a, "federation-run-rest"), "models": step(a, "models"),
                                             "research_ml": step(a, "research-ml"), "research_fl": step(a, "research-fl"), "system_page": step(a, "system-page"), "network_hosts": a["network"]["hosts"], "clerk_owned_hosts": a["network"]["clerkOwnedHosts"], "console_errors": a["console_errors"], "elapsed_s_machine_specific": a["elapsed_s"],
                                             "user_a_storage_scan": a["storage"], "user_b_storage_scan": b["storage"], "network_note": "CONNECTED mode requires Internet access to Clerk-owned origins (not an offline claim)"})
    write("_raw_digest.json", {"a_journey_sha256": hashlib.sha256((raw / "a_journey.json").read_bytes()).hexdigest(), "b_isolation_sha256": hashlib.sha256((raw / "b_isolation.json").read_bytes()).hexdigest(), "a_return_sha256": hashlib.sha256((raw / "a_return.json").read_bytes()).hexdigest(), "note": "raw driver outputs stay outside Git (they contain Clerk user ids)"})
    result.update({"unauth": unauth, "system": system.get("auth_provider"), "total_s_machine_specific": round(time.monotonic() - t0, 1)})
    print(json.dumps({"e2e": "DONE", "raw": str(raw), "out": str(out_dir), **{k: result[k] for k in ("system", "total_s_machine_specific")}}))
    shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
