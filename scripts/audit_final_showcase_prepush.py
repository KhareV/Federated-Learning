# ruff: noqa: E501
"""Pre-push governance and integrity audit for NHM-FINAL-SHOWCASE-001 (read-only). Writes reports/final_showcase_audit/pre_push_audit.json.
  python -m scripts.audit_final_showcase_prepush --tests "<pytest summary line>" """

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIAG = "artifacts/observatory/NHM_OBS_DIAG_001.lock.json"
V1 = "artifacts/observatory/NHM_RESEARCH_OBSERVATORY_V1.lock.json"


def git(*a: str) -> str:
    return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


def blob_sha(commit: str, path: str) -> str | None:
    r = subprocess.run(["git", "show", f"{commit}:{path}"], cwd=ROOT, capture_output=True)
    return hashlib.sha256(r.stdout).hexdigest() if r.returncode == 0 else None


def historical(commit: str) -> dict:
    work = tempfile.mkdtemp(prefix=f"audit-wt-{commit}-")
    subprocess.run(["git", "worktree", "add", "-q", "--detach", work, commit], cwd=ROOT, check=True)
    out = {}
    try:
        env = {**os.environ, "PYTHONPATH": f"{work}/src:{work}"}
        for name in ("verify_obs_diag_001", "verify_observatory_v1"):
            r = subprocess.run([sys.executable, "-m", f"scripts.{name}"], cwd=work, env=env, capture_output=True, text=True)
            out[name] = {"exit": r.returncode, "tail": (r.stdout + r.stderr).strip().splitlines()[-1][:160]}
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", work], cwd=ROOT, check=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tests", default="NOT_RUN")
    a = ap.parse_args()
    commits = ["7d8a90a", "7debd49", "aa36f53", "3713c20"]
    report = {
        "head": git("rev-parse", "HEAD"), "origin_main": git("rev-parse", "origin/main"), "ahead_behind_vs_origin": git("rev-list", "--left-right", "--count", "origin/main...HEAD"),
        "obs_diag_lock_sha256_by_commit": {c: blob_sha(c, DIAG) for c in commits}, "obs_diag_lock_sha256_working_tree": hashlib.sha256((ROOT / DIAG).read_bytes()).hexdigest(),
        "v1_lock_sha256_by_commit": {c: blob_sha(c, V1) for c in ("7e91690", *commits)}, "v1_lock_sha256_working_tree": hashlib.sha256((ROOT / V1).read_bytes()).hexdigest(),
        "obs_diag_lock_commits": git("log", "--format=%h", "--", DIAG).split(),
        "historical_verification": {c: historical(c) for c in ("7d8a90a", "aa36f53")},
        "current_verification": json.loads(subprocess.run([sys.executable, "-m", "scripts.verify_final_showcase", "--lock"], cwd=ROOT, env={**os.environ, "PYTHONPATH": "src:."}, capture_output=True, text=True).stdout.strip().splitlines()[-1]),
        "final_lock_sha256": hashlib.sha256((ROOT / "artifacts/final_showcase/NHM_FINAL_SHOWCASE_001.lock.json").read_bytes()).hexdigest(),
        "protected_surface_diff_vs_aa36f53": [p for p in git("diff", "--name-only", "aa36f53", "--", "artifacts/capstone", "preprocessing", "federated", "product/federation", "product/monitoring", "product/models", "capstone_persistence", "evaluation", "datasets", "simulation", "src", "models", "checkpoints", "api/product_app_v1_1.py", "api/product_app_v1_2.py", "api/product_app_v1_3.py", "api/runtime_v2.py", "deployment", "fusion", ":(exclude)artifacts/capstone/*.amendment_*.json").split("\n") if p],
        "frozen_evidence_diff_vs_aa36f53": [p for p in git("diff", "--name-only", "aa36f53", "--", "reports/model_v2", "reports/observatory", "reports/v2_fl_005", "checkpoints", "contracts").split("\n") if p],
        "default_sqlite": {"path": "data/capstone/product.sqlite3", "git_tracked": bool(git("ls-files", "data/capstone/product.sqlite3")), "mtime_epoch": int((ROOT / "data/capstone/product.sqlite3").stat().st_mtime), "size": (ROOT / "data/capstone/product.sqlite3").stat().st_size},
        "tests": a.tests, "bibliography": "UNVERIFIED: manuscript is not reference-complete; all citation slots are REFERENCE_REQUIRED",
    }
    out = ROOT / "reports/final_showcase_audit"
    out.mkdir(parents=True, exist_ok=True)
    (out / "pre_push_audit.json").write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: report[k] for k in ("obs_diag_lock_sha256_by_commit", "obs_diag_lock_sha256_working_tree", "historical_verification", "current_verification", "protected_surface_diff_vs_aa36f53", "frozen_evidence_diff_vs_aa36f53", "default_sqlite")}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
