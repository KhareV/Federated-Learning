#!/usr/bin/env python3
"""Generate the final V2-001 run_manifest.json and artifact_hashes.json from the already
-generated evidence files under reports/model_v2/v2_001/. Machine-generated, not hand-typed."""

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
OUT = ROOT / "reports/model_v2/v2_001"
SCHEMA = ROOT / "contracts/model_v2_run_manifest_v1.schema.json"


def main() -> None:
    # Validated against the additive contracts/model_v2_run_manifest_v1.schema.json
    # (MODEL_V2_RUN_MANIFEST_V1); the canonical contracts/run_manifest_v1.schema.json
    # (^T[0-9]{3}$ only) is never touched and is not used here.
    manifest = create_model_v2_run_manifest(
        ROOT,
        run_id="v2-001-lineage-bootstrap",
        phase_id="V2-001",
        task_id="V2-001",
        config_path=ROOT / "configs/model_v2/research_protocol_v1.yaml",
        dependency_snapshot_path=None,
        input_artifacts=[
            artifact_record(ROOT / "checkpoints/MODEL_V1.pt", ROOT),
            artifact_record(ROOT / "artifacts/CAL_V1.json", ROOT),
            artifact_record(ROOT / "manifests/windows/MITDB_WINDOWS_V1.csv", ROOT),
            artifact_record(ROOT / "manifests/splits/MITDB_SPLIT_V1.csv", ROOT),
        ],
        output_artifacts=[
            artifact_record(
                ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V1.lock.json", ROOT
            ),
            artifact_record(ROOT / "manifests/model_v2/cv/MITDB_TRAIN_CV_V2_V1.csv", ROOT),
            artifact_record(ROOT / "manifests/model_v2/cv/MITDB_TRAIN_INNER_V2_V1.csv", ROOT),
        ],
        seed=None,
        notes=(
            "V2-001 lineage bootstrap: control-plane/data-governance/pre-registration only. "
            "No MODEL_V2 training and no MODEL_V1 retraining occurred."
        ),
    )
    write_model_v2_run_manifest(manifest, OUT / "run_manifest.json", SCHEMA)

    artifacts = sorted(p.name for p in OUT.glob("*.json") if p.name != "artifact_hashes.json")
    hashes = {f"reports/model_v2/v2_001/{name}": hash_file(OUT / name) for name in artifacts}
    hashes.update(
        {
            "configs/model_v2/research_protocol_v1.yaml": hash_file(
                ROOT / "configs/model_v2/research_protocol_v1.yaml"
            ),
            "docs/MODEL_V2_RESEARCH_PROTOCOL_V1.md": hash_file(
                ROOT / "docs/MODEL_V2_RESEARCH_PROTOCOL_V1.md"
            ),
            "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V1.lock.json": hash_file(
                ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V1.lock.json"
            ),
            "manifests/model_v2/cv/MITDB_TRAIN_CV_V2_V1.csv": hash_file(
                ROOT / "manifests/model_v2/cv/MITDB_TRAIN_CV_V2_V1.csv"
            ),
            "manifests/model_v2/cv/MITDB_TRAIN_CV_V2_V1.lock.json": hash_file(
                ROOT / "manifests/model_v2/cv/MITDB_TRAIN_CV_V2_V1.lock.json"
            ),
            "manifests/model_v2/cv/MITDB_TRAIN_INNER_V2_V1.csv": hash_file(
                ROOT / "manifests/model_v2/cv/MITDB_TRAIN_INNER_V2_V1.csv"
            ),
            "manifests/model_v2/cv/MITDB_TRAIN_INNER_V2_V1.lock.json": hash_file(
                ROOT / "manifests/model_v2/cv/MITDB_TRAIN_INNER_V2_V1.lock.json"
            ),
            "manifests/model_v2/task_registry_v1.csv": hash_file(
                ROOT / "manifests/model_v2/task_registry_v1.csv"
            ),
            "manifests/model_v2/gate_registry_v1.csv": hash_file(
                ROOT / "manifests/model_v2/gate_registry_v1.csv"
            ),
            "manifests/model_v2/component_registry_v1.csv": hash_file(
                ROOT / "manifests/model_v2/component_registry_v1.csv"
            ),
        }
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
    print("V2-001 evidence generated")


if __name__ == "__main__":
    main()
