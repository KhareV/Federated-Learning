"""C-V2-001-VERIFY Section 3: additive MODEL_V2 run-manifest schema tests.

Proves: a valid V2-001 manifest validates against contracts/model_v2_run_manifest_v1.schema.
json; a malformed V2 task_id/phase_id fails closed (both at the helper layer and at schema
validation); a manifest missing a required field fails schema validation; the canonical
T-task schema (contracts/run_manifest_v1.schema.json) remains byte-unchanged; and the V2
schema/manifest-building path is deterministic.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema.exceptions import ValidationError

from nhm.hashing import hash_file
from nhm.model_v2_run_manifest import (
    ModelV2RunManifestError,
    artifact_record,
    create_model_v2_run_manifest,
    validate_model_v2_run_manifest,
    write_model_v2_run_manifest,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "contracts/model_v2_run_manifest_v1.schema.json"
CANONICAL_SCHEMA = ROOT / "contracts/run_manifest_v1.schema.json"
CANONICAL_SCHEMA_SHA_EXPECTED = (
    "1cf3b21a400a2eeab482279a5172f9ab5665478bb57edc899a819d5c1f0e1731"
)


def _valid_manifest() -> dict:
    return create_model_v2_run_manifest(
        ROOT,
        run_id="test-run",
        phase_id="V2-001",
        task_id="V2-001",
        config_path=None,
        dependency_snapshot_path=None,
        input_artifacts=[artifact_record(ROOT / "checkpoints/MODEL_V1.pt", ROOT)],
        output_artifacts=[],
        seed=None,
        notes="test manifest",
    )


def test_valid_v2_001_manifest_passes_schema_validation() -> None:
    manifest = _valid_manifest()
    validate_model_v2_run_manifest(manifest, SCHEMA)


def test_malformed_task_id_rejected_by_helper_before_schema() -> None:
    with pytest.raises(ModelV2RunManifestError, match="MODEL_V2_RUN_MANIFEST_INVALID_TASK_ID"):
        create_model_v2_run_manifest(
            ROOT,
            run_id="test-run",
            phase_id="V2-001",
            task_id="T015",
            config_path=None,
            dependency_snapshot_path=None,
        )


def test_malformed_phase_id_rejected_by_helper_before_schema() -> None:
    with pytest.raises(ModelV2RunManifestError, match="MODEL_V2_RUN_MANIFEST_INVALID_PHASE_ID"):
        create_model_v2_run_manifest(
            ROOT,
            run_id="test-run",
            phase_id="V2-abc",
            task_id="V2-001",
            config_path=None,
            dependency_snapshot_path=None,
        )


def test_malformed_task_id_also_rejected_directly_by_schema() -> None:
    manifest = _valid_manifest()
    manifest["task_id"] = "T015"
    with pytest.raises(ValidationError):
        validate_model_v2_run_manifest(manifest, SCHEMA)


def test_manifest_missing_required_field_fails_validation() -> None:
    manifest = _valid_manifest()
    del manifest["git_commit"]
    with pytest.raises(ValidationError):
        validate_model_v2_run_manifest(manifest, SCHEMA)


def test_manifest_with_unknown_extra_field_fails_validation() -> None:
    manifest = _valid_manifest()
    manifest["unexpected_field"] = "nope"
    with pytest.raises(ValidationError):
        validate_model_v2_run_manifest(manifest, SCHEMA)


def test_canonical_t_task_schema_byte_unchanged() -> None:
    assert hash_file(CANONICAL_SCHEMA) == CANONICAL_SCHEMA_SHA_EXPECTED


def test_canonical_schema_still_rejects_v2_ids() -> None:
    """Confirms the canonical schema was never loosened to accept V2-xxx IDs."""
    schema = json.loads(CANONICAL_SCHEMA.read_text(encoding="utf-8"))
    assert schema["properties"]["phase_id"]["pattern"] == "^T[0-9]{3}$"


def test_v2_schema_id_is_explicit_in_every_manifest() -> None:
    manifest = _valid_manifest()
    assert manifest["schema_id"] == "MODEL_V2_RUN_MANIFEST_V1"


def test_write_and_reread_roundtrip_is_deterministic(tmp_path: Path) -> None:
    manifest = _valid_manifest()
    manifest["created_at_utc"] = "2026-10-02T00:00:00Z"
    manifest["git_commit"] = "0" * 40

    out_path = tmp_path / "manifest.json"
    write_model_v2_run_manifest(manifest, out_path, SCHEMA)
    first = out_path.read_text(encoding="utf-8")

    write_model_v2_run_manifest(manifest, out_path, SCHEMA)
    second = out_path.read_text(encoding="utf-8")

    assert first == second


def test_v2_001_evidence_run_manifest_validates() -> None:
    manifest = json.loads(
        (ROOT / "reports/model_v2/v2_001/run_manifest.json").read_text(encoding="utf-8")
    )
    validate_model_v2_run_manifest(manifest, SCHEMA)
    assert manifest["task_id"] == "V2-001"
    assert manifest["phase_id"] == "V2-001"
