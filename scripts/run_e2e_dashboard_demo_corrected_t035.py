#!/usr/bin/env python3
"""T035-REPRO corrected one-command software demo supervisor.

Identical orchestration to scripts/run_e2e_dashboard_demo_c034.py (reused directly, not
duplicated) except the upstream-lock verification checks the latest successors
(API_RUNTIME_V1_1, DASHBOARD_UI_V1_3). scripts/run_e2e_dashboard_demo_c034.py and
scripts/run_e2e_dashboard_demo_corrected_c032.py are both left byte-identical.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import scripts.run_e2e_dashboard_demo_c034 as _demo_c034
from scripts.verify_api_runtime_v1_1_c032 import verify as verify_api_runtime_v1_1
from scripts.verify_dashboard_ui_v1_3_t035 import verify as verify_dashboard_ui_v1_3


def _verify_locks() -> dict[str, str]:
    return {
        "api_runtime_v1_1": verify_api_runtime_v1_1()["status"],
        "dashboard_ui_v1_3": verify_dashboard_ui_v1_3()["status"],
    }


def run(*, speed: int, backend_timeout: float, frontend_timeout: float) -> dict[str, object]:
    original_verify_locks = _demo_c034._verify_locks
    _demo_c034._verify_locks = _verify_locks
    try:
        result = _demo_c034.run(
            speed=speed, backend_timeout=backend_timeout, frontend_timeout=frontend_timeout
        )
    finally:
        _demo_c034._verify_locks = original_verify_locks
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--speed", type=int, default=0, choices=[0, 1])
    parser.add_argument("--backend-timeout", type=float, default=30.0)
    parser.add_argument("--frontend-timeout", type=float, default=60.0)
    parser.add_argument("--audit-out", default=None)
    args = parser.parse_args()

    result = run(
        speed=args.speed,
        backend_timeout=args.backend_timeout,
        frontend_timeout=args.frontend_timeout,
    )
    if args.audit_out:
        Path(args.audit_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.audit_out).write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
