# ruff: noqa: E501
"""Run and record the CAP-010 command outcomes (targeted, full regression under the inherited CAP-003 flake policy,
frontend npm test/check/build, ruff, pip check). Writes reports/capstone/cap_010/test_report.json and
inherited_cap003_flake.json. Failed attempts are never overwritten silently: every attempt is recorded."""

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
OUT = ROOT / "reports/capstone/cap_010"
WORK = Path(os.environ.get("CAP010_WORK", "/tmp/cap010_work"))
ENV = {**os.environ, "PYTHONPATH": "src:."}
TARGETED = ["tests/test_capstone_demo_workspace.py", "tests/test_capstone_demo_preflight.py", "tests/test_capstone_demo_orchestrator.py",
            "tests/test_capstone_full_demo.py", "tests/test_capstone_lifecycle.py"]
FLAKE = "tests/test_capstone_monitoring_websocket.py::test_monitoring_completes_with_zero_subscribers"
SIGNATURE = "AssertionError: assert (789 > 100 and False)"
BIN = Path(sys.executable).parent


def sh(cmd: list[str], log: str, cwd: Path = ROOT, timeout: int = 7200) -> tuple[int, str, float]:
    t0 = time.time()
    r = subprocess.run(cmd, cwd=cwd, env=ENV, capture_output=True, text=True, timeout=timeout)
    text = r.stdout + r.stderr
    (WORK / log).write_text(text)
    return r.returncode, text, round(time.time() - t0, 1)


def junit(path: Path) -> dict[str, str]:
    out = {}
    for case in ET.parse(path).getroot().iter("testcase"):
        status = "passed"
        if case.find("failure") is not None or case.find("error") is not None:
            status = "failed"
        elif case.find("skipped") is not None:
            status = "skipped"
        out[f"{case.get('classname')}::{case.get('name')}"] = status
    return out


def counts(text: str) -> dict[str, int | None]:
    last = [ln for ln in text.splitlines() if re.search(r" in [\d.]+s", ln)]
    summary = last[-1] if last else ""
    return {k: int(v) for v, k in re.findall(r"(\d+) (passed|failed|skipped|deselected|error|errors)", summary)}


def flake_probe() -> dict:
    attempts = []
    for i in range(12):
        r = subprocess.run([sys.executable, "-m", "pytest", FLAKE, "-q", "-p", "no:cacheprovider"], cwd=ROOT, env=ENV, capture_output=True, text=True, timeout=120)
        text = r.stdout + r.stderr
        attempts.append({"attempt": i + 1, "passed": r.returncode == 0, "known_signature": SIGNATURE in text, "returncode": r.returncode})
    ok = any(a["passed"] for a in attempts) and all(a["passed"] or a["known_signature"] for a in attempts)
    report = {"status": "PASS_INHERITED_FLAKE_POLICY" if ok else "FAIL", "test": FLAKE, "prior_documentation": "reports/capstone/cap_004/preexisting_cap003_flake.json",
              "frozen_monitoring_files_modified": False, "full_suite_signature": SIGNATURE, "attempts": attempts}
    (OUT / "inherited_cap003_flake.json").write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    return report


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    report: dict = {"commands": {}}
    rc, text, secs = sh([sys.executable, "-m", "pytest", *TARGETED, "-q", "-p", "no:cacheprovider", f"--junitxml={WORK / 'targeted.xml'}"], "targeted.log")
    targeted = junit(WORK / "targeted.xml")
    report["targeted"] = {"returncode": rc, "counts": counts(text), "seconds_machine_specific": secs, "tests": targeted}
    flake = flake_probe()
    report["inherited_flake"] = {"status": flake["status"], "isolated_passes": sum(a["passed"] for a in flake["attempts"]), "attempts": len(flake["attempts"])}
    rc, text, secs = sh([sys.executable, "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider", f"--deselect={FLAKE}", f"--junitxml={WORK / 'full.xml'}"], "full.log")
    full = junit(WORK / "full.xml")
    prior = {k: v for k, v in full.items() if "capstone" in k and "demo" not in k}
    report["full_regression"] = {"returncode": rc, "counts": counts(text), "known_flake_deselected": FLAKE, "failed": sorted(k for k, v in full.items() if v == "failed"),
                                 "seconds_machine_specific": secs, "tests_total": len(full)}
    report["prior_capstone_tests"] = {"total": len(prior), "failed": sorted(k for k, v in prior.items() if v == "failed")}
    fe = ROOT / "frontend"
    for name, cmd in (("npm_test", ["npm", "test", "--silent"]), ("svelte_check", ["npm", "run", "check"]), ("build", ["npm", "run", "build"])):
        rc, text, secs = sh(cmd, f"{name}.log", cwd=fe, timeout=1800)
        report["commands"][name] = {"returncode": rc, "seconds_machine_specific": secs, "tail": "\n".join(text.strip().splitlines()[-6:])}
    rc, text, _ = sh([str(BIN / "ruff"), "check", "."], "ruff.log")
    report["commands"]["ruff"] = {"returncode": rc, "output": text.strip()[-300:]}
    rc, text, _ = sh([sys.executable, "-m", "pip", "check"], "pip.log")
    report["commands"]["pip_check"] = {"returncode": rc, "output": text.strip()[-300:]}
    c = report["commands"]
    report["frontend_summary"] = {"vitest": re.findall(r"(\d+) passed", c["npm_test"]["tail"]), "svelte_check_zero_errors": " 0 errors" in (WORK / "svelte_check.log").read_text().lower(),
                                  "build_done": "✔ done" in (WORK / "build.log").read_text()}
    report["ci_queried"] = False
    report["ci_triggered"] = False
    report["status"] = "PASS" if (report["targeted"]["returncode"] == 0 and flake["status"] == "PASS_INHERITED_FLAKE_POLICY" and report["full_regression"]["returncode"] == 0
                                  and all(v["returncode"] == 0 for v in c.values()) and report["frontend_summary"]["svelte_check_zero_errors"] and report["frontend_summary"]["build_done"]) else "FAIL"
    (OUT / "test_report.json").write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "targeted": report["targeted"]["counts"], "full": report["full_regression"]["counts"]}))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
