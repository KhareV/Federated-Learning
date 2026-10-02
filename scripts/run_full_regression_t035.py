#!/usr/bin/env python3
"""T035-REPRO full local regression: Ruff, full pytest, pip check, and (if frontend/
node_modules is present) the frontend Vitest/svelte-check/build suite. Writes
reports/t035/full_test_report.json and the canonical reports/test_report.json (TEST01).
Intended to be invoked with the SAME interpreter/venv the caller wants audited -- it shells
out to `python -m ruff` / `python -m pytest` / `python -m pip check` using sys.executable, and
to `npm` for the frontend, so it is equally valid run from the developer tree or a clean
checkout.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
OUT = ROOT / "reports/t035"


def _run(cmd: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> dict[str, object]:
    import os

    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    start = time.monotonic()
    result = subprocess.run(
        cmd, cwd=cwd, env=full_env, capture_output=True, text=True, check=False
    )
    return {
        "command": " ".join(cmd),
        "cwd": str(cwd.relative_to(ROOT)) if cwd.is_relative_to(ROOT) else str(cwd),
        "exit_code": result.returncode,
        "duration_seconds": round(time.monotonic() - start, 3),
        "stdout_tail": "\n".join(result.stdout.splitlines()[-40:]),
        "stderr_tail": "\n".join(result.stderr.splitlines()[-40:]),
    }


def _pytest_counts(stdout_tail: str) -> dict[str, int | None]:
    for line in reversed(stdout_tail.splitlines()):
        if " passed" in line or " failed" in line or " error" in line:
            import re

            counts = {}
            for key in ("passed", "failed", "skipped", "error", "errors"):
                match = re.search(rf"(\d+) {key}", line)
                if match:
                    counts[key] = int(match.group(1))
            if counts:
                return counts
    return {}


def main() -> None:
    env = {"PYTHONPATH": "src:."}
    steps: dict[str, dict[str, object]] = {}

    steps["ruff"] = _run(
        [
            sys.executable, "-m", "ruff", "check",
            "src", "tests", "scripts", "simulation", "deployment", "fusion", "api",
            "datasets", "features", "models", "training", "evaluation", "preprocessing",
        ],
        cwd=ROOT,
        env=env,
    )

    steps["pip_check"] = _run([sys.executable, "-m", "pip", "check"], cwd=ROOT)

    steps["pytest"] = _run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT, env=env)
    steps["pytest"]["counts"] = _pytest_counts(str(steps["pytest"]["stdout_tail"]))

    frontend_steps: dict[str, dict[str, object]] = {}
    if (FRONTEND / "node_modules").exists():
        frontend_steps["vitest"] = _run(["npm", "run", "test", "--", "--run"], cwd=FRONTEND)
        frontend_steps["svelte_check"] = _run(["npm", "run", "check"], cwd=FRONTEND)
        frontend_steps["build"] = _run(["npm", "run", "build"], cwd=FRONTEND)
    else:
        frontend_steps["note"] = {"skipped": "frontend/node_modules not present; run npm ci first"}

    report = {
        "report_version": "1.0",
        "task_id": "T035",
        "requirement": "TEST01",
        "python_executable": sys.executable,
        "python_version": sys.version.split()[0],
        "steps": steps,
        "frontend_steps": frontend_steps,
        "status": (
            "PASS"
            if steps["ruff"]["exit_code"] == 0
            and steps["pip_check"]["exit_code"] == 0
            and steps["pytest"]["exit_code"] == 0
            and all(
                s.get("exit_code", 0) == 0
                for s in frontend_steps.values()
                if isinstance(s, dict) and "exit_code" in s
            )
            else "FAIL"
        ),
    }

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "full_test_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (ROOT / "reports/test_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    summary = {k: v for k, v in report.items() if k != "steps"}
    print(json.dumps(summary, indent=2))
    step_summary = {
        name: {k: v for k, v in step.items() if k not in ("stdout_tail", "stderr_tail")}
        for name, step in steps.items()
    }
    print(json.dumps(step_summary, indent=2))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
