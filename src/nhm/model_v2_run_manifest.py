"""Versioned run-manifest creation, validation, and writing for the separate MODEL_V2
research lineage (C-V2-001-VERIFY). Additive counterpart to nhm.run_manifest: that module and
contracts/run_manifest_v1.schema.json remain byte-unchanged and continue to serve the
canonical T001-T036 namespace exclusively. This module validates against
contracts/model_v2_run_manifest_v1.schema.json (schema_id MODEL_V2_RUN_MANIFEST_V1), which
requires phase_id/task_id to match ^V2-[0-9]{3}$ and fails closed on any other shape.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from nhm.hashing import hash_file
from nhm.reproducibility import capture_execution_identity

MANIFEST_VERSION = "1.0"
SCHEMA_ID = "MODEL_V2_RUN_MANIFEST_V1"
V2_ID_PATTERN = re.compile(r"^V2-[0-9]{3}$")


class ModelV2RunManifestError(ValueError):
    """A MODEL_V2 run manifest field does not satisfy the additive V2 contract."""


def artifact_record(path: str | Path, repository_root: str | Path) -> dict[str, str]:
    """Create a repository-relative artifact record with SHA-256. Identical in shape to
    nhm.run_manifest.artifact_record (duplicated here only to keep this module
    self-contained and independently importable without creating a dependency edge back
    onto the canonical T-task manifest module)."""
    root = Path(repository_root).resolve()
    artifact = Path(path).resolve()
    relative = str(artifact.relative_to(root)) if artifact.is_relative_to(root) else str(artifact)
    return {"path": relative, "sha256": hash_file(artifact)}


def create_model_v2_run_manifest(
    repository_root: str | Path,
    *,
    run_id: str,
    phase_id: str,
    task_id: str,
    config_path: str | Path | None,
    dependency_snapshot_path: str | Path | None,
    input_artifacts: list[dict[str, str]] | None = None,
    output_artifacts: list[dict[str, str]] | None = None,
    seed: int | None = None,
    notes: str | None = None,
    corrective_checkpoint: str | None = None,
) -> dict[str, Any]:
    """Create a MODEL_V2 manifest from live execution identity. Fails closed (before any
    file I/O beyond identity capture) if phase_id/task_id do not match ^V2-[0-9]{3}$."""
    if not V2_ID_PATTERN.match(phase_id):
        raise ModelV2RunManifestError(f"MODEL_V2_RUN_MANIFEST_INVALID_PHASE_ID:{phase_id}")
    if not V2_ID_PATTERN.match(task_id):
        raise ModelV2RunManifestError(f"MODEL_V2_RUN_MANIFEST_INVALID_TASK_ID:{task_id}")

    identity = capture_execution_identity(
        repository_root,
        config_path=config_path,
        dependency_snapshot_path=dependency_snapshot_path,
        seed=seed,
    )
    return {
        "schema_id": SCHEMA_ID,
        "manifest_version": MANIFEST_VERSION,
        "run_id": run_id,
        "created_at_utc": identity["created_at_utc"],
        "phase_id": phase_id,
        "task_id": task_id,
        "spec_version": identity["spec_version"],
        "git_commit": identity["git_commit"],
        "git_dirty": identity["git_dirty"],
        "python_version": identity["python_version"],
        "platform": identity["platform"],
        "config_path": identity["config_path"],
        "config_sha256": identity["config_sha256"],
        "dependency_snapshot_path": identity["dependency_snapshot_path"],
        "dependency_snapshot_sha256": identity["dependency_snapshot_sha256"],
        "input_artifacts": input_artifacts or [],
        "output_artifacts": output_artifacts or [],
        "seed": seed,
        "notes": notes,
        "corrective_checkpoint": corrective_checkpoint,
    }


def validate_model_v2_run_manifest(manifest: dict[str, Any], schema_path: str | Path) -> None:
    """Validate a MODEL_V2 manifest against contracts/model_v2_run_manifest_v1.schema.json,
    including formats. Raises jsonschema.exceptions.ValidationError on any malformed field --
    including a phase_id/task_id that does not match the V2 pattern."""
    with Path(schema_path).open(encoding="utf-8") as handle:
        schema = json.load(handle)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(manifest)


def write_model_v2_run_manifest(
    manifest: dict[str, Any], output_path: str | Path, schema_path: str | Path
) -> None:
    """Validate then atomically replace a MODEL_V2 manifest JSON file."""
    validate_model_v2_run_manifest(manifest, schema_path)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(f"{output.suffix}.tmp")
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(output)
