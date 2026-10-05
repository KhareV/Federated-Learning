#!/usr/bin/env python3
# ruff: noqa: E501
"""V2-REL-001 fresh-clone RELEASE SMOKE of the cutover commit. Reuses the V2-014 clean-clone harness
(brand-new git clone, fresh Python 3.11 venv from requirements-dev.lock, fresh `npm ci`, isolated HOME,
no copied source/data, no rescue install, evidence written OUTSIDE the clone) with a release scope:
release locks + decision re-evaluation, default app + V2 replay through the default launcher, V1
rollback replay, process isolation, MODEL_V2/gateway/FL_INIT/V2-FL-005 smoke, frontend, full regression
(CLEAN_CLONE_GATING_V1 reported separately), ruff, pip check and zero tracked drift.

  python3 scripts/run_v2_rel_001_clean_release_smoke.py --target-sha <sha> --evidence-dir <ext> \
      --base-dir <scratch base> --label release_smoke
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

from scripts.run_v2_014_clean_repro import Harness

ENTRY = "f3d3d9f642fbd20158743c24c60d96b945c35d0c"


class ReleaseHarness(Harness):
    def write(self, name: str, data) -> None:
        if name == "reproducibility_manifest.json":
            data = {**data, "phase_id": "V2-REL-001", "gate": "V2RELG0", "entry_sha": ENTRY,
                    "scope": "fresh-clone release smoke of the cutover commit"}
        super().write(name, data)

    def rel(self, check: str, name: str) -> bool:
        out = self.evidence / f"{name}.json"
        result = self.py(f"release:{name}", "-m", "scripts.run_v2_rel_001_release_checks", check,
                         "--out", str(out))
        return result.returncode == 0 and out.exists()

    def module_json(self, module: str, name: str, *extra: str) -> bool:
        out = self.evidence / f"{name}.json"
        result = self.py(f"verify:{name}", "-m", module, *extra)
        out.write_text(result.stdout if result.stdout.strip().startswith("{") else
                       '{"status": "FAIL", "stdout": ' + repr(result.stdout[-300:]).replace("'", '"')
                       + "}", encoding="utf-8")
        return result.returncode == 0

    def scope_release(self) -> None:
        self.frontend()
        self.write("provenance_pre_checks.json", self.provenance("after_install_before_checks"))
        self.module_json("scripts.verify_default_runtime_binding_v2", "release_binding_verification")
        self.module_json("scripts.verify_dashboard_ui_v1_5_v2rel001",
                         "dashboard_ui_v1_5_verification")
        self.module_json("scripts.verify_e2e_replay_v1_4_v2rel001",
                         "e2e_replay_v1_4_verification")
        decision = self.evidence / "decision_reevaluation"
        self.py("release decision re-evaluation (frozen evidence only)", "-m",
                "scripts.evaluate_system_v2_release", "--out-dir", str(decision))
        self.rel("default-replay", "default_replay")
        self.rel("rollback-replay", "rollback_replay")
        self.rel("isolation", "isolation")
        for check in ("model-v2", "fixed-vectors", "gateway", "fl-init"):
            self.check(check, name=f"smoke_{check.replace('-', '_')}")
        self.check("synthetic-fl", "--dir", str(self.raw / "synthetic_fl"),
                   name="smoke_synthetic_fl")
        self.check("lifecycle")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target-sha", required=True)
    parser.add_argument("--evidence-dir", required=True)
    parser.add_argument("--base-dir", required=True)
    parser.add_argument("--label", default="release_smoke")
    parser.add_argument("--remote")
    parser.add_argument("--python", default="python3.11")
    args = parser.parse_args()
    args.mode = "final"
    if not args.remote:
        args.remote = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True,
                                     text=True, check=True).stdout.strip()
    for var in ("PYTHONPATH", "NODE_PATH", "VIRTUAL_ENV"):
        os.environ.pop(var, None)
    harness = ReleaseHarness(args)
    harness.clone_and_audit()
    if harness.failed:
        sys.exit(harness.write_manifests() or 1)
    harness.environment()
    if harness.failed:
        sys.exit(harness.write_manifests() or 1)
    harness.scope_release()
    sys.exit(harness.finish())


if __name__ == "__main__":
    main()
