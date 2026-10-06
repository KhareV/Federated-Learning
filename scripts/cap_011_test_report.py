# ruff: noqa: E501
"""Record the development-checkout verification (preparation only; canonical evidence comes from the fresh clones):
targeted CAP-011 tests, full regression under the inherited CAP-003 flake policy, ruff and pip check.
Writes reports/capstone/cap_011/dev_test_report.json. It defines no pass criteria (the frozen evaluator does)."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get("CAP011_OUT", ROOT / "reports/capstone/cap_011"))
WORK = Path(os.environ.get("CAP011_WORK", "/tmp/cap011_work"))
ENV = {**os.environ, "PYTHONPATH": "src:."}
TARGETED = ["tests/test_capstone_release_lib.py", "tests/test_capstone_release_harness.py", "tests/test_capstone_release_guide.py", "tests/test_capstone_release_target.py",
            "tests/test_capstone_lifecycle.py", "tests/test_capstone_demo_preflight.py"]
FLAKE = "tests/test_capstone_monitoring_websocket.py::test_monitoring_completes_with_zero_subscribers"
SIGNATURE = "AssertionError: assert (789 > 100 and False)"
BIN = Path(sys.executable).parent


def sh(cmd: list[str], log: str) -> tuple[int, str, float]:
    t0 = time.time()
    r = subprocess.run(cmd, cwd=ROOT, env=ENV, capture_output=True, text=True, timeout=7200)
    (WORK / log).write_text(r.stdout + r.stderr)
    return r.returncode, r.stdout + r.stderr, round(time.time() - t0, 1)


def junit(path: Path) -> dict[str, str]:
    out = {}
    for case in ET.parse(path).getroot().iter("testcase"):
        out[f"{case.get('classname')}::{case.get('name')}"] = "failed" if (case.find("failure") is not None or case.find("error") is not None) else ("skipped" if case.find("skipped") is not None else "passed")
    return out


def counts(text: str) -> dict[str, int]:
    last = [ln for ln in text.splitlines() if re.search(r" in [\d.]+s", ln)]
    return {k: int(v) for v, k in re.findall(r"(\d+) (passed|failed|skipped|deselected|errors?)", last[-1] if last else "")}


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    report: dict = {"commands": {}}
    rc, text, secs = sh([sys.executable, "-m", "pytest", *TARGETED, "-q", "-p", "no:cacheprovider", f"--junitxml={WORK / 'targeted.xml'}"], "targeted.log")
    report["targeted"] = {"returncode": rc, "counts": counts(text), "seconds_machine_specific": secs}
    attempts = []
    for i in range(12):
        r = subprocess.run([sys.executable, "-m", "pytest", FLAKE, "-q", "-p", "no:cacheprovider"], cwd=ROOT, env=ENV, capture_output=True, text=True, timeout=180)
        attempts.append({"attempt": i + 1, "passed": r.returncode == 0, "known_signature": SIGNATURE in r.stdout + r.stderr})
    ok = any(a["passed"] for a in attempts) and all(a["passed"] or a["known_signature"] for a in attempts)
    report["inherited_flake"] = {"status": "PASS_INHERITED_FLAKE_POLICY" if ok else "FAIL", "test": FLAKE, "attempts": attempts}
    rc, text, secs = sh([sys.executable, "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider", f"--deselect={FLAKE}", f"--junitxml={WORK / 'full.xml'}"], "full.log")
    full = junit(WORK / "full.xml")
    report["full_regression"] = {"returncode": rc, "counts": counts(text), "known_flake_deselected": FLAKE, "failed": sorted(k for k, v in full.items() if v == "failed"), "seconds_machine_specific": secs, "tests_total": len(full)}
    rc, text, _ = sh([str(BIN / "ruff"), "check", "."], "ruff.log")
    report["commands"]["ruff"] = {"returncode": rc, "output": text.strip()[-200:]}
    rc, text, _ = sh([sys.executable, "-m", "pip", "check"], "pip.log")
    report["commands"]["pip_check"] = {"returncode": rc, "output": text.strip()[-200:]}
    report["ci_queried"] = False
    report["ci_triggered"] = False
    (OUT / "dev_test_report.json").write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"targeted": report["targeted"]["counts"], "full": report["full_regression"]["counts"], "flake": report["inherited_flake"]["status"]}))
    return 0 if rc == 0 and report["full_regression"]["returncode"] == 0 and report["targeted"]["returncode"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
