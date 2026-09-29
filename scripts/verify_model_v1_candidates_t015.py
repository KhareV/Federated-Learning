#!/usr/bin/env python3
"""Verify the existing real T015 candidate package without retraining it."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from models.baseline_freeze import verify_baseline_freeze  # noqa: E402
from nhm.hashing import hash_file  # noqa: E402
from preprocessing.freeze import verify_preproc_freeze  # noqa: E402


def main() -> None:
    verify_preproc_freeze(ROOT)
    verify_baseline_freeze(ROOT)
    manifest_path = ROOT / "checkpoints/candidates/MODEL_V1/candidate_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["overall_status"] != "PASS" or manifest["release_candidate_seed"] != 20260927:
        raise RuntimeError("candidate manifest identity/status failure")
    if hash_file(ROOT / "configs/model_v1.yaml") != manifest["config_sha256"]:
        raise RuntimeError("candidate config hash mismatch")
    for candidate in manifest["candidates"]:
        if hash_file(ROOT / candidate["checkpoint_path"]) != candidate["checkpoint_sha256"]:
            raise RuntimeError(f"candidate checkpoint mismatch: {candidate['seed']}")
        if hash_file(ROOT / candidate["metadata_path"]) != candidate["metadata_sha256"]:
            raise RuntimeError(f"candidate metadata mismatch: {candidate['seed']}")
        if hash_file(ROOT / candidate["seed_log_path"]) != candidate["seed_log_sha256"]:
            raise RuntimeError(f"candidate log mismatch: {candidate['seed']}")
    print("T015 candidate package verification: PASS")


if __name__ == "__main__":
    main()
