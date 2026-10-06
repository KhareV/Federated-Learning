# ruff: noqa: E501
"""Record FINAL_EVAL_REPAIR_002_TARGET_SHA (the pushed commit that freezes the FER-001 repair + verification method) BEFORE any canonical evidence exists. Facts only."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts import final_eval_repair_lib as lib

ROOT = lib.ROOT
ENTRY = "3402dc1da1c6d5c029903a9a51a74e4ecc427ec8"
CANONICAL = ("connected_owner", "route_crawl_final", "copy_truth_matrix_final", "landing_browser_audit", "product_browser_audit", "landing_claim_inventory_final", "secret_audit", "clean_clone", "mutation_controls", "ferg1_criteria", "test_report", "demo_regression", "protected_artifact_final", "final_handoff")


def g(*a: str) -> str:
    return lib.git(*a)


def main() -> int:
    subprocess.run(["git", "fetch", "origin"], cwd=ROOT, check=True, capture_output=True)
    sha = g("rev-parse", "HEAD")
    sys.path.insert(0, str(ROOT))
    from scripts.final_eval_repair_002_evaluate_gate import delta_outside_authorised

    delta = delta_outside_authorised(sha)
    existing = g("ls-tree", "-r", "--name-only", sha, "--", "reports/final_eval_repair/fer_002").split()
    pre_existing_ok = {f"reports/final_eval_repair/fer_002/{n}" for n in ("entry_audit.json", "protected_artifact_entry.json", "prior_lock_verification.json", "failed_findings_reproduction.json", "landing_claim_inventory_entry.json", "landing_browser_entry.json", "product_browser_entry.json")}
    canonical_present = sorted(p for p in existing if p not in pre_existing_ok and "/attempt_" not in p and any(Path(p).name.startswith(c) or c in p for c in CANONICAL))
    facts = {"repair_target_sha": sha, "entry_sha": ENTRY, "pushed_to_origin_main_at_record": g("rev-parse", "origin/main") == sha, "working_tree_clean_at_record": g("status", "--porcelain") == "", "unauthorised_delta_from_entry": delta, "canonical_evidence_existed_at_target": bool(canonical_present),
             "canonical_evidence_paths_at_target": canonical_present, "commit_subject": g("log", "-1", "--format=%s", sha), "release_vehicle": "the exact Git repository state at repair_target_sha (no archive)", "note": "candidate build for the unchanged FINAL_EVALUATOR_AUDIT_V1 rerun; NOT an evaluator-ready release"}
    print(json.dumps(facts, indent=1, sort_keys=True))
    return 0 if facts["pushed_to_origin_main_at_record"] and facts["working_tree_clean_at_record"] and not delta and not canonical_present else 1


if __name__ == "__main__":
    sys.exit(main())
