# ruff: noqa: E501
"""CAP-005 canonical frontend E2E (real stack, DEMO mode, no mock backend).

    PYTHONPATH=src:. python scripts/run_capstone_frontend_e2e.py --run N [--skip-build]

Processes: (1) fresh released SOFTWARE_SYSTEM_V2 inference service; (2) a CAP-004 product process on a
temporary SQLite file for the REAL-BACKEND frontend integration test (vitest, actual frontend client +
parser + LiveModel); (3) a second product process + `vite preview` of the PRODUCTION frontend build +
headless Chrome (CDP) driving the faculty flow in the browser with a host resolver that blocks every
non-loopback host (so any external dependency would fail loudly and be recorded).
Writes reports/capstone/cap_005/{frontend_integration.json,canonical_frontend_e2e.json,...}.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx

from scripts.run_capstone_monitoring_e2e import launch_released_inference
from scripts.run_capstone_persistent_e2e import db_evidence, free_port, product_process

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
OUT = ROOT / "reports/capstone/cap_005"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PREDECLARED = {"windows": 93, "valid": 86, "unusable": 7, "inference_results": 86, "event_count": 3157,
               "model_id": "MODEL_V2_FINAL", "calibration_id": "CAL_V2", "terminal": "COMPLETED",
               "monitoring_states": ["NORMAL_MONITORED_PATTERN", "CONTEXT_UNAVAILABLE", "NORMAL_MONITORED_PATTERN"],
               "gap": [118800, 124199]}


def tree_hash(path: Path, skip: tuple[str, ...] = ("node_modules", "build", ".svelte-kit")) -> dict[str, Any]:
    digest, count = hashlib.sha256(), 0
    for file in sorted(p for p in path.rglob("*") if p.is_file() and not any(part in skip for part in p.relative_to(path).parts)):
        digest.update(str(file.relative_to(path)).encode())
        digest.update(file.read_bytes())
        count += 1
    return {"sha256": digest.hexdigest(), "files": count}


def run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=FRONTEND, text=True, capture_output=True, **kwargs)


@contextlib.contextmanager
def preview_server(product_port: int):
    port = free_port()
    env = {**os.environ, "NHM_PRODUCT_API_PORT": str(product_port)}
    process = subprocess.Popen(["npm", "run", "preview", "--", "--port", str(port), "--strictPort", "--host", "127.0.0.1"],
                               cwd=FRONTEND, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    deadline = time.monotonic() + 60
    try:
        while True:
            try:
                if httpx.get(f"http://127.0.0.1:{port}/sign-in", timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            if process.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError("PREVIEW_LAUNCH_FAILED")
            time.sleep(0.3)
        yield f"http://127.0.0.1:{port}"
    finally:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(os.getpgid(process.pid), signal.SIGTERM) if False else process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()


@contextlib.contextmanager
def chrome(debug_port: int, profile: str):
    process = subprocess.Popen(
        [CHROME, "--headless=new", f"--remote-debugging-port={debug_port}", f"--user-data-dir={profile}",
         "--no-first-run", "--no-default-browser-check", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist", "--mute-audio",
         "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE localhost", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.monotonic() + 30
    try:
        while True:
            try:
                if httpx.get(f"http://127.0.0.1:{debug_port}/json/version", timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            if time.monotonic() > deadline:
                raise RuntimeError("CHROME_LAUNCH_TIMEOUT")
            time.sleep(0.3)
        yield process
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


def run_number() -> int:
    return int(sys.argv[sys.argv.index("--run") + 1]) if "--run" in sys.argv else 1


def main() -> int:
    n = run_number()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "logs").mkdir(exist_ok=True)
    shots = OUT / "screenshots" if n == 1 else OUT / "logs" / f"screenshots_run_{n}"
    shots.mkdir(parents=True, exist_ok=True)
    build_log = ""
    if "--skip-build" not in sys.argv:
        built = run(["npm", "run", "build"])
        build_log = (built.stdout + built.stderr)[-600:]
        if built.returncode != 0:
            print(build_log)
            return 1
    result: dict[str, Any] = {"run": n, "frontend_build": {"source": tree_hash(FRONTEND / "src"), "build_output": tree_hash(FRONTEND / "build", skip=()),
                                                  "build_log_tail": build_log, "adapter": "@sveltejs/adapter-static (production build served by vite preview)"},
                              "auth_mode": "DEMO (explicit, acknowledged)", "predeclared_invariants": PREDECLARED}
    with tempfile.TemporaryDirectory(prefix="cap005-") as tmp, launch_released_inference() as (inference_url, inference_info):
        result["inference_service"] = {k: v for k, v in inference_info.items() if k not in ("pid", "port")}
        # ---- A: real-backend frontend integration test (vitest) ---------------------------------
        db_a = os.path.join(tmp, "integration.sqlite3")
        evidence_a = OUT / f"frontend_integration_run_{n}.json"
        with product_process(db_a, inference_url) as (_base, _ws, _pid, port_a):
            env = {**os.environ, "NHM_REAL_PRODUCT_URL": f"http://127.0.0.1:{port_a}", "NHM_REAL_EVIDENCE_PATH": str(evidence_a)}
            tests = subprocess.run(["npx", "vitest", "run", "src/lib/product/__tests__/real-backend.integration.test.ts"], cwd=FRONTEND, env=env, text=True, capture_output=True, timeout=400)
            (OUT / "logs" / f"frontend_integration_run_{n}.log").write_text(tests.stdout[-4000:] + tests.stderr[-2000:])
            result["real_backend_integration"] = {"exit": tests.returncode, "evidence": f"frontend_integration_run_{n}.json",
                                                  "product_base": "real CAP-004 DEMO process (ephemeral port)", "passed": tests.returncode == 0}
        db_a_evidence = db_evidence(db_a)
        # ---- B: browser faculty flow against the production build ---------------------------------
        db_b = os.path.join(tmp, "browser.sqlite3")
        browser_out = OUT / "logs" / f"browser_run_{n}.json"
        with product_process(db_b, inference_url) as (base_b, _wsb, pid_b, port_b), preview_server(port_b) as origin:
            debug_port = free_port()
            with chrome(debug_port, os.path.join(tmp, "profile")):
                driver = subprocess.run(["node", str(ROOT / "scripts/cap_005_cdp_driver.mjs"), str(debug_port), origin, str(browser_out), str(shots)],
                                        cwd=ROOT, text=True, capture_output=True, timeout=600)
            (OUT / "logs" / f"browser_driver_run_{n}.log").write_text(driver.stdout[-4000:] + driver.stderr[-4000:])
            result["browser_driver_exit"] = driver.returncode
            result["product_process_pid_excluded"] = pid_b
            system = httpx.get(f"{base_b}/system").json()
            result["product_backend"] = {k: system[k] for k in ("product_api_implementation", "auth_provider", "demo_mode", "persistence_mode", "software_system", "model_id", "calibration_id", "hardware_mode", "physical_hardware_available")}
        db_b_evidence = db_evidence(db_b)
        # persistence after a product-process restart on the same database
        with product_process(db_b, inference_url) as (base_c, _wsc, _pidc, _p):
            result["after_product_restart"] = {"sessions": [{k: s[k] for k in ("session_id", "state")} for s in httpx.get(f"{base_c}/sessions").json()]}
    browser = json.loads(browser_out.read_text()) if browser_out.exists() else {}
    result["browser"] = browser
    result["database_after_browser_run"] = {k: db_b_evidence[k] for k in ("pragmas", "integrity_check", "foreign_key_check", "row_counts", "inference_models", "sessions", "devices", "users", "quality_rows", "waveform_preview", "withheld_context_cases")}
    result["database_after_integration_run"] = {k: db_a_evidence[k] for k in ("row_counts", "sessions", "inference_models")}
    (OUT / f"canonical_frontend_e2e_run_{n}.json").write_text(json.dumps(result, indent=1, sort_keys=True, default=str) + "\n")
    print(json.dumps({"integration_exit": result["real_backend_integration"]["exit"], "driver_exit": result["browser_driver_exit"],
                      "session_rows": db_b_evidence["row_counts"]["monitoring_sessions"], "external_origins": browser.get("network", {}).get("external")}))
    return 0 if result["real_backend_integration"]["passed"] and result["browser_driver_exit"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
