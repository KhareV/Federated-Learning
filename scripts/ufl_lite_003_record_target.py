# ruff: noqa: E501
"""Record UFL_LITE_ACCEPTANCE_TARGET_SHA (the pushed commit that freezes the UFL-LITE-003 method) BEFORE any canonical evidence exists.
Facts only: the SHA, push state, the protected-tree delta from the entry (must be empty: additive verification material only) and the absence of canonical evidence at the target."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRY = "9324ef40ecb8fdecfc4880aa827bc68b45e4f9a0"
ADDITIVE = ("manifests/ufl_lite/", "configs/ufl_lite/", "docs/ufl_lite/", "artifacts/ufl_lite/", "reports/ufl_lite/", "scripts/ufl_lite_003_", "tests/test_ufl_lite_003_")
MODIFIABLE = ("manifests/ufl_lite/task_registry_v1.csv", "manifests/ufl_lite/gate_registry_v1.csv")
CANONICAL = ("owner_e2e_observations.json", "owner_e2e_analysis.json", "secret_and_persistence_audit.json", "clean_clone", "mutation_controls.json", "uflg2_criteria.json", "test_report.json", "demo_regression.json")


def g(*a: str) -> str:
    return subprocess.run(["git", *a], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def main() -> int:
    subprocess.run(["git", "fetch", "origin"], cwd=ROOT, check=True, capture_output=True)
    sha = g("rev-parse", "HEAD")
    entry_files = set(g("ls-tree", "-r", "--name-only", ENTRY).split())
    delta = [p for p in g("diff", "--name-only", ENTRY, sha).split() if not p.startswith(ADDITIVE) or (p in entry_files and p not in MODIFIABLE)]
    existing = set(g("ls-tree", "-r", "--name-only", sha, "--", "reports/ufl_lite/ufl_lite_003").split())
    canonical_present = sorted(p for p in existing if any(p.split("reports/ufl_lite/ufl_lite_003/")[1].startswith(c) for c in CANONICAL))
    facts = {"acceptance_target_sha": sha, "entry_sha": ENTRY, "pushed_to_origin_main_at_record": g("rev-parse", "origin/main") == sha, "working_tree_clean_at_record": g("status", "--porcelain") == "", "protected_tree_delta_from_entry": delta,
             "canonical_evidence_existed_at_target": bool(canonical_present), "canonical_evidence_paths_at_target": canonical_present, "commit_subject": g("log", "-1", "--format=%s", sha),
             "release_vehicle": "the exact Git repository state at acceptance_target_sha (no archive)", "product_feature_delta": "none: additive verification material only"}
    print(json.dumps(facts, indent=1, sort_keys=True))
    return 0 if facts["pushed_to_origin_main_at_record"] and facts["working_tree_clean_at_record"] and not delta and not canonical_present else 1


if __name__ == "__main__":
    sys.exit(main())
