"""Run the FL10 real-browser smoke against an already-running isolated DEMO stack."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from scripts.run_capstone_frontend_e2e import chrome
from scripts.run_capstone_persistent_e2e import free_port

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    out = ROOT / "reports/fl10/browser"
    out.mkdir(parents=True, exist_ok=True)
    port = free_port()
    with tempfile.TemporaryDirectory(prefix="nhm-fl10-chrome-") as profile, chrome(port, profile):
        subprocess.run(
            ["node", str(ROOT / "scripts/fl10_browser_smoke.mjs"), str(port),
             os.environ.get("NHM_FL10_FRONTEND_URL", "http://127.0.0.1:5185"), str(out)],
            cwd=ROOT, check=True,
        )


if __name__ == "__main__":
    main()
