#!/usr/bin/env python3
"""Generate T020 run provenance and non-circular artifact hashes."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from evaluation.external_incart import verify_external_freeze  # noqa: E402
from nhm.hashing import hash_file  # noqa: E402
from nhm.run_manifest import artifact_record, create_run_manifest, write_run_manifest  # noqa: E402


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    verification = verify_external_freeze(ROOT)
    inputs = [
        ROOT / "checkpoints/MODEL_V1.pt",
        ROOT / "artifacts/CAL_V1.json",
        ROOT / "manifests/preprocessing/PREPROC_V1.lock.json",
        ROOT / "manifests/labels/AAMI_SVF_MAP_V1.yaml",
        ROOT / "manifests/datasets/incart_v1.yaml",
        ROOT / "manifests/datasets/incart_v1_files.csv",
        ROOT / "manifests/datasets/incart_lead_ii_records.csv",
        ROOT / "manifests/datasets/incart_patient_map.csv",
        ROOT / "reports/internal_test.json",
        ROOT / "artifacts/internal_test_access_v1.json",
    ]
    outputs = [
        ROOT / "evaluation/external_incart.py",
        ROOT / "configs/external_incart_v1.yaml",
        ROOT / "manifests/windows/INCART_EXTERNAL_WINDOWS_V1.csv",
        ROOT / "reports/external_incart.json",
        ROOT / "reports/external_incart_metrics.csv",
        ROOT / "reports/external_incart_predictions.csv",
        ROOT / "artifacts/external_incart_access_v1.json",
        ROOT / "reports/t020/pre_access_audit.json",
        ROOT / "reports/t020/one_shot_access_audit.json",
        ROOT / "reports/t020/incart_window_audit.json",
        ROOT / "reports/t020/patient_group_audit.json",
        ROOT / "reports/t020/lead_policy_audit.json",
        ROOT / "reports/t020/bootstrap_draws.npz",
        ROOT / "reports/t020/bootstrap_replicates.csv",
        ROOT / "reports/t020/bootstrap_summary.json",
        ROOT / "reports/t020/reproducibility.json",
    ]
    manifest = create_run_manifest(
        ROOT,
        run_id="T020-EXTERNAL-INCART-V1",
        phase_id="T020",
        task_id="T020",
        config_path=ROOT / "configs/external_incart_v1.yaml",
        dependency_snapshot_path=ROOT / "requirements-dev.lock",
        input_artifacts=[artifact_record(path, ROOT) for path in inputs],
        output_artifacts=[artifact_record(path, ROOT) for path in outputs],
        seed=20260927,
        notes=(
            "One locked MODEL_V1 inference pass over official INCART v1.0.0 exact Lead II; "
            "all metrics and 2,000 patient-cluster bootstrap replicates derive from the "
            "immutable prediction table. No adaptation, retuning, CI, or other dataset access."
        ),
    )
    run_path = ROOT / "reports/t020/run_manifest.json"
    write_run_manifest(manifest, run_path, ROOT / "contracts/run_manifest_v1.schema.json")
    hashed = [
        *outputs,
        run_path,
        ROOT / "scripts/verify_external_incart_reproducibility_t020.py",
        ROOT / "scripts/generate_t020_evidence.py",
    ]
    evidence = {
        "manifest_version": "1.0",
        "algorithm": "sha256",
        "rule": "exact file bytes; this manifest excludes itself to avoid circular digest",
        "artifacts": {
            str(path.relative_to(ROOT)): hash_file(path) for path in sorted(set(hashed))
        },
        "upstream_frozen_hashes": {
            str(path.relative_to(ROOT)): hash_file(path) for path in inputs
        },
        "verification": verification,
        "T020_status": "PASS",
        "G10_status": "PASS",
        "F11_status": "FROZEN",
        "MODEL_V1_external_inference_passes": 1,
        "CI_executed": False,
    }
    write_json(ROOT / "reports/t020/artifact_hashes.json", evidence)
    print("T020 evidence: PASS")


if __name__ == "__main__":
    main()
