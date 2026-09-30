#!/usr/bin/env python3
"""Freeze BIDMC_CONTEXT_V2 and record deterministic C021-HR-B evidence."""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from evaluation.bidmc_context_v2 import (  # noqa: E402
    context_lock_payload,
    sha256,
    verify_context_lock,
    verify_rows,
)

REPORT_DIR = ROOT / "reports/c021_hr_b"


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def semantic_sha(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def git_sha() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def commit_for_subject(subject: str) -> str:
    return subprocess.check_output(
        ["git", "log", "--format=%H", "--grep", f"^{subject}$", "-1"],
        cwd=ROOT,
        text=True,
    ).strip()


def main() -> None:
    protocol_commit = commit_for_subject(
        "ctx(C021-HR-B): freeze BIDMC V2 evaluation protocol"
    )
    result_commit = commit_for_subject(
        "ctx(C021-HR-B): record frozen BIDMC V2 engineering evaluation"
    )
    if not protocol_commit or not result_commit:
        raise RuntimeError("C021_HR_B_COMMIT_CHRONOLOGY_MISSING")
    first = verify_rows(ROOT)
    second = verify_rows(ROOT)
    if first != second:
        raise RuntimeError("BIDMC_CONTEXT_V2_REPRODUCIBILITY_FAILURE")
    write_json(
        REPORT_DIR / "reproducibility.json",
        {
            "frozen_row_sha256": sha256(REPORT_DIR / "bidmc_context_rows_v2.csv"),
            "metric_recomputation_1_sha256": semantic_sha(first),
            "metric_recomputation_2_sha256": semantic_sha(second),
            "identical": True,
            "raw_detector_rerun_required": False,
            "status": "PASS",
        },
    )
    lock_path = ROOT / "artifacts/BIDMC_CONTEXT_V2.lock.json"
    write_json(lock_path, context_lock_payload(ROOT))
    verification = verify_context_lock(ROOT)

    protected_paths = [
        "configs/preproc_v1.yaml",
        "manifests/preprocessing/PREPROC_V1.lock.json",
        "checkpoints/MODEL_V1.pt",
        "artifacts/CAL_V1.json",
        "reports/internal_test.json",
        "reports/noise_robustness.json",
        "reports/external_incart.json",
        "configs/bidmc_context_v1.yaml",
        "reports/bidmc_multimodal_engineering.json",
        "reports/t021/artifact_hashes.json",
        "configs/ecg_hr_context_v2.yaml",
        "preprocessing/ecg_hr_context.py",
        "artifacts/ECG_HR_CONTEXT_V2.lock.json",
        "reports/c021_hr_a/artifact_hashes.json",
        "configs/alert_policy_v1.yaml",
        "fusion/state_machine.py",
        "fusion/episode_manager.py",
        "artifacts/ALERT_POLICY_V1.lock.json",
        "reports/t022/artifact_hashes.json",
    ]
    write_json(
        REPORT_DIR / "run_manifest.json",
        {
            "checkpoint": "C021-HR-B",
            "evaluation_id": "BIDMC_CONTEXT_V2",
            "git_sha_at_evidence_generation": git_sha(),
            "pre_result_protocol_commit": protocol_commit,
            "v2_result_commit": result_commit,
            "python": platform.python_version(),
            "records": 53,
            "raw_BIDMC_access": "one frozen V2 engineering evaluation",
            "MODEL_V1_inference": False,
            "controlled_perturbations": False,
            "ci_executed": False,
            "protected_upstream_hashes": {
                path: sha256(ROOT / path) for path in protected_paths
            },
            "verification": verification,
            "status": "PASS",
        },
    )
    write_json(
        REPORT_DIR / "change_control.json",
        {
            "checkpoint": "C021-HR-B",
            "canonical_task_added": False,
            "canonical_freeze_row_added": False,
            "reason": "independent frozen BIDMC evaluation after ECG-HR V2 and alert policy locks",
            "changed_component": "BIDMC context authority: ECG-HR V2 only",
            "predecessor_preserved": True,
            "upstream_scientific_evidence_invalidated": False,
            "T022_policy_changed": False,
            "T023_started": False,
            "G9_closed": False,
            "downstream_authority": "BIDMC_CONTEXT_V2",
            "status": "PASS",
        },
    )
    artifact_paths = [
        "configs/bidmc_context_v2.yaml",
        "evaluation/bidmc_context_v2.py",
        "artifacts/BIDMC_CONTEXT_V2.lock.json",
        "artifacts/BIDMC_CONTEXT_V2.supersedes.json",
        "reports/bidmc_multimodal_engineering_v2.json",
        "reports/bidmc_multimodal_engineering_v2.csv",
        "reports/c021_hr_b/protocol.json",
        "reports/c021_hr_b/bidmc_context_rows_v2.csv",
        "reports/c021_hr_b/bidmc_by_record_v2.csv",
        "reports/c021_hr_b/v1_v2_comparison.json",
        "reports/c021_hr_b/rate_consistency_audit.json",
        "reports/c021_hr_b/reproducibility.json",
        "reports/c021_hr_b/run_manifest.json",
        "reports/c021_hr_b/change_control.json",
    ]
    write_json(
        REPORT_DIR / "artifact_hashes.json",
        {
            "algorithm": "sha256",
            "artifacts": {path: sha256(ROOT / path) for path in artifact_paths},
            "status": "PASS",
        },
    )
    print("C021-HR-B evidence: PASS")


if __name__ == "__main__":
    main()
