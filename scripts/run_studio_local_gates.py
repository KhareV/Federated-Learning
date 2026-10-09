# ruff: noqa: E501
"""Final local regression gates for NHM_UNIFIED_LIVE_FEDERATION_STUDIO_001 (run after the implementation is final, before the lock is frozen).

Runs the ENTIRE backend suite in chunks of test files (separate processes), the frontend unit suite, svelte-check, the production build and the real `--demo` launcher preflight.
Every failing test is recorded by name; nothing is allow-listed here. Writes reports/unified_live_fl/local_test_report.json and launcher_preflight.json."""

from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/unified_live_fl"
CHUNK = 30
BASELINE_SVELTE_WARNINGS = 123           # measured on the clean tree before any Studio change
EXCLUDED = {"test_studio_successor.py"}   # validates the FINAL lock itself: run right after the freeze (reports/unified_live_fl/successor_gate.json)


def run(cmd: list[str], cwd: Path = ROOT, env_extra: dict[str, str] | None = None) -> tuple[int, str, float]:
    started = time.time()
    done = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env={**os.environ, "PYTHONPATH": "src:.", **(env_extra or {})})
    return done.returncode, done.stdout + done.stderr, time.time() - started


def pytest_chunks() -> dict:
    files = sorted(p.name for p in (ROOT / "tests").glob("test_*.py") if p.name not in EXCLUDED)
    totals = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0, "chunks": 0, "seconds": 0.0, "failures": []}
    for i in range(0, len(files), CHUNK):
        group = [f"tests/{f}" for f in files[i:i + CHUNK]]
        code, out, seconds = run([sys.executable, "-m", "pytest", *group, "-q", "-p", "no:cacheprovider", "-rfE", "--tb=line"])
        tail = out.strip().splitlines()[-1] if out.strip() else ""
        for key in ("passed", "failed", "skipped", "error", "errors"):
            m = re.search(rf"(\d+) {key}\b", tail)
            if m:
                totals["errors" if key.startswith("error") else key] += int(m.group(1))
        totals["failures"] += re.findall(r"^(?:FAILED|ERROR) (\S+)", out, re.M)
        totals["chunks"] += 1
        totals["seconds"] += seconds
        print(f"chunk {totals['chunks']}: {tail}", flush=True)
        if code not in (0, 5) and not totals["failures"]:
            totals["failures"].append(f"CHUNK_{totals['chunks']}_EXIT_{code}")
    return totals


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    report: dict = {"started": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "environment": {"python": platform.python_version(), "platform": platform.platform()}, "steps": {}}
    code, out, sec = run(["npm", "run", "build"], ROOT / "frontend")
    report["steps"]["frontend_build"] = {"returncode": code, "seconds": round(sec, 1), "tail": out.strip().splitlines()[-1][:160] if out.strip() else ""}
    stamp_code, _stamp_out, _ = run([sys.executable, "-c", "from scripts.run_capstone_faculty_demo import build_frontend; print(build_frontend())"])   # writes the build stamp the launcher preflight checks
    report["steps"]["frontend_build"]["stamp_returncode"] = stamp_code
    py = pytest_chunks()
    report["steps"]["backend_pytest"] = py
    code, out, sec = run(["npx", "vitest", "run"], ROOT / "frontend")
    m = re.search(r"Tests\s+(?:(\d+) failed \| )?(\d+) passed(?: \| (\d+) skipped)?", out)
    report["steps"]["frontend_vitest"] = {"returncode": code, "failed": int(m.group(1) or 0) if m else None, "passed": int(m.group(2)) if m else None, "skipped": int(m.group(3) or 0) if m else None, "seconds": round(sec, 1)}
    code, out, sec = run(["npx", "svelte-check", "--tsconfig", "./tsconfig.json", "--output", "machine"], ROOT / "frontend")
    m = re.search(r"COMPLETED (\d+) FILES (\d+) ERRORS (\d+) WARNINGS", out)
    report["steps"]["svelte_check"] = {"files": int(m.group(1)), "errors": int(m.group(2)), "warnings": int(m.group(3)), "baseline_warnings": BASELINE_SVELTE_WARNINGS} if m else {"errors": None}
    code2, out2, _ = run([sys.executable, "-m", "scripts.run_nhm", "--demo", "--preflight-only"])
    try:
        checks = json.loads(out2.strip().splitlines()[-1])["preflight"]
    except (ValueError, KeyError, IndexError):
        checks = {}
    launcher = {"command": "python -m scripts.run_nhm --demo --preflight-only", "returncode": code2, "checks": checks, "passed": code2 == 0 and bool(checks) and all(checks.values())}
    (OUT / "launcher_preflight.json").write_text(json.dumps(launcher, indent=1, sort_keys=True) + "\n")
    report["steps"]["launcher_preflight"] = launcher
    steps = report["steps"]
    report["passed"] = bool(not py["failures"] and py["failed"] == 0 and py["errors"] == 0 and steps["frontend_vitest"]["failed"] == 0 and steps["frontend_vitest"]["returncode"] == 0 and steps["svelte_check"].get("errors") == 0
                            and steps["svelte_check"].get("warnings", 10**6) <= BASELINE_SVELTE_WARNINGS and steps["frontend_build"]["returncode"] == 0 and steps["frontend_build"]["stamp_returncode"] == 0 and launcher["passed"])
    report["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    report["note"] = "Any failing test is listed by name under backend_pytest.failures; none is allow-listed. A pre-existing monitoring race flake, if it appears, is reported there and judged separately."
    (OUT / "local_test_report.json").write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"passed": report["passed"], "pytest": {k: py[k] for k in ("passed", "failed", "skipped", "errors")}, "failures": py["failures"][:10]}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
