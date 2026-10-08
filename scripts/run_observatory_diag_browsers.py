# ruff: noqa: E501
"""OBS-DIAG-001: start the offline DEMO development stack (batch capture ON), run the diag smoke and the accessibility assessment in every available Chromium build.
Firefox is not installed and Safari remote automation is disabled in this environment; they are recorded as NOT TESTED, never assumed.
  python -m scripts.run_observatory_diag_browsers"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/observatory/obs_diag_001"
BROWSERS = {
    "chrome_stable": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "chrome_for_testing": str(Path.home() / "Library/Caches/ms-playwright/chromium-1243/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"),
}


def free_port() -> int:
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def launch(executable: str, port: int, profile: str) -> subprocess.Popen:
    proc = subprocess.Popen([executable, "--headless=new", f"--remote-debugging-port={port}", f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check", "--mute-audio", "--disable-gpu", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(100):
        try:
            if httpx.get(f"http://127.0.0.1:{port}/json/version", timeout=2).status_code == 200:
                return proc
        except httpx.HTTPError:
            time.sleep(0.3)
    raise RuntimeError("BROWSER_LAUNCH_TIMEOUT")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="obsdiag-browsers-"))
    env = {**os.environ, "PYTHONPATH": "src:.", "NHM_PRODUCT_AUTH_MODE": "DEMO", "NHM_PRODUCT_DEMO_AUTH_ACK": "I_UNDERSTAND_THIS_IS_NOT_CLERK", "NHM_PRODUCT_DB_PATH": str(work / "p.sqlite3"),
           "NHM_FEDERATION_ARTIFACT_ROOT": str(work / "fed"), "NHM_FL_CANDIDATE_ROOT": str(work / "cand"), "NHM_OBSERVATORY_BATCH_CAPTURE": "1", "NHM_PRODUCT_API_PORT": "8002"}
    api = subprocess.Popen([sys.executable, "-m", "scripts.run_observatory_product", "--port", "8002"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    vite = subprocess.Popen(["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", "5173", "--strictPort"], cwd=ROOT / "frontend", env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    results: dict[str, object] = {"browsers_tested": [], "browsers_not_tested": {"firefox": "not installed in this environment", "webkit_safari": "Safari 'Allow remote automation' is disabled; enabling it requires a manual settings change"}}
    try:
        for _ in range(120):
            try:
                if httpx.get("http://127.0.0.1:5173/sign-in", timeout=3).status_code == 200 and httpx.get("http://127.0.0.1:8002/product/v1/system", headers={"X-Demo-User": "x"}, timeout=3).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(1)
        for name, executable in BROWSERS.items():
            if not Path(executable).exists():
                results["browsers_not_tested"][name] = "executable not found"  # type: ignore[index]
                continue
            for script, args, key in (("observatory_diag_smoke.mjs", [str(OUT / f"smoke_{name}")], "diag_smoke"), ("observatory_a11y_assessment.mjs", [str(OUT / f"a11y_{name}.json")], "a11y")):
                port = free_port()
                profile = tempfile.mkdtemp(prefix=f"obsdiag-{name}-")
                browser = launch(executable, port, profile)
                try:
                    cmd = ["node", str(ROOT / f"scripts/{script}"), str(port), "http://127.0.0.1:5173", *args]
                    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=1500)
                    results[f"{name}:{key}"] = {"exit_code": r.returncode, "tail": (r.stdout + r.stderr)[-400:]}
                finally:
                    browser.terminate()
                    shutil.rmtree(profile, ignore_errors=True)
            results["browsers_tested"].append(name)  # type: ignore[attr-defined]
        (OUT / "browser_runner.json").write_text(json.dumps(results, indent=1) + "\n")
        print(json.dumps({k: (v if not isinstance(v, dict) else v.get("exit_code")) for k, v in results.items() if k != "browsers_not_tested"}))
        return 0
    finally:
        for proc in (vite, api):
            proc.send_signal(signal.SIGINT)
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
