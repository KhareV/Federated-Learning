"""Non-secret execution identity capture for reproducible NHM runs."""

from __future__ import annotations

import platform
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nhm.hashing import hash_file

SPEC_VERSION = "2.2"
CURRENT_PHASE = "T003"


def _git_output(repository_root: Path, *args: str) -> str | None:
    result = subprocess.run(
        ["git", *args],
        cwd=repository_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def git_identity(repository_root: str | Path) -> tuple[str | None, bool | None]:
    """Return Git commit and dirty state, or explicit unavailable values."""
    root = Path(repository_root)
    commit = _git_output(root, "rev-parse", "HEAD")
    inside = _git_output(root, "rev-parse", "--is-inside-work-tree")
    if inside != "true":
        return None, None
    status = _git_output(root, "status", "--porcelain")
    return commit, None if status is None else bool(status)


def capture_execution_identity(
    repository_root: str | Path,
    *,
    config_path: str | Path | None = None,
    dependency_snapshot_path: str | Path | None = None,
    seed: int | None = None,
    include_hostname: bool = False,
) -> dict[str, Any]:
    """Capture reproducibility metadata, intentionally excluding environment secrets."""
    root = Path(repository_root).resolve()
    commit, dirty = git_identity(root)

    def relative_and_hash(path_value: str | Path | None) -> tuple[str | None, str | None]:
        if path_value is None:
            return None, None
        path = Path(path_value).resolve()
        relative = str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
        return relative, hash_file(path)

    config_relative, config_hash = relative_and_hash(config_path)
    deps_relative, deps_hash = relative_and_hash(dependency_snapshot_path)
    identity: dict[str, Any] = {
        # timezone.utc keeps this bootstrap runnable on the documented Python 3.9 fallback.
        "created_at_utc": datetime.now(timezone.utc).isoformat().replace(  # noqa: UP017
            "+00:00", "Z"
        ),
        "git_commit": commit,
        "git_dirty": dirty,
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "os": platform.system(),
        "architecture": platform.machine(),
        "config_path": config_relative,
        "config_sha256": config_hash,
        "dependency_snapshot_path": deps_relative,
        "dependency_snapshot_sha256": deps_hash,
        "spec_version": SPEC_VERSION,
        "current_phase": CURRENT_PHASE,
        "seed": seed,
    }
    if include_hostname:
        identity["hostname"] = socket.gethostname()
    return identity


def runtime_version_line() -> str:
    """Return an exact, single-line Python runtime description."""
    return sys.version.replace("\n", " ")
