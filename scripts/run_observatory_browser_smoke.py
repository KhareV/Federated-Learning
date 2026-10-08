"""Run the Observatory browser smoke against an already-running local development stack."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from scripts.run_capstone_frontend_e2e import chrome
from scripts.run_capstone_persistent_e2e import free_port

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    out = ROOT / "reports/observatory/workstream_a"
    out.mkdir(parents=True, exist_ok=True)
    port = free_port()
    with (tempfile.TemporaryDirectory(prefix="nhm-observatory-chrome-") as profile,
          chrome(port, profile)):
        subprocess.run(
            ["node", str(ROOT / "scripts/observatory_browser_smoke.mjs"), str(port),
             "http://127.0.0.1:5173", str(out)], cwd=ROOT, check=True,
        )


if __name__ == "__main__":
    main()
