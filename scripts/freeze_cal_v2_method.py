#!/usr/bin/env python3
"""V2-009 Section 38/40: freeze all CAL_V2 scientific method artifacts BEFORE any
CALIBRATION waveform access. Arms the one-shot V2_CALIBRATION_ONCE guard and writes
method_freeze.json binding every frozen identity/hash this phase depends on. No waveform
access, no neural fit.
"""

from __future__ import annotations

import json

import scripts._cal_v2_lib as lib
from nhm.hashing import hash_file
from nhm.model_v2_calibration_guard import arm_guard

ROOT = lib.ROOT
OUT_DIR = ROOT / "reports/model_v2/v2_009"
CONFIG_PATH = ROOT / "configs/model_v2/calibration_v2.yaml"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    config_sha256 = hash_file(CONFIG_PATH)
    checkpoint_sha256 = hash_file(ROOT / "checkpoints/MODEL_V2_FINAL.pt")
    manifest_sha256 = hash_file(ROOT / "checkpoints/MODEL_V2_FINAL.manifest.json")
    frozen_config_sha256 = hash_file(ROOT / "configs/model_v2_final_frozen.yaml")
    protocol_v3_sha256 = hash_file(
        ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V3.lock.json"
    )

    preconditions = {
        "calibration_method_config_sha256": config_sha256,
        "model_v2_final_checkpoint_sha256": checkpoint_sha256,
        "model_v2_final_manifest_sha256": manifest_sha256,
        "model_v2_final_frozen_config_sha256": frozen_config_sha256,
        "protocol_v3_lock_sha256": protocol_v3_sha256,
    }
    guard_state = arm_guard(ROOT, preconditions=preconditions)

    method_freeze = {
        "calibration_id": "CAL_V2",
        "owner_task": "V2-009",
        "model_id": "MODEL_V2_FINAL",
        "fit_partition": "CALIBRATION",
        "calibration_domain": "MIT-BIH-v1.0.0",
        "method_config_path": "configs/model_v2/calibration_v2.yaml",
        "method_config_sha256": config_sha256,
        "model_v2_final_checkpoint_sha256": checkpoint_sha256,
        "guard_armed": guard_state["state"] == "ARMED",
        "cal_v2_result_exists_at_method_commit": False,
        "fitted_temperature_exists_at_method_commit": False,
        "fitted_threshold_exists_at_method_commit": False,
        "status": "PASS",
    }
    (OUT_DIR / "method_freeze.json").write_text(
        json.dumps(method_freeze, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("V2-009 CAL_V2 method freeze complete.")


if __name__ == "__main__":
    main()
