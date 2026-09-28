"""Versioned run-manifest creation, validation, and writing."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from nhm.hashing import hash_file
from nhm.reproducibility import capture_execution_identity

MANIFEST_VERSION = "1.0"


def artifact_record(path: str | Path, repository_root: str | Path) -> dict[str, str]:
    """Create a repository-relative artifact record with SHA-256."""
    root = Path(repository_root).resolve()
    artifact = Path(path).resolve()
    relative = str(artifact.relative_to(root)) if artifact.is_relative_to(root) else str(artifact)
    return {"path": relative, "sha256": hash_file(artifact)}


def create_run_manifest(
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
) -> dict[str, Any]:
    """Create a manifest from live execution identity."""
    identity = capture_execution_identity(
        repository_root,
        config_path=config_path,
        dependency_snapshot_path=dependency_snapshot_path,
        seed=seed,
    )
    return {
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
    }


def validate_run_manifest(manifest: dict[str, Any], schema_path: str | Path) -> None:
    """Validate a manifest against the versioned JSON Schema, including formats."""
    with Path(schema_path).open(encoding="utf-8") as handle:
        schema = json.load(handle)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(manifest)


def write_run_manifest(
    manifest: dict[str, Any], output_path: str | Path, schema_path: str | Path
) -> None:
    """Validate then atomically replace a manifest JSON file."""
    validate_run_manifest(manifest, schema_path)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(f"{output.suffix}.tmp")
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(output)

