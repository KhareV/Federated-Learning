"""CAP-009 entry inventory and protected-file comparison."""

from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path

from scripts.cap_001_protected_audit import named_components, tracked_hashes
from scripts.cap_008_protected_audit import all_locks
from src.nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/capstone/cap_009"
ENTRY = "bdc16611290d371abbcca582920086dcfe4d49a8"


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def registry_statuses() -> dict[str, dict[str, str]]:
    result = {}
    for name, key in (("task", "task_id"), ("gate", "gate_id")):
        path = ROOT / f"manifests/capstone/{name}_registry_v1.csv"
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        result[name] = {row[key]: row["status"] for row in rows}
    return result


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def entry() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    head = git("rev-parse", "HEAD")
    origin = git("rev-parse", "origin/main")
    status = git("status", "--porcelain")
    if head != ENTRY or origin != head or status not in {
        "", "?? scripts/cap_009_protected_audit.py"
    }:
        raise RuntimeError("CAP009_ENTRY_STATE_CONFLICT")
    statuses = registry_statuses()
    expected_tasks = {f"CAP-{i:03d}": "PASS" for i in range(1, 9)}
    expected_tasks.update({f"CAP-{i:03d}": "NOT_STARTED" for i in range(9, 12)})
    expected_gates = {f"CAPG{i}": "PASS" for i in range(8)}
    if any(statuses["task"].get(k) != v for k, v in expected_tasks.items()):
        raise RuntimeError("CAP009_TASK_STATUS_CONFLICT")
    if any(statuses["gate"].get(k) != v for k, v in expected_gates.items()):
        raise RuntimeError("CAP009_GATE_STATUS_CONFLICT")
    locks = all_locks()
    if not all(value["verified"] for value in locks.values()):
        raise RuntimeError("CAP009_PRIOR_LOCK_FAILURE")
    files = tracked_hashes()
    components = named_components()
    if any(value["sha256"] is None for value in components.values()):
        raise RuntimeError("CAP009_UNRESOLVED_PROTECTED_COMPONENT")
    audit = {
        "phase": "CAP-009",
        "entry_sha": head,
        "origin_main_sha": origin,
        "expected_entry_sha": ENTRY,
        "working_tree_clean_before_entry": True,
        "entry_audit_script_untracked_during_generation": bool(status),
        "intervening_commits": [],
        "prior_tasks": expected_tasks,
        "prior_gates": expected_gates,
        "cap_010_011_not_started": True,
        "prior_locks_verified": all(value["verified"] for value in locks.values()),
        "protected_tracked_file_count": len(files),
        "ci_queried": False,
        "ci_triggered": False,
    }
    snapshot = {
        "entry_sha": head,
        "tracked_file_count": len(files),
        "tracked_files_sha256": files,
        "named_components": components,
        "frontend": {p: digest for p, digest in files.items() if p.startswith("frontend/")},
        "protected_predecessor_locks": {
            p: hash_file(ROOT / p)
            for p in (
                "artifacts/capstone/CAPSTONE_UI_V1.lock.json",
                "artifacts/capstone/CAPSTONE_UI_V1_1.lock.json",
            )
        },
    }
    write(OUT / "entry_audit.json", audit)
    write(OUT / "protected_artifact_entry.json", snapshot)
    write(OUT / "prior_lock_verification.json", locks)
    return {"entry_sha": head, "tracked": len(files), "locks": len(locks)}


if __name__ == "__main__":
    print(json.dumps(entry(), sort_keys=True))
