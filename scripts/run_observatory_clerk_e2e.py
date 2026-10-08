# ruff: noqa: E501
"""Observatory connected-Clerk E2E: additive launcher + REAL Chrome + REAL Clerk TEST sign-in for users A and B.
  python -m scripts.run_observatory_clerk_e2e --env-file <env outside Git> --users-file <json outside Git> --out <evidence dir>
Reuses the accepted CLERK-LIVE-001 harness (Stack/Browser/secret scan); only the launcher module and the browser driver differ.
Evidence contains booleans, statuses, counts and digests only: no token, cookie, secret or password."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from scripts import run_capstone_clerk_connected_e2e as base
from scripts.run_capstone_clerk_connected import parse_env_file

ROOT = base.ROOT
DRIVER = ROOT / "scripts/observatory_clerk_e2e_driver.mjs"


class ObservatoryStack(base.Stack):
    """Same supervised subprocess, additive Observatory launcher module."""

    def start(self, timeout: float = 600.0) -> float:
        import os
        import subprocess
        import sys
        import time

        cmd = [sys.executable, "-m", "scripts.run_observatory_clerk_connected", "--workspace",
               str(self.workspace), "--mode", self.mode, "--build"]
        env = {**os.environ, **self.env, "PYTHONPATH": "src:."}
        t0 = time.monotonic()
        self.process = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=self.log.open("ab"),
                                        stderr=subprocess.STDOUT)
        while time.monotonic() < t0 + timeout:
            if self.process.poll() is not None:
                raise RuntimeError("OBSERVATORY_LAUNCHER_EXITED:" + self.log.read_text()[-400:])
            if "OBSERVATORY_CLERK_TEST_READY" in self.log.read_text(errors="ignore"):
                return round(time.monotonic() - t0, 1)
            time.sleep(1)
        raise RuntimeError("OBSERVATORY_LAUNCHER_READY_TIMEOUT")


def run_driver(mode: str, who: str, users: Path, raw: Path, name: str, known: dict[str, Any] | None = None) -> dict[str, Any]:
    import subprocess

    profile = Path(tempfile.mkdtemp(prefix=f"obs-clerk-{name}-"))   # fresh Chrome profile per journey
    port = base.free_port()
    browser = base.Browser(profile, port)
    out = raw / f"{name}.json"
    try:
        r = subprocess.run(["node", str(DRIVER), mode, str(port), base.ORIGIN, str(users), who, str(out),
                            str(raw / f"shots_{name}"), json.dumps(known or {})],
                           cwd=ROOT, capture_output=True, text=True, timeout=2400)
    finally:
        browser.close()
        shutil.rmtree(profile, ignore_errors=True)
    if r.returncode != 0 or not out.exists():
        raise RuntimeError(f"DRIVER_FAILED:{name}:{(r.stdout + r.stderr)[-600:]}")
    return json.loads(out.read_text())


def main() -> int:
    ap = argparse.ArgumentParser()
    for flag in ("--env-file", "--users-file", "--out"):
        ap.add_argument(flag, required=True)
    args = ap.parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    env = parse_env_file(Path(args.env_file))
    secret = env["CLERK_SECRET_KEY"]
    work = Path(tempfile.mkdtemp(prefix="obs-clerk-e2e-"))
    stack = ObservatoryStack(env, work / "workspace", work / "launcher.out")
    startup = stack.start()
    try:
        a = run_driver("a-journey", "A", Path(args.users_file), out_dir, "a_journey")
        b = None
        for attempt in range(3):   # a Clerk sign-in timeout is an external flake: retry B with a fresh profile, record attempts
            try:
                b = run_driver("b-isolation", "B", Path(args.users_file), out_dir, "b_isolation", a["known"])
                break
            except RuntimeError as error:
                detail = str(error)
                (out_dir / f"b_attempt_{attempt + 1}_failure.txt").write_text(
                    re.sub(r"[\w.+-]+@[\w-]+\.\w+", "<email>", detail)[-600:])
                if "Password is incorrect" in detail:   # never burn lockout attempts on a rejected credential
                    break
                time.sleep(30)
        if b is None:
            raise RuntimeError("B_ISOLATION_FAILED_AFTER_3_ATTEMPTS")
    finally:
        shutdown = stack.stop()
    text = json.dumps({"startup_s": startup, "a": a, "b": b, "shutdown": shutdown}, indent=1, sort_keys=True, default=str)
    assert secret not in text and "sk_test_" not in text and not base.JWT.search(text) and not re.search(r"@[\w-]+\.\w+", text), "SECRET_IN_EVIDENCE"
    (out_dir / "observatory_clerk_e2e.json").write_text(text + "\n")
    print(text[:6000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
