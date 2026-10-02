#!/usr/bin/env python3
"""Generate the final V2-001 run_manifest.json and artifact_hashes.json from the already
-generated evidence files under reports/model_v2/v2_001/. Machine-generated, not hand-typed."""

from __future__ import annotations

import json
from pathlib import Path

from nhm.hashing import hash_file
from nhm.reproducibility import capture_execution_identity
from nhm.run_manifest import MANIFEST_VERSION, artifact_record

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_001"


def main() -> None:
    # The canonical contracts/run_manifest_v1.schema.json constrains phase_id/task_id to the
    # ^T[0-9]{3}$ pattern (T001-T036 only) and is never touched for the separate MODEL_V2
    # namespace; this V2 manifest reuses the same identity-capture primitive but is written
    # directly (no schema validation against the canonical T-task schema).
    identity = capture_execution_identity(
        ROOT, config_path=ROOT / "configs/model_v2/research_protocol_v1.yaml"
    )
    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "run_id": "v2-001-lineage-bootstrap",
        "created_at_utc": identity["created_at_utc"],
        "phase_id": "V2-001",
        "task_id": "V2-001",
        "spec_version": identity["spec_version"],
        "git_commit": identity["git_commit"],
        "git_dirty": identity["git_dirty"],
        "python_version": identity["python_version"],
        "platform": identity["platform"],
        "config_path": identity["config_path"],
        "config_sha256": identity["config_sha256"],
        "dependency_snapshot_path": None,
        "dependency_snapshot_sha256": None,
        "input_artifacts": [
            artifact_record(ROOT / "checkpoints/MODEL_V1.pt", ROOT),
            artifact_record(ROOT / "artifacts/CAL_V1.json", ROOT),
            artifact_record(ROOT / "manifests/windows/MITDB_WINDOWS_V1.csv", ROOT),
            artifact_record(ROOT / "manifests/splits/MITDB_SPLIT_V1.csv", ROOT),
        ],
        "output_artifacts": [
            artifact_record(
                ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V1.lock.json", ROOT
            ),
            artifact_record(ROOT / "manifests/model_v2/cv/MITDB_TRAIN_CV_V2_V1.csv", ROOT),
            artifact_record(ROOT / "manifests/model_v2/cv/MITDB_TRAIN_INNER_V2_V1.csv", ROOT),
        ],
        "seed": None,
        "notes": (
            "V2-001 lineage bootstrap: control-plane/data-governance/pre-registration only. "
            "No MODEL_V2 training and no MODEL_V1 retraining occurred."
        ),
    }
    (OUT / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

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
