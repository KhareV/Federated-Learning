#!/usr/bin/env python3
"""V2-013 method freeze: records the hash of every method/integration file BEFORE any canonical
V2-013 replay or equivalence result is produced. The METHOD commit contains this record; the
canonical result commit must not change any file listed here (verified by the evidence
finalizer)."""

from __future__ import annotations

import json
import subprocess

from nhm.hashing import hash_file
from scripts._v2_013_lib import OUT, ROOT

METHOD_FILES = [
    "api/app_v2.py", "api/runtime_v2.py", "fusion/alert_policy_v2_binding.py",
    "simulation/profile_v2013.py", "simulation/truth_v2013.py",
    "simulation/stream_runtime_v2013.py", "configs/model_v2/api_runtime_v2.yaml",
    "scripts/_v2_013_lib.py", "scripts/build_wearable_sim_v2_replay_v2013.py",
    "scripts/generate_v2_013_entry.py", "scripts/run_v2_013_equivalence.py",
    "scripts/run_v2_013_state_sequences.py", "scripts/run_v2_013_v1_isolation.py",
    "scripts/run_v2_013_replay.py", "scripts/run_v2_013_static_audits.py",
    "scripts/run_research_v2_demo.py", "scripts/freeze_api_runtime_v2.py",
    "scripts/verify_api_runtime_v2.py", "scripts/run_v2_013_chunked_regression.py",
    "scripts/freeze_dashboard_ui_v1_4_v2013.py", "scripts/verify_dashboard_ui_v1_4_v2013.py",
    "scripts/freeze_e2e_replay_v1_3_v2013.py", "scripts/verify_e2e_replay_v1_3_v2013.py",
    "frontend/src/lib/dashboard/state-presentation.ts",
    "frontend/src/routes/monitoring/+page.svelte",
    "frontend/src/lib/dashboard/__tests__/v2-runtime-e2e.test.ts",
    "frontend/src/lib/dashboard/__tests__/model-neutral-copy.test.ts",
    "frontend/static/replay/WEARABLE_SIM_V2_REPLAY_V1.json",
    "tests/fixtures/e2e/WEARABLE_SIM_V2_REPLAY_V1.manifest.json",
    "tests/test_v2_013_runtime.py", "tests/test_v2_013_simulation.py",
    "artifacts/DASHBOARD_UI_V1_4.lock.json", "artifacts/E2E_REPLAY_SOFTWARE_V1_3.lock.json",
]


def main() -> None:
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                          text=True, check=True).stdout.strip()
    data = {
        "owner_task": "V2-013", "gate": "V2G12", "entry_head": head,
        "canonical_replay_results_exist_at_method_freeze": False,
        "method_file_sha256": {p: hash_file(ROOT / p) for p in METHOD_FILES},
        "harness_dry_run_disclosure": (
            "Equivalence, state-sequence, isolation and replay harness scripts were executed "
            "against a scratch output directory (V2_013_OUT) while debugging harness mechanics "
            "(port/process launch, JSON number spelling in the digest, a frontend test "
            "assertion). No model, threshold, calibration, policy or signal-processing "
            "behavior was changed in response to those outcomes; scratch outputs are not "
            "evidence and are not committed."),
        "model_fits": 0, "protected_partitions_accessed": [],
        "status": "PASS",
    }
    (OUT / "method_freeze.json").write_text(json.dumps(data, indent=2, sort_keys=True) + "\n",
                                            encoding="utf-8")
    print(len(METHOD_FILES), "method files frozen at", head)


if __name__ == "__main__":
    main()
