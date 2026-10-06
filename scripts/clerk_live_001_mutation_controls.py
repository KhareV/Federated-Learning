# ruff: noqa: E501
"""CLERK-LIVE-001 mutation / negative controls (20). Each mutation is applied to a TEMPORARY copy or synthetic evidence, must fail a
NAMED check of the frozen connected layer, and leaves the working tree byte-identical (verified with git status).
Writes reports/clerk_connected/clerk_live_001/mutation_controls.json (or CLERK_EVD)."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from scripts import clerk_connected_lib as lib
from scripts import run_capstone_clerk_connected as launcher

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get("CLERK_EVD", ROOT / "reports/clerk_connected/clerk_live_001"))
SECRET = "sk_test_" + "Z" * 28
PK = "pk_test_" + "ZXhhbXBsZS1hcHAtMTIzNC5jbGVyay5hY2NvdW50cy5kZXYk"
GOOD_WS = {"handshakeStatus": 101, "urlHasToken": False, "cookieSessionSent": True, "framesReceived": 7, "sessionIdInPathIsOwned": True, "runIdInPathIsOwned": True}
PROBES = [{"label": "read A session", "rewritten": True, "app_bearer_kept": True, "status": 403}, {"label": "start A run (control)", "rewritten": True, "app_bearer_kept": True, "status": 403},
          {"label": "CONTROL: nonexistent session", "rewritten": True, "app_bearer_kept": True, "status": 404}, {"label": "CONTROL: global research view", "rewritten": True, "app_bearer_kept": True, "status": 200}]
B_WS = {"monitoring": {"closeCode": 4403, "frames": 0}, "federation": {"closeCode": 4403, "frames": 0}}
UI = [{"target": "session", "status": 403}]
MODELS = {"candidate": [{"production_deployed": False, "governance_status": "ACCEPTED_TO_SANDBOX", "sandbox_status": "IN_SANDBOX", "state_digest": "d1"}], "released_default": "MODEL_V2_FINAL", "controls": []}
DEMO_OK = {"demo_auth_works": True, "equals_cap_010_canonical_digest": True, "clerk_global_in_browser": False, "external_requests": [], "blocked_external_requests": [], "clerk_origins_contacted": []}


def frontend_copy() -> Path:
    d = Path(tempfile.mkdtemp(prefix="clkmut_"))
    shutil.copytree(ROOT / "frontend/src", d / "frontend/src")
    shutil.copy(ROOT / "frontend/vite.config.ts", d / "frontend/vite.config.ts")
    return d


def with_frontend(content: str, failure: str):
    d = frontend_copy()
    try:
        (d / "frontend/src/lib/product/injected.ts").write_text(content)
        r = lib.frontend_static_audit(d, SECRET)
        return (failure in r["failures"]), failure
    finally:
        shutil.rmtree(d, ignore_errors=True)


def secret_in(kind: str):
    d = Path(tempfile.mkdtemp(prefix="clkmut_"))
    try:
        if kind == "sqlite":
            db = d / "p.sqlite3"
            conn = sqlite3.connect(db)
            conn.execute("create table users (user_id text, display_name text)")
            conn.execute("insert into users values ('user_x', ?)", (SECRET,))
            conn.commit()
            conn.close()
            return bool(lib.sqlite_secret_hits(db, SECRET)), "sqlite_secret_audit"
        (d / ("app.js" if kind == "build" else "product.log")).write_text(f"value={SECRET}")
        return bool(lib.find_secret(d, SECRET)), "frontend_bundle_secret_audit" if kind == "build" else "secret_leak_audit"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def clerk_falls_back():
    class R:
        status_code = 200

        def json(self):
            return {"product_api_implementation": "CAPSTONE_PRODUCT_API_V1_3", "software_system": "SOFTWARE_SYSTEM_V2", "model_id": "MODEL_V2_FINAL", "persistence_mode": "SQLITE", "auth_provider": "DEMO", "demo_mode": True, "federation_runtime": "ENABLED_ENGINEERING", "hardware_mode": "SIMULATED_ONLY"}

    original = launcher.httpx.get
    launcher.httpx.get = lambda *a, **k: R()
    try:
        ready, _ = launcher.clerk_probe_product(8002)
    finally:
        launcher.httpx.get = original
    return (ready is False), "clerk_probe_product (readiness)"


def wildcard():
    try:
        launcher.resolve_config({"NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY": PK, "CLERK_SECRET_KEY": SECRET, "NHM_CLERK_AUTHORIZED_PARTIES": "*"}, 4173)
    except launcher.ConnectedConfigError as error:
        return True, f"resolve_config:{error}"[:80]
    return False, "wildcard accepted"


def tmp_tree(rel: str, name: str, body: str, check):
    d = Path(tempfile.mkdtemp(prefix="clkmut_"))
    try:
        (d / "product/auth").mkdir(parents=True)
        (d / "api").mkdir()
        (d / "product/federation").mkdir(parents=True)
        (d / "product/auth/clerk.py").write_text("from clerk_backend_api.security import authenticate_request_async\n")
        (d / rel).mkdir(parents=True, exist_ok=True)
        (d / rel / name).write_text(body)
        return check(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)


MUTATIONS = (
    ("SECRET_IN_FRONTEND_SOURCE", lambda: with_frontend(f"export const leaked = '{SECRET}';", "frontend_source_contains_secret")),
    ("SECRET_IN_FRONTEND_BUILD", lambda: secret_in("build")),
    ("SECRET_PRINTED_IN_LOG", lambda: secret_in("log")),
    ("SECRET_WRITTEN_TO_SQLITE", lambda: secret_in("sqlite")),
    ("FRONTEND_USES_NEXT_PUBLIC_DIRECTLY", lambda: with_frontend("export const k = import.meta.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;", "frontend_reads_NEXT_PUBLIC")),
    ("CLERK_MODE_FALLS_BACK_TO_DEMO", clerk_falls_back),
    ("WILDCARD_AUTHORIZED_PARTY_ACCEPTED", wildcard),
    ("WEBSOCKET_TOKEN_IN_URL", lambda: ((not lib.ws_evidence_ok({**GOOD_WS, "urlHasToken": True}, "sessionIdInPathIsOwned")), "monitoring_ws_no_token")),
    ("MONITORING_WS_ACCEPTS_UNAUTHENTICATED", lambda: ((not lib.unauth_ws_rejected({"closeCode": 1000, "frames": 12})), "logout_ok (monitoring socket after logout)")),
    ("FEDERATION_WS_ACCEPTS_UNAUTHENTICATED", lambda: ((not lib.unauth_ws_rejected({"closeCode": None, "frames": 4})), "logout_ok (federation socket after logout)")),
    ("USER_B_READS_USER_A_SESSION", lambda: ((not lib.ownership_ok([{"target": "session", "status": 200}], PROBES, B_WS)["ok"]), "ownership_rest")),
    ("USER_B_CONNECTS_TO_USER_A_MONITORING_WS", lambda: ((not lib.ownership_ok(UI, PROBES, {**B_WS, "monitoring": {"closeCode": None, "frames": 30}})["ok"]), "ownership_monitoring_ws")),
    ("USER_B_CONTROLS_USER_A_FEDERATION_RUN", lambda: ((not lib.ownership_ok(UI, [PROBES[0], {**PROBES[1], "status": 200}, *PROBES[2:]], B_WS)["ok"]), "ownership_federation")),
    ("USER_B_CONNECTS_TO_USER_A_FEDERATION_WS", lambda: ((not lib.ownership_ok(UI, PROBES, {**B_WS, "federation": {"closeCode": 1000, "frames": 202}})["ok"]), "ownership_federation")),
    ("CLERK_IDENTITY_CHANGES_MODEL_OR_CHECKPOINT", lambda: ((not lib.noninterference_ok(MODELS, {"model_id": "CAPSTONE_FL_CANDIDATE_0001"}, "d1", {})["ok"]) and (not lib.noninterference_ok(MODELS, {"model_id": "MODEL_V2_FINAL"}, "d2", {})["ok"]), "identity_no_ml_selection")),
    ("MONITORING_SESSION_FEEDS_FL", lambda: tmp_tree("product/federation", "leak.py", "from product.history import summaries\n", lambda d: ((not lib.fl_isolation_static(d)["ok"]), "fl_isolation"))),
    ("CONNECTED_INTEGRATION_BREAKS_DEMOAUTH", lambda: ((lib.demo_regression_ok(DEMO_OK)["ok"] and not lib.demo_regression_ok({**DEMO_OK, "clerk_global_in_browser": True})["ok"] and not lib.demo_regression_ok({**DEMO_OK, "demo_auth_works": False})["ok"]), "demo_no_clerk")),
    ("CANDIDATE_BECOMES_DEPLOYED", lambda: ((not lib.candidate_ok({**MODELS, "candidate": [{**MODELS["candidate"][0], "production_deployed": True}]})["ok"]), "not_deployed")),
    ("CUSTOM_JWT_VERIFICATION_ADDED", lambda: tmp_tree("product/auth", "custom.py", "import jwt\n", lambda d: ((not lib.backend_static_audit(d)["ok"]), "no_custom_crypto"))),
    ("HISTORICAL_RELEASE_TAG_MOVED", lambda: ((lib.tag_ok(lib.HISTORICAL_RELEASE_TARGET) and not lib.tag_ok("0" * 40)), "tag_unchanged")),
)


def main() -> int:
    before = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout
    results = []
    for name, fn in MUTATIONS:
        try:
            caught, failing = fn()
        except Exception as error:   # an exception is not a catch
            caught, failing = False, f"EXCEPTION:{type(error).__name__}"
        after = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout
        results.append({"mutation": name, "caught": bool(caught), "failing_check": failing[:120], "restored": after == before, "applied_to": "temporary copy / synthetic evidence"})
        print(name, caught, failing[:60], flush=True)
    payload = {"controls": results, "all_caught": all(r["caught"] for r in results), "all_restored": all(r["restored"] for r in results), "count": len(results)}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "mutation_controls.json").write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: payload[k] for k in ("count", "all_caught", "all_restored")}))
    return 0 if payload["all_caught"] and payload["all_restored"] else 1


if __name__ == "__main__":
    sys.exit(main())
