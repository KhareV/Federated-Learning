# ruff: noqa: E501
"""CAPSTONE_DEMO_WORKSPACE_V1 -- isolated runtime workspace of the faculty demo.

Runtime state (SQLite, federation artifacts, candidate artifacts, logs) lives OUTSIDE the Git working tree,
in a directory that carries a sentinel manifest ``CAPSTONE_DEMO_WORKSPACE_V1.json``. Reset/delete may operate
only on a validated workspace (valid sentinel, not the repository, not an ancestor of it, not the home
directory, not a filesystem root). FRESH never silently erases an existing workspace; RESUME needs the sentinel.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_VERSION = "CAPSTONE_DEMO_WORKSPACE_V1"
SENTINEL = "CAPSTONE_DEMO_WORKSPACE_V1.json"
SUBDIRS = ("federation", "candidates", "logs")
SECRET_PATTERNS = (r"CLERK_SECRET_KEY\s*=\s*\S+", r"CLERK_JWT_KEY\s*=\s*\S+", r"\bsk_(live|test)_[A-Za-z0-9]+", r"Bearer\s+[A-Za-z0-9._-]{16,}",
                   r"Authorization:\s*\S+", r"__session=", r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}")


class WorkspaceError(RuntimeError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}:{detail}" if detail else code)
        self.code = code


def _commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN"


def assert_outside_repository(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved == ROOT or ROOT in resolved.parents or resolved in ROOT.parents:
        raise WorkspaceError("WORKSPACE_MUST_BE_OUTSIDE_THE_REPOSITORY", str(resolved))
    return resolved


def forbidden_reset_target(path: Path) -> str | None:
    """Reason a path may never be reset, or None."""
    resolved = path.expanduser().resolve()
    home = Path.home().resolve()
    if resolved == Path(resolved.anchor) or len(resolved.parts) <= 2:
        return "FILESYSTEM_ROOT_OR_TOP_LEVEL"
    if resolved == home or resolved in home.parents:
        return "HOME_DIRECTORY_OR_ANCESTOR"
    if resolved == ROOT or resolved in ROOT.parents or ROOT in resolved.parents:
        return "REPOSITORY_ROOT_ANCESTOR_OR_DESCENDANT"
    return None


def read_sentinel(path: Path) -> dict:
    sentinel = path / SENTINEL
    if not sentinel.is_file():
        raise WorkspaceError("WORKSPACE_SENTINEL_MISSING", str(path))
    try:
        data = json.loads(sentinel.read_text())
    except ValueError as error:
        raise WorkspaceError("WORKSPACE_SENTINEL_INVALID", str(path)) from error
    if data.get("workspace_version") != WORKSPACE_VERSION or not isinstance(data.get("paths"), dict):
        raise WorkspaceError("WORKSPACE_SENTINEL_INVALID", str(path))
    return data


class Workspace:
    def __init__(self, path: Path, manifest: dict) -> None:
        self.path, self.manifest = path, manifest

    @property
    def db(self) -> Path:
        return self.path / "product.sqlite3"

    @property
    def federation(self) -> Path:
        return self.path / "federation"

    @property
    def candidates(self) -> Path:
        return self.path / "candidates"

    @property
    def logs(self) -> Path:
        return self.path / "logs"

    @classmethod
    def create_fresh(cls, path: str | Path | None = None) -> Workspace:
        if path is None:
            root = Path(tempfile.mkdtemp(prefix="nhm-faculty-demo-")).resolve()
        else:
            root = assert_outside_repository(Path(path))
            if root.exists() and any(root.iterdir()):
                raise WorkspaceError("WORKSPACE_NOT_EMPTY_FOR_FRESH_MODE", str(root))
            root.mkdir(parents=True, exist_ok=True)
        assert_outside_repository(root)
        for sub in SUBDIRS:
            (root / sub).mkdir(exist_ok=True)
        manifest = {"workspace_version": WORKSPACE_VERSION, "created_at_utc": datetime.now(UTC).isoformat(), "repository_commit": _commit(),
                    "product_api": "CAPSTONE_PRODUCT_API_V1_3", "released_runtime": "SOFTWARE_SYSTEM_V2/MODEL_V2_FINAL", "auth_mode": "DEMO",
                    "paths": {"database": "product.sqlite3", "federation_artifacts": "federation", "candidate_artifacts": "candidates", "logs": "logs"}}
        (root / SENTINEL).write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
        return cls(root, manifest)

    @classmethod
    def open_resume(cls, path: str | Path) -> Workspace:
        root = assert_outside_repository(Path(path))
        manifest = read_sentinel(root)
        for sub in SUBDIRS:
            (root / sub).mkdir(exist_ok=True)
        return cls(root, manifest)

    @staticmethod
    def reset(path: str | Path) -> None:
        """Delete ONLY a validated demo workspace."""
        target = Path(path).expanduser()
        reason = forbidden_reset_target(target)
        if reason:
            raise WorkspaceError("UNSAFE_RESET_TARGET", reason)
        resolved = target.resolve()
        if not resolved.is_dir():
            raise WorkspaceError("RESET_TARGET_NOT_A_DIRECTORY", str(resolved))
        read_sentinel(resolved)  # raises without a valid sentinel
        shutil.rmtree(resolved)


def scan_logs_for_secrets(logs: Path) -> dict:
    hits = []
    for log in sorted(logs.glob("*.log")):
        text = log.read_text(errors="replace")
        for pattern in SECRET_PATTERNS:
            if re.search(pattern, text):
                hits.append({"log": log.name, "pattern": pattern})
    return {"logs_scanned": sorted(p.name for p in logs.glob("*.log")), "secret_pattern_hits": hits, "clean": not hits}
