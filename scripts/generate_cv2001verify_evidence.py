#!/usr/bin/env python3
"""Generate the final C-V2-001-VERIFY run_manifest.json and artifact_hashes.json. The run
manifest validates against the additive MODEL_V2_RUN_MANIFEST_V1 schema with task_id V2-001
(this is a corrective checkpoint on V2-001, not a new canonical V2-015) and an explicit
corrective_checkpoint field."""

from __future__ import annotations

import json
from pathlib import Path

from nhm.hashing import hash_file
from nhm.model_v2_run_manifest import (
    artifact_record,
    create_model_v2_run_manifest,
    write_model_v2_run_manifest,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/cv2_001_verify"
SCHEMA = ROOT / "contracts/model_v2_run_manifest_v1.schema.json"


def main() -> None:
    manifest = create_model_v2_run_manifest(
        ROOT,
        run_id="c-v2-001-verify",
        phase_id="V2-001",
        task_id="V2-001",
        config_path=ROOT / "configs/model_v2/research_protocol_v1.yaml",
        dependency_snapshot_path=None,
        input_artifacts=[
            artifact_record(ROOT / "checkpoints/MODEL_V1.pt", ROOT),
            artifact_record(ROOT / "artifacts/CAL_V1.json", ROOT),
            artifact_record(
                ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V1.lock.json", ROOT
            ),
            artifact_record(ROOT / "manifests/model_v2/cv/MITDB_TRAIN_CV_V2_V1.csv", ROOT),
            artifact_record(ROOT / "manifests/model_v2/cv/MITDB_TRAIN_INNER_V2_V1.csv", ROOT),
        ],
        output_artifacts=[
            artifact_record(
                ROOT / "contracts/model_v2_run_manifest_v1.schema.json", ROOT
            ),
            artifact_record(
                ROOT / "reports/model_v2/cv2_001_verify/full_regression_proof.json", ROOT
            ),
            artifact_record(
                ROOT / "reports/model_v2/cv2_001_verify/pytest_chunks.json", ROOT
            ),
        ],
        seed=None,
        notes=(
            "C-V2-001-VERIFY: full-regression proof + V2 provenance hardening on top of the "
            "already-PASS V2-001. No MODEL_V2_RESEARCH_PROTOCOL_V1 change, no CV manifest "
            "regeneration, no MODEL_V1/MODEL_V2 training, no new waveform access."
        ),
        corrective_checkpoint="C-V2-001-VERIFY",
    )
    write_model_v2_run_manifest(manifest, OUT / "run_manifest.json", SCHEMA)

    artifacts = sorted(p.name for p in OUT.glob("*.json") if p.name != "artifact_hashes.json")
    hashes = {
        f"reports/model_v2/cv2_001_verify/{name}": hash_file(OUT / name) for name in artifacts
    }
    hashes["reports/model_v2/cv2_001_verify/pytest_collection.txt"] = hash_file(
        OUT / "pytest_collection.txt"
    )
    hashes["contracts/model_v2_run_manifest_v1.schema.json"] = hash_file(SCHEMA)
    hashes["src/nhm/model_v2_run_manifest.py"] = hash_file(
        ROOT / "src/nhm/model_v2_run_manifest.py"
    )
    hashes["reports/model_v2/v2_001/source_conflict_audit.json"] = hash_file(
        ROOT / "reports/model_v2/v2_001/source_conflict_audit.json"
    )
    hashes["reports/model_v2/v2_001/run_manifest.json"] = hash_file(
        ROOT / "reports/model_v2/v2_001/run_manifest.json"
    )
    hashes["reports/model_v2/v2_001/artifact_hashes.json"] = hash_file(
        ROOT / "reports/model_v2/v2_001/artifact_hashes.json"
    )
    (OUT / "artifact_hashes.json").write_text(
        json.dumps(
            {"manifest_version": "1.0", "algorithm": "sha256", "artifacts": hashes},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print("C-V2-001-VERIFY evidence generated")


if __name__ == "__main__":
    main()
