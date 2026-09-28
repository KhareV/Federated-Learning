#!/usr/bin/env python3
"""Offline, fixture-driven T001 smoke execution."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from nhm.config import load_yaml, validate_base_config
from nhm.hashing import hash_canonical_json, hash_file
from nhm.run_manifest import artifact_record, create_run_manifest, write_run_manifest

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/base.yaml"
FIXTURE = ROOT / "tests/fixtures/mongodb_observed_v0.json"
SCHEMA = ROOT / "contracts/run_manifest_v1.schema.json"
DEPENDENCIES = ROOT / "reports/t001/dependencies.txt"
REPORT_DIR = ROOT / "reports/t001"


def validate_fixture(fixture: dict[str, object]) -> None:
    """Validate only the observed structure; never infer physiological ranges."""
    if fixture.get("fixture_origin") != "example_observed_hardware_document":
        raise ValueError("Unexpected fixture origin")
    if fixture.get("physiological_validity") != "UNVERIFIED":
        raise ValueError("Fixture must not claim physiological validity")
    document = fixture.get("document")
    if not isinstance(document, dict) or set(document) != {
        "_id",
        "bpm",
        "spo2",
        "ecg",
        "timestamp",
    }:
        raise ValueError("Observed MongoDB fixture shape does not match V0")
    timestamp = document["timestamp"]
    if not isinstance(timestamp, str):
        raise ValueError("Fixture timestamp must use deterministic ISO-8601 text")
    datetime.fromisoformat(timestamp.replace("Z", "+00:00"))


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    config = load_yaml(CONFIG)
    validate_base_config(config)
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    validate_fixture(fixture)

    canonical_probe_first = hash_canonical_json({"a": 1, "b": 2})
    canonical_probe_second = hash_canonical_json({"b": 2, "a": 1})
    if canonical_probe_first != canonical_probe_second:
        raise RuntimeError("Canonical hashing is not deterministic")

    dependencies = DEPENDENCIES if DEPENDENCIES.exists() else None
    inputs = [artifact_record(CONFIG, ROOT), artifact_record(FIXTURE, ROOT)]
    manifest = create_run_manifest(
        ROOT,
        run_id="t001-smoke",
        phase_id="T001",
        task_id="T001",
        config_path=CONFIG,
        dependency_snapshot_path=dependencies,
        input_artifacts=inputs,
        seed=None,
        notes="Structural bootstrap only; physiological validity remains UNVERIFIED.",
    )
    manifest_path = REPORT_DIR / "run_manifest.json"
    write_run_manifest(manifest, manifest_path, SCHEMA)

    report = {
        "report_version": "1.0",
        "phase_id": "T001",
        "spec_version": "2.2",
        "status": "PASS",
        "claims": {
            "repository_config_bootstrap": True,
            "structural_fixture_validation": True,
            "deterministic_hashing": True,
            "manifest_capture": True,
            "sensor_physiological_validity": "UNVERIFIED",
        },
        "artifacts": {
            "config_sha256": hash_file(CONFIG),
            "fixture_sha256": hash_file(FIXTURE),
            "run_manifest_sha256": hash_file(manifest_path),
        },
    }
    (REPORT_DIR / "smoke_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("T001 smoke: PASS (structural only; physiological validity UNVERIFIED)")


if __name__ == "__main__":
    main()

