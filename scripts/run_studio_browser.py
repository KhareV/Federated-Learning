# ruff: noqa: E501
"""Run a Studio CDP browser script (scripts/*.mjs) against an already-running stack in real headless Chrome."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from scripts.run_capstone_frontend_e2e import chrome
from scripts.run_capstone_persistent_e2e import free_port

ROOT = Path(__file__).resolve().parents[1]


def main(script: str, origin: str, out: str) -> int:
    port = free_port()
    with tempfile.TemporaryDirectory(prefix="nhm-studio-chrome-") as profile, chrome(port, profile):
        return subprocess.run(["node", str(ROOT / script), str(port), origin, str(ROOT / out)], cwd=ROOT).returncode


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:4]))
