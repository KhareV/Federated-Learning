#!/usr/bin/env python3
"""V2-014 PRE-CANONICAL method freeze: artifacts/MODEL_V2_COMPLETE_REPRO_PROTOCOL_V1.lock.json and
reports/model_v2/v2_014/method_freeze.json, written BEFORE the first canonical clean clone. The
mutable strict lifecycle test is deliberately NOT bound."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import yaml

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
METHOD_FILES = [
    "configs/model_v2/complete_repro_protocol_v1.yaml",
    "docs/MODEL_V2_COMPLETE_REPRO_PROTOCOL_V1.md",
    "scripts/run_v2_014_clean_repro.py", "scripts/v2_014_clone_checks.py",
    "scripts/v2_014_fl_dev_reconstruct.py", "scripts/run_v2_014_replay.py",
    "scripts/verify_v2_014_evidence.py", "scripts/import_v2_014_evidence.py",
    "tests/conftest.py", "tests/test_v2_014_method.py",
    "reports/model_v2/v2_014/entry_and_control_plane_audit.json",
    # dependency definitions installed in the clean clone
    "requirements-dev.lock", "pyproject.toml", "frontend/package.json",
    "frontend/package-lock.json",
    # repository-native scripts the harness executes
    "scripts/verify_v2_fl_eval_stats.py", "scripts/run_v2_013_replay.py", "scripts/_v2_013_lib.py",
    "scripts/run_v2_fl_005_system_demo.py", "scripts/generate_model_v2_final_test_vector_v2008.py",
    "scripts/select_v2_fedprox_mu.py", "scripts/run_secagg_t028.py",
    "scripts/verify_api_runtime_v2_1.py", "scripts/verify_dashboard_ui_v1_4_v2013.py",
    "scripts/verify_e2e_replay_v1_3_v2013.py",
    # frozen references the checks compare against
    "reports/model_v2/v2_fl_005/federation_run.json", "reports/model_v2/v2_fl_005/events.json",
    "reports/model_v2/v2_fl_005/semantic_replay_digest.json",
    "reports/model_v2/v2_013/replay_semantic_digest.json",
    "reports/model_v2/c_v2_013_quality_flatline/replay/replay_semantic_digest.json",
    "artifacts/deployment/MODEL_V2_GATEWAY_FP32.ts",
]


def main() -> None:
    out = ROOT / "reports/model_v2/v2_014"
    protocol = yaml.safe_load(
        (ROOT / "configs/model_v2/complete_repro_protocol_v1.yaml").read_text())
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                          check=True).stdout.strip()
    bound = {p: hash_file(ROOT / p) for p in METHOD_FILES}
    lock = {
        "lock_id": "MODEL_V2_COMPLETE_REPRO_PROTOCOL_V1", "status": "FROZEN",
        "owner_task": "V2-014", "gate": {"gate_id": "V2G13", **protocol["v2g13"]},
        "entry_sha": protocol["entry_sha"], "bound_artifacts": bound,
        "lifecycle_test_bound": False, "frozen_before_first_canonical_clean_clone": True,
        "scientific_model_fits_added": 0, "real_waveform_datasets_accessed": False,
        "change_control": "A change after the first canonical clone requires a prospective "
        "correction, a new method commit and an entirely NEW clone."}
    (ROOT / "artifacts/MODEL_V2_COMPLETE_REPRO_PROTOCOL_V1.lock.json").write_text(
        json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "method_freeze.json").write_text(json.dumps({
        "owner_task": "V2-014", "gate": "V2G13", "entry_head": head, "method_file_sha256": bound,
        "lock_sha256": hash_file(ROOT / "artifacts/MODEL_V2_COMPLETE_REPRO_PROTOCOL_V1.lock.json"),
        "canonical_clean_clone_exists_at_method_freeze": False, "status": "PASS"},
        indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("MODEL_V2_COMPLETE_REPRO_PROTOCOL_V1 frozen on top of", head)


if __name__ == "__main__":
    main()
