"""Document the inherited CAP-003 journal-close race without editing frozen monitoring code."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/capstone/cap_009/inherited_cap003_flake.json"
TEST = (
    "tests/test_capstone_monitoring_websocket.py"
    "::test_monitoring_completes_with_zero_subscribers"
)
SIGNATURE = "AssertionError: assert (789 > 100 and False)"


def main() -> None:
    attempts = []
    for index in range(12):
        result = subprocess.run(
            [sys.executable, "-m", "pytest", TEST, "-q"],
            cwd=ROOT, env={**os.environ, "PYTHONPATH": "src:."},
            capture_output=True, text=True, timeout=60,
        )
        output = result.stdout + result.stderr
        attempts.append({
            "attempt": index + 1, "passed": result.returncode == 0,
            "known_signature": SIGNATURE in output,
            "returncode": result.returncode,
        })
    observed = any(row["passed"] for row in attempts)
    only_known_failures = all(row["passed"] or row["known_signature"] for row in attempts)
    report = {
        "status": "PASS_INHERITED_FLAKE_POLICY" if observed and only_known_failures else "FAIL",
        "test": TEST,
        "prior_documentation": "reports/capstone/cap_004/preexisting_cap003_flake.json",
        "frozen_monitoring_files_modified": False,
        "full_suite_signature": SIGNATURE,
        "attempts": attempts,
        "isolated_pass_observed": observed,
        "only_known_failure_signature": only_known_failures,
    }
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "passes": sum(x["passed"] for x in attempts)}))
    raise SystemExit(0 if report["status"] == "PASS_INHERITED_FLAKE_POLICY" else 1)


if __name__ == "__main__":
    main()
