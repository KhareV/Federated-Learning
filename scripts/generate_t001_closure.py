#!/usr/bin/env python3
"""Generate T001 closure evidence from public GitHub Actions metadata."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "reports/t001/closure_verification.json"
API_ROOT = "https://api.github.com/repos/KhareV/Federated-Learning"
DEPENDENCY_POLICY = (
    "requirements-dev.lock is the exact CPython 3.11 project dependency resolution; "
    "reports/t001/dependencies.txt is a host-specific installed-environment snapshot"
)


def get_json(url: str) -> dict[str, Any]:
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "nhm-t001-closure",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def git_config(key: str) -> str | None:
    result = subprocess.run(
        ["git", "config", "--get", key],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() or None


def step_conclusion(steps: list[dict[str, Any]], name: str) -> str:
    match = next((step for step in steps if step.get("name") == name), None)
    return str(match.get("conclusion", "UNVERIFIED")).upper() if match else "UNVERIFIED"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True, type=int)
    args = parser.parse_args()

    run = get_json(f"{API_ROOT}/actions/runs/{args.run_id}")
    jobs = get_json(f"{API_ROOT}/actions/runs/{args.run_id}/jobs").get("jobs", [])
    artifacts = get_json(f"{API_ROOT}/actions/runs/{args.run_id}/artifacts").get(
        "artifacts", []
    )
    if len(jobs) != 1:
        raise RuntimeError(f"Expected one T001 job, found {len(jobs)}")
    steps = jobs[0].get("steps", [])
    runtime_artifact = next(
        (artifact for artifact in artifacts if str(artifact.get("name", "")).startswith("python-")),
        None,
    )
    python_version = (
        str(runtime_artifact["name"]).removeprefix("python-")
        if runtime_artifact
        else "UNVERIFIED"
    )
    ci = {
        "status": "PASS" if run.get("conclusion") == "success" else "FAIL",
        "run_id": str(run["id"]),
        "run_url": run["html_url"],
        "commit_sha": run["head_sha"],
        "python_version": python_version,
        "runtime_check": step_conclusion(steps, "Verify Python 3.11 runtime"),
        "lint": step_conclusion(steps, "Lint"),
        "pytest": step_conclusion(steps, "Pytest"),
        "smoke": step_conclusion(steps, "Smoke"),
        "workflow_conclusion": str(run.get("conclusion", "UNVERIFIED")).upper(),
    }
    all_ci_pass = all(
        ci[key] == "SUCCESS" for key in ("runtime_check", "lint", "pytest", "smoke")
    ) and ci["status"] == "PASS"
    configured_name = git_config("user.name")
    configured_email = git_config("user.email")
    git_author_status = (
        f"EXPLICITLY_CONFIGURED: {configured_name} <{configured_email}>"
        if configured_name and configured_email
        else "INFERRED_NOT_CONFIGURED: future commits require explicit user.name and user.email"
    )
    payload = {
        "phase": "T001",
        "spec_version": "2.2",
        "local_python_version": platform.python_version(),
        "python_311_ci": ci,
        "dependency_lock_policy": DEPENDENCY_POLICY,
        "git_author_status": git_author_status,
        "g0_status": "PASS" if all_ci_pass and python_version.startswith("3.11.") else "FAIL",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(OUTPUT)
    print(f"T001 closure: {payload['g0_status']}")


if __name__ == "__main__":
    main()
