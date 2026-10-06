# ruff: noqa: E501
"""FINAL-EVAL-REPAIR-002 real-browser verification (records observations; the frozen FERG1 evaluator defines pass/fail).
  python -m scripts.final_eval_repair_002_e2e --env-file <env outside Git> --users-file <json outside Git> --out <evidence dir> --raw <scratch dir> [--label NAME]
Runs: Clerk-connected launcher (build) -> TEST_USER_A product journey -> full route crawl (FER-001 harness, reused) -> FER-002 browser audit (public landing unauthenticated + product pages signed in:
4 widths, reduced-motion rAF/animation counting, skip-link keyboard test, landmarks, computed target sizes) -> owner-bound federation regression. No token/cookie/secret is recorded."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from scripts import final_eval_repair_002_entry_evidence as ee
from scripts import final_eval_repair_crawl_analysis as ca
from scripts import final_eval_repair_e2e as e1
from scripts import final_eval_repair_lib as lib
from scripts import ufl_lite_003_e2e as ufl
from scripts import ufl_lite_003_lib as ual
from scripts import ufl_lite_lib as ulib
from scripts.run_capstone_clerk_connected import parse_env_file
from scripts.run_capstone_clerk_connected_e2e import (
    JWT,
    ORIGIN,
    Browser,
    Stack,
    free_port,
    run_driver,
    scan_tree,
)

ROOT = lib.ROOT
BROWSER = ROOT / "scripts/final_eval_repair_002_browser.mjs"
PRODUCT_PAGES = ("/sign-in", "/app", "/app/device", "/app/monitoring", "/app/history", "/app/federation", "/app/federation/clients", "/app/federation/privacy", "/app/models", "/app/research/ml", "/app/research/fl", "/app/system", "/app/about")


def browser_audit(name: str, who: str, routes: list[dict[str, Any]], users: Path | None, raw: Path) -> dict[str, Any]:
    prof = Path(tempfile.mkdtemp(prefix=f"fer2-prof-{name}-"))
    port = free_port()
    b = Browser(prof, port)
    rf = raw / f"{name}_routes.json"
    rf.write_text(json.dumps(routes))
    out = raw / f"{name}.json"
    try:
        r = subprocess.run(["node", str(BROWSER), str(port), ORIGIN, str(users) if users else "-", who, str(out), str(raw / f"shots_{name}"), str(rf)], capture_output=True, text=True, timeout=3400)
        if r.returncode or not out.exists():
            raise RuntimeError(f"BROWSER_AUDIT_FAILED:{name}:{(r.stdout + r.stderr)[-500:]}")
    finally:
        b.close()
        shutil.rmtree(prof, ignore_errors=True)
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
    work = Path(tempfile.mkdtemp(prefix="fer2-e2e-"))
    t0 = time.monotonic()

    def write(name: str, payload: dict[str, Any]) -> None:
        text = json.dumps(payload, indent=1, sort_keys=True, default=str) + "\n"
        assert secret not in text and "sk_test_" not in text and not JWT.search(text), f"SECRET_IN_EVIDENCE:{name}"
        (out_dir / name).write_text(text)

    stack = Stack(env, work / "workspace", work / "launcher.out", build=True)
    stack.start()
    try:
        a = run_driver("a-journey", "A", users, raw, "a_journey")
        sid, rid = a["sessionId"], a["runId"]
        policy = json.loads((ROOT / "configs/final_eval_repair/legacy_route_policy_v1.json").read_text())
        sample = {"/app/history/[session_id]": f"/app/history/{sid}", "/app/federation/live": f"/app/federation/live?run={rid}", "/app/federation/rounds": f"/app/federation/rounds?run={rid}"}
        routes = []
        for row in policy["routes"]:
            if row["class"] == "CATCH_ALL":
                continue
            path = sample.get(row["pattern"], row["pattern"])
            item = {"path": path, "cls": row["class"]}
            if row["pattern"] in e1.DEEP or row["pattern"] in {"/app/history/[session_id]", "/app/federation/live"}:
                item["reload"] = True
            if "live?run" in path:
                item["ready"] = "!!document.querySelector('[data-testid=client-grid]')"
            if "rounds?run" in path:
                item["ready"] = "document.querySelectorAll('[data-testid=round-cards] li').length===3"
            routes.append(item)
        routes.append({"path": "/this-route-does-not-exist", "cls": "UNKNOWN"})
        c = e1.crawl("crawl_authed", "A", routes, users, raw)
        landing = browser_audit("landing_unauth", "-", [{"path": "/", "wait": 7000}], None, raw)
        prod_routes = [{"path": p, "wait": 4000} for p in PRODUCT_PAGES] + [{"path": f"/app/history/{sid}", "wait": 4000}, {"path": f"/app/federation/live?run={rid}", "ready": "!!document.querySelector('[data-testid=client-grid]')", "wait": 4000}]
        prod = browser_audit("product_authed", "A", prod_routes, users, raw)
        o = ufl.run_driver("owner-live", "A", users, raw, "owner_live")
    finally:
        if stack.process is not None and stack.process.poll() is None:
            stack.stop()
    cs = ca.sanitize(c)
    analysis = ca.analyze_crawl(cs, policy, sample)
    matrix = ca.truth_matrix(cs, sample)
    base = ulib.load_baseline(ROOT)
    f, auth = ual.step(o, "live-completed"), ual.step(o, "live-authoritative")
    models, rp = ual.step(o, "models-after-live"), ual.step(o, "replay")
    owner = {"identity": ual.analyze_identity(ual.step(o, "signin")), "live": ual.analyze_live(f, auth, ual.step(o, "clients-rest"), base), "candidate": {k: v for k, v in ual.analyze_candidate(models, auth).items() if k != "one_candidate"}, "refresh": ual.analyze_refresh(ual.step(o, "refresh-mid-run")),
             "websocket": ual.analyze_ws(o["websockets"]), "rounds_page": ual.analyze_rounds_page(ual.step(o, "rounds-page")), "global": ual.analyze_global(ual.step(o, "global-clients-view")), "replay": ual.analyze_replay(rp, auth, ual.step(o, "models-after-replay"), models)}
    cands = models.get("candidates") or []
    owner["candidate"]["all_candidates_canonical"] = bool(cands) and all(x["state_digest"] == ual.CANDIDATE for x in cands)
    sec = {"raw": scan_tree(raw, secret), "build": scan_tree(ROOT / "frontend/build", secret), "src": scan_tree(ROOT / "frontend/src", secret), "prefix_build": scan_tree(ROOT / "frontend/build", "sk" + "_test_"), "workspace": scan_tree(work, secret), "jwt_in_raw": [p.name for p in raw.glob("*.json") if JWT.search(p.read_text())]}
    san = ca.sanitize
    write("landing_claim_inventory_final.json", {"label": args.label, **ee.inventory(ROOT)})
    write("route_crawl_final.json", {"label": args.label, "real_clerk_test_instance": True, "fresh_browser_profile": True, "observations": cs, "analysis": analysis, "sample": sample})
    write("copy_truth_matrix_final.json", {"label": args.label, **matrix})
    write("landing_browser_audit.json", {"label": args.label, "observations": san(landing)})
    write("product_browser_audit.json", {"label": args.label, "real_clerk_test_instance": True, "observations": san(prod)})
    write("connected_owner_binding_regression.json", {"label": args.label, "real_clerk_test_instance": True, "groups": {k: {"checks": v, "all_pass": all(v.values())} for k, v in owner.items()}, "all_pass": all(all(v.values()) for v in owner.values()), "observations": o})
    write("secret_audit.json", {"label": args.label, "scopes": {k: len(v) for k, v in sec.items()}, "clean": all(not v for v in sec.values()), "secret_value_recorded": False})
    shutil.rmtree(work, ignore_errors=True)
    print(json.dumps({"e2e": "DONE", "label": args.label, "crawl_all_pass": analysis["all_pass"], "matrix_consistent": matrix["consistent"], "owner_all_pass": all(all(v.values()) for v in owner.values()), "secrets_clean": all(not v for v in sec.values()), "total_s": round(time.monotonic() - t0, 1)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
