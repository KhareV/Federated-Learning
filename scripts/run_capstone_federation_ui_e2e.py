# ruff: noqa: E501
"""CAP-008 canonical federation UI E2E (real stack, DEMO, offline, no mocks).

    PYTHONPATH=src:. python -m scripts.run_capstone_federation_ui_e2e [--skip-build]

(A) the real-backend frontend integration test (vitest: actual product client + federation parser +
    FederationLiveModel) against a REAL CAP-007 DEMO process running real local training;
(B) the faculty browser flow: production CAPSTONE_UI_V1_1 build served by `vite preview`, headless Chrome (CDP) with a
    host resolver that blocks every non-loopback host, a SECOND real CAP-007 process on a fresh SQLite + fresh
    federation/candidate roots: LIVE_RUN (FEDAVG + SECAGG_SHADOW) -> models -> privacy -> reload persistence -> REPLAY ->
    refresh during a second genuine run -> responsive/accessibility/network audits;
(C) persistence after a product-process restart on the same database.
Writes the evidence JSON files under reports/capstone/cap_008/ (``CAP008_OUT`` overrides)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import httpx

from scripts.run_capstone_federation import product
from scripts.run_capstone_frontend_e2e import chrome, preview_server, run, tree_hash
from scripts.run_capstone_persistent_e2e import free_port

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
OUT = Path(os.environ.get("CAP008_OUT", ROOT / "reports/capstone/cap_008"))


def write(name: str, payload: Any) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(payload, indent=1, sort_keys=True, default=str) + "\n")


def main() -> int:
    (OUT / "logs").mkdir(parents=True, exist_ok=True)
    shots = OUT / "screenshots"
    shots.mkdir(parents=True, exist_ok=True)
    build_log = ""
    if "--skip-build" not in sys.argv:
        built = run(["npm", "run", "build"])
        build_log = (built.stdout + built.stderr)[-500:]
        if built.returncode != 0:
            print(build_log)
            return 1
    build = {"source": tree_hash(FRONTEND / "src"), "build_output": tree_hash(FRONTEND / "build", skip=()), "adapter": "@sveltejs/adapter-static (production build served by vite preview)", "build_log_tail": build_log}
    with tempfile.TemporaryDirectory(prefix="cap008-") as tmp:
        # ---- A: real-backend integration --------------------------------------------------------
        root_a = Path(tmp) / "integration"
        evidence_a = OUT / "logs" / "integration_raw.json"
        with product(root_a) as a:
            env = {**os.environ, "NHM_REAL_PRODUCT_URL": f"http://127.0.0.1:{a.port}", "NHM_REAL_EVIDENCE_PATH": str(evidence_a)}
            tests = subprocess.run(["npx", "vitest", "run", "src/lib/product/federation/__tests__/real-backend.integration.test.ts"], cwd=FRONTEND, env=env, text=True, capture_output=True, timeout=700)
            (OUT / "logs" / "integration_vitest.log").write_text(tests.stdout[-4000:] + tests.stderr[-2000:])
        integration = {"exit": tests.returncode, "passed": tests.returncode == 0, "backend": "real CAP-007 DEMO process, real local training, no fixtures", "evidence": json.loads(evidence_a.read_text()) if evidence_a.exists() else None}
        write("real_backend_frontend_integration.json", integration)
        # ---- B: browser flow -------------------------------------------------------------------
        root_b = Path(tmp) / "browser"
        browser_out = OUT / "logs" / "browser_raw.json"
        with product(root_b) as b, preview_server(b.port) as origin:
            debug_port = free_port()
            with chrome(debug_port, os.path.join(tmp, "profile")):
                driver = subprocess.run(["node", str(ROOT / "scripts/cap_008_cdp_driver.mjs"), str(debug_port), origin, str(browser_out), str(shots)], cwd=ROOT, text=True, capture_output=True, timeout=1500)
            (OUT / "logs" / "browser_driver.log").write_text(driver.stdout[-4000:] + driver.stderr[-4000:])
            system = httpx.get(f"{b.http}/system").json()
            backend = {k: system[k] for k in ("product_api_implementation", "auth_provider", "demo_mode", "persistence_mode", "federation_runtime", "software_system", "model_id", "hardware_mode", "physical_hardware_available")}
            pid_b = b.pid
        # ---- C: restart persistence --------------------------------------------------------------
        with product(root_b) as c:
            after_restart = {"models": httpx.get(f"{c.http}/models").json(), "runs": [{k: r[k] for k in ("run_id", "run_type", "status", "candidate_ids")} for r in httpx.get(f"{c.http}/federation/runs").json()]}
    browser = json.loads(browser_out.read_text()) if browser_out.exists() else {}
    steps = {s["step"]: s for s in browser.get("steps", [])}
    ident = {"frontend_build": build, "product_backend": backend, "auth_mode": "DEMO (explicit, acknowledged); Clerk not initialised", "backend_pid_excluded": pid_b, "internet": "blocked by --host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE localhost"}
    live, models, replay, refresh = steps.get("live-run-1"), steps.get("models"), steps.get("replay"), steps.get("refresh-during-run")
    write("canonical_federation_browser_e2e.json", {**ident, "driver_exit": driver.returncode, "steps": [steps.get(k) for k in ("app-overview", "federation-overview", "configuration", "live-run-1", "models", "privacy", "reload-persistence")], "after_backend_restart": after_restart,
                                                    "candidate_count_before_live_run": steps.get("federation-overview", {}).get("overviewBefore", {}).get("candidate_count"), "elapsed_s": browser.get("elapsed_s"), "console_errors": browser.get("console_errors")})
    write("canonical_replay_browser_e2e.json", {**ident, "replay": replay})
    write("refresh_during_run.json", {**ident, "refresh": refresh})
    write("offline_network_audit.json", {**ident, "network": browser.get("network"), "console_errors": browser.get("console_errors")})
    write("responsive_audit.json", {"responsive": steps.get("responsive"), "screenshots": sorted(p.name for p in shots.glob("*.png"))})
    write("accessibility_audit.json", {"accessibility": steps.get("accessibility"), "keyboard": steps.get("keyboard"), "formal_wcag_certification_claimed": False})
    write("browser_raw_summary.json", {"steps": sorted(steps), "live": bool(live), "models": bool(models)})
    print(json.dumps({"integration_exit": tests.returncode, "driver_exit": driver.returncode, "external_origins": (browser.get("network") or {}).get("external")}))
    return 0 if tests.returncode == 0 and driver.returncode == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
