# ruff: noqa: E501
"""FINAL-EVAL-REPAIR-001 shared helpers: dynamic SvelteKit route discovery, UFL lock verification with pure successor amendments, hashing."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ROUTES = ROOT / "frontend/src/routes"
ENTRY = "5d40752442fd1a05dd2459dd216aff51fe4c022c"
UFL_LOCKS = {"UFL_LITE_001": "artifacts/ufl_lite/UFL_LITE_001_PROTOCOL_V1.lock.json", "UFL_LITE_002": "artifacts/ufl_lite/UFL_LITE_002_PROTOCOL_V1.lock.json", "UFL_LITE_003": "artifacts/ufl_lite/UFL_LITE_003_PROTOCOL_V1.lock.json"}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*a: str) -> str:
    return subprocess.run(["git", *a], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def discover_routes(root: Path = ROOT) -> list[dict[str, str]]:
    """Every +page.svelte under frontend/src/routes as a routable pattern (dynamic segments kept in [brackets])."""
    out = []
    for f in sorted((root / "frontend/src/routes").rglob("+page.svelte")):
        rel = f.relative_to(root / "frontend/src/routes").parent.as_posix()
        pattern = "/" if rel == "." else "/" + rel
        out.append({"pattern": pattern, "file": f.relative_to(root).as_posix(), "dynamic": "[" in pattern})
    return out


def verify_ufl_lock(lock_rel: str, root: Path = ROOT) -> dict[str, Any]:
    """Frozen UFL method lock verification with pure old->new SHA successor amendments (artifacts/ufl_lite/<LOCK>.amendment_*.json)."""
    lock = json.loads((root / lock_rel).read_text())
    expected = dict(lock["bound_files"])
    stem = Path(lock_rel).name.replace(".lock.json", "")
    chain = []
    for a in sorted((root / "artifacts/ufl_lite").glob(f"{stem}.amendment_*.json")):
        data = json.loads(a.read_text())
        if data.get("scope") != "SUCCESSOR_COMPATIBILITY_ONLY":
            return {"lock": lock_rel, "verified": False, "reason": "AMENDMENT_NOT_PURE"}
        for path, ch in data["files"].items():
            chain.append({"amendment": a.name, "path": path, "old_matches_previous_link": expected.get(path) == ch["old_sha256"]})
            expected[path] = ch["new_sha256"]
    broken = [c for c in chain if not c["old_matches_previous_link"]]
    mismatches = [p for p, h in expected.items() if not (root / p).exists() or sha(root / p) != h]
    return {"lock": lock_rel, "verified": not broken and not mismatches, "amendments": len({c["amendment"] for c in chain}), "mismatches": mismatches, "broken_chain_links": broken}


def verify_all_ufl_locks(root: Path = ROOT) -> dict[str, dict[str, Any]]:
    return {k: verify_ufl_lock(v, root) for k, v in UFL_LOCKS.items()}


def registry(path: str, key: str) -> dict[str, str]:
    import csv

    with (ROOT / path).open(newline="", encoding="utf-8") as h:
        return {r[key]: r["status"] for r in csv.DictReader(h)}


def tag_target(tag: str) -> str:
    """Commit a remote tag points to (annotated tags are dereferenced)."""
    rows = [ln.split("\t") for ln in subprocess.run(["git", "ls-remote", "origin", f"refs/tags/{tag}", f"refs/tags/{tag}^{{}}"], cwd=ROOT, capture_output=True, text=True).stdout.splitlines() if ln]
    peeled = [sha_ for sha_, ref in rows if ref.endswith("^{}")]
    plain = [sha_ for sha_, ref in rows if not ref.endswith("^{}")]
    return (peeled or plain or [""])[0]


TAGS = {"user-bound-fl-lite-v1": "cf18cba4d7891c514553a1702e227f28dbe26f7c", "capstone-release-v1": "3ad1b07408a0c3556fbc5039f1a7a4fee824db96", "capstone-clerk-connected-v1": "4cb20ec1093f3a8697827abfffc1e5c1fd787055"}


def tags_ok() -> bool:
    return all(tag_target(t) == s for t, s in TAGS.items())


def strip_comments(text: str) -> str:
    return re.sub(r"<!--[\s\S]*?-->", "", re.sub(r"/\*[\s\S]*?\*/", "", text))
