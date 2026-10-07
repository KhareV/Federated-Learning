"""Run UI-ENH-002 browser smoke on the real offline faculty-demo stack."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from scripts.run_capstone_frontend_e2e import chrome
from scripts.run_capstone_full_demo_e2e import Launcher
from scripts.run_capstone_persistent_e2e import free_port

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/ui_enh_002"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    screenshots = OUT / "screenshots"
    screenshots.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ui-enh-002-") as temporary:
        workspace = Path(temporary) / "workspace"
        ports = (free_port(), free_port(), free_port())
        launcher = Launcher(workspace, ports, build=True, prewarm=False)
        launcher.start()
        try:
            debug_port = free_port()
            with chrome(debug_port, str(Path(temporary) / "chrome-profile")):
                completed = subprocess.run(
                    ["node", str(ROOT / "scripts/ui_enh_002_browser.mjs"),
                     str(debug_port), launcher.origin,
                     str(OUT / "browser_smoke.json"), str(screenshots)],
                    cwd=ROOT, capture_output=True, text=True, timeout=350,
                )
            (OUT / "browser_driver.log").write_text(
                completed.stdout + completed.stderr, encoding="utf-8"
            )
            if completed.returncode:
                raise RuntimeError(f"UI_ENH_002_BROWSER_DRIVER_FAILED:{completed.returncode}")
            print(completed.stdout.strip())
        finally:
            launcher.stop()


if __name__ == "__main__":
    main()
