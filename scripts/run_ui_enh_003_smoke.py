"""Launch real offline DEMO stack and run UI-ENH-003 Chrome sweep."""

from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

from scripts.run_capstone_frontend_e2e import chrome
from scripts.run_capstone_full_demo_e2e import Launcher
from scripts.run_capstone_persistent_e2e import free_port

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("baseline", "final"), required=True)
    args = parser.parse_args()
    out = ROOT / "reports/ui_enh_003" / args.stage
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ui-enh-003-") as temporary:
        ports = (free_port(), free_port(), free_port())
        launcher = Launcher(Path(temporary) / "workspace", ports, build=True, prewarm=False)
        launcher.start()
        try:
            debug_port = free_port()
            with chrome(debug_port, str(Path(temporary) / "chrome-profile")):
                completed = subprocess.run(
                    ["node", str(ROOT / "scripts/ui_enh_003_browser.mjs"), str(debug_port),
                     launcher.origin, str(out), args.stage],
                    cwd=ROOT, capture_output=True, text=True, timeout=500,
                )
            (out / "browser_driver.log").write_text(
                completed.stdout + completed.stderr, encoding="utf-8"
            )
            if completed.returncode:
                raise RuntimeError(f"UI_ENH_003_BROWSER_DRIVER_FAILED:{completed.returncode}")
            print(completed.stdout.strip())
        finally:
            launcher.stop()


if __name__ == "__main__":
    main()
