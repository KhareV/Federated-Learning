#!/usr/bin/env python3
"""Generate T008 (AAMI_SVF_MAP_V1 census + label-map freeze) evidence with the canonical
SHA-256 convention.

Runs the offline census builder and the label-map audit, both of which require the
already-acquired, hash-verified local T006/T007 raw data. No network access, no window-
building, no split, no preprocessing, no model training.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from nhm.hashing import hash_file
from nhm.run_manifest import artifact_record, create_run_manifest, write_run_manifest

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports/t008"

CODE_ARTIFACTS = [
    ROOT / "datasets/labels.py",
    ROOT / "scripts/build_annotation_census_t008.py",
    ROOT / "scripts/audit_label_map_t008.py",
]
MANIFEST_ARTIFACTS = [
    ROOT / "manifests/labels/AAMI_SVF_MAP_V1.yaml",
]
CENSUS_ARTIFACTS = [
    REPORT_DIR / "mitdb_annotation_symbol_census.csv",
    REPORT_DIR / "incart_annotation_symbol_census.csv",
    REPORT_DIR / "annotation_symbol_census.csv",
    REPORT_DIR / "symbol_accounting.csv",
]
GATE_EVIDENCE_PATH = ROOT / "reports/labels/label_audit.json"


def run_script(relative_path: str) -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / relative_path)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    print(result.stdout, end="")


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    run_script("scripts/build_annotation_census_t008.py")
    run_script("scripts/audit_label_map_t008.py")

    audit = json.loads(GATE_EVIDENCE_PATH.read_text(encoding="utf-8"))
    if audit["overall_status"] != "PASS":
        raise RuntimeError(f"T008 evidence requires label_audit.json to PASS: {audit['errors']}")

    input_paths = [*CODE_ARTIFACTS, *MANIFEST_ARTIFACTS, ROOT / "contracts/LABEL_SCHEMA_V1.md"]
    output_paths = [*CENSUS_ARTIFACTS, GATE_EVIDENCE_PATH]

    manifest_path = REPORT_DIR / "run_manifest.json"
    manifest = create_run_manifest(
        ROOT,
        run_id="T008-LABEL-MAP-FREEZE-V1",
        phase_id="T008",
        task_id="T008",
        config_path=ROOT / "configs/base.yaml",
        dependency_snapshot_path=ROOT / "reports/t001/dependencies.txt",
        input_artifacts=[artifact_record(path, ROOT) for path in input_paths],
        output_artifacts=[artifact_record(path, ROOT) for path in output_paths],
        notes=(
            "Shared AAMI_SVF_MAP_V1 beat-symbol mapper and AAMI_SVF_WINDOW_V1 window-target "
            "decision rule for MIT-BIH and INCART, plus the full annotation symbol census "
            "with explicit SOURCE vs CORE_CHANNEL_ELIGIBLE scope separation. No window-"
            "building, no patient split, no preprocessing, no model training. G4 closes only "
            "if the label-map audit fully passes."
        ),
    )
    write_run_manifest(manifest, manifest_path, ROOT / "contracts/run_manifest_v1.schema.json")

    hash_paths = [
        *CODE_ARTIFACTS, *MANIFEST_ARTIFACTS, *CENSUS_ARTIFACTS, GATE_EVIDENCE_PATH, manifest_path,
    ]
    missing = [str(path) for path in hash_paths if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Cannot hash missing T008 evidence: {missing}")

    output = REPORT_DIR / "artifact_hashes.json"
    temporary = output.with_suffix(f"{output.suffix}.tmp")
    temporary.write_text(
        json.dumps(
            {
                "manifest_version": "1.0",
                "algorithm": "sha256",
                "rule": (
                    "exact file bytes; this manifest excludes itself to avoid a circular digest"
                ),
                "artifacts": {
                    str(path.relative_to(ROOT)): hash_file(path) for path in sorted(hash_paths)
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(output)
    print("T008 evidence: generated")


if __name__ == "__main__":
    main()
