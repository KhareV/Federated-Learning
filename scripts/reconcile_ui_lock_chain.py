# ruff: noqa: E501
"""File-by-file reconciliation of the UI lock chain against the current working tree (read-only evidence, never edits a lock).

For every frontend file bound by the V1_9..FINAL_SHOWCASE tip and every file in the current frontend set: the digest the accepted tip
expects, the digest the next additive successor binds, the current digest, the commits that touched the file after the accepted tip,
and a verdict: UNCHANGED, AUTHORIZED_BY_SUCCESSOR (current bytes equal the digest of a validly chained successor lock), or UNAUTHORIZED."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TIP_PATH = "artifacts/final_showcase/NHM_FINAL_SHOWCASE_001.lock.json"
SUCCESSORS = [("NHM_FL10_001", "artifacts/fl10/NHM_FL10_001.lock.json"),
              ("NHM_UNIFIED_LIVE_FEDERATION_STUDIO_001", "artifacts/unified_studio/NHM_UNIFIED_LIVE_FEDERATION_STUDIO_001.lock.json")]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def commits_touching(path: str, since_ref: str) -> list[str]:
    out = subprocess.run(["git", "log", "--format=%h %s", f"{since_ref}..HEAD", "--", path], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [line[:90] for line in out.splitlines()]


def reconcile(since_ref: str = "274323730d1c7355f688ad4c9ff01ecbfb746501") -> dict[str, Any]:
    from scripts.freeze_observatory_v1 import frontend_files

    tip = json.loads((ROOT / TIP_PATH).read_text())
    expected = dict(tip["bound_artifacts"])
    successor_maps: dict[str, dict[str, str]] = {}
    for lock_id, rel in SUCCESSORS:
        if not (ROOT / rel).exists():          # a successor that has not been frozen yet contributes nothing
            continue
        lock = json.loads((ROOT / rel).read_text())
        successor_maps[lock_id] = dict(lock["frontend_files"])
    current_set = set(frontend_files())
    rows = []
    for path in sorted(set(expected) | current_set | {p for m in successor_maps.values() for p in m}):
        target = ROOT / path
        now = sha(target) if target.is_file() else None
        tip_digest = expected.get(path)
        bound_by = {lock_id: m.get(path) for lock_id, m in successor_maps.items()}
        if now is not None and now == tip_digest:
            verdict = "UNCHANGED"
        elif now is not None and any(d == now for d in bound_by.values()):
            verdict = "AUTHORIZED_BY_SUCCESSOR"
        else:
            verdict = "UNAUTHORIZED"
        rows.append({"path": path, "tip_sha256": tip_digest, "successor_sha256": bound_by, "current_sha256": now, "verdict": verdict,
                     "commits_since_tip": commits_touching(path, since_ref) if verdict != "UNCHANGED" else []})
    summary: dict[str, int] = {}
    for row in rows:
        summary[row["verdict"]] = summary.get(row["verdict"], 0) + 1
    return {"tip": TIP_PATH, "tip_lock_sha256": sha(ROOT / TIP_PATH), "since": since_ref, "summary": summary, "files": rows}


if __name__ == "__main__":
    result = reconcile()
    print(json.dumps({"summary": result["summary"], "non_unchanged": [(r["path"], r["verdict"], r["commits_since_tip"]) for r in result["files"] if r["verdict"] != "UNCHANGED"]}, indent=1))
