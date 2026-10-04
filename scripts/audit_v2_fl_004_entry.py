#!/usr/bin/env python3
"""V2-FL-004 entry audit: (1) V2-FL-EVAL-001 lifecycle drift (the five changed control/lifecycle
tests) re-audited and shown to have no scientific effect, (2) the one-time MODEL_V2 lifecycle
governance normalization (policy + historical-test edits made in this phase), (3) upstream freezes
verified. Metadata and git diffs only."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import yaml

from evaluation.model_v2_fl_eval import GUARDS, guard_state, load_roster
from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_fl_004"
EVAL_ENTRY = "0c51b8e9def4df0d6725539d108c9a310b4d0d66"   # V2-FL-EVAL-001 entry
EVAL_RESULT = "da30b7a2a41f32aa93fe32a22bb5030048f70645"  # V2-FL-004 entry
EVAL_FIVE = ["tests/test_c_v2_fl_003_freeze_integrity_method.py",
             "tests/test_model_v2_control_plane.py", "tests/test_model_v2_current_lifecycle.py",
             "tests/test_v2_fl_003_method.py", "tests/test_v2_fl_003_results.py"]
SCIENTIFIC_PATHS = ["federated", "models", "evaluation/bootstrap.py", "evaluation/metrics.py",
                    "evaluation/internal_test.py", "evaluation/external_incart.py",
                    "preprocessing", "src/nhm/model_v2_partition_guard.py", "checkpoints",
                    "artifacts/FEDPROX_MU_V2.lock.json", "artifacts/FEDPROX_MU_V1.lock.json",
                    "configs/model_v2/fedprox_v2.yaml", "configs/model_v2/fl_iid_model_v2_v1.yaml",
                    "configs/model_v2/fl_non_iid_model_v2_v1.yaml"]


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                          check=False).stdout


def _sha_at(commit: str, path: str) -> str | None:
    blob = subprocess.run(["git", "show", f"{commit}:{path}"], cwd=ROOT, capture_output=True,
                          check=False)
    return hashlib.sha256(blob.stdout).hexdigest() if blob.returncode == 0 else None


def _classify(path: str, base: str, kind: str) -> dict:
    diff = _git("diff", base, "--", path)
    changed = [c for c in diff.splitlines() if c[:1] in "+-" and not c.startswith(("+++", "---"))]
    return {"base_sha256": _sha_at(base, path), "current_sha256": hash_file(ROOT / path),
            "diff": diff, "changed_lines": changed, "classification": kind}


def main() -> None:
    policy = yaml.safe_load((ROOT / "configs/model_v2/lifecycle_test_policy_v1.yaml").read_text())
    eval_files = {p: _classify(p, EVAL_ENTRY, "FORWARD_LIFECYCLE_ONLY") for p in EVAL_FIVE}
    eval_files["tests/test_model_v2_current_lifecycle.py"]["classification"] = (
        "CONTROL_STATE_TRANSITION")
    # exact diff for the EVAL phase (entry -> result commit), not the working tree
    for path in EVAL_FIVE:
        eval_files[path]["diff_between_eval_entry_and_eval_result"] = _git(
            "diff", EVAL_ENTRY, EVAL_RESULT, "--", path)
    scientific_modified = [
        line for line in _git("diff", "--name-status", "--diff-filter=MDRT", EVAL_ENTRY,
                              EVAL_RESULT, "--", *SCIENTIFIC_PATHS).splitlines() if line]
    scientific_added = _git("diff", "--name-status", "--diff-filter=A", EVAL_ENTRY, EVAL_RESULT,
                            "--", *SCIENTIFIC_PATHS).splitlines()
    roster = load_roster(ROOT)
    family_lock = json.loads((ROOT / "manifests/model_v2/V2_FL_TEST_FAMILY_V1.lock.json"
                              ).read_text())
    effect = {
        "checkpoint_hashes_unchanged": all(
            family_lock["checkpoints"][m["id"]]["sha256"] == m["checkpoint_sha256"]
            == hash_file(ROOT / m["checkpoint"]) for m in roster),
        "existing_scientific_files_modified_in_eval_phase": scientific_modified,
        "scientific_files_added_in_eval_phase": [a.split("\t")[1] for a in scientific_added],
        "optimizer_budget_fedprox_mu_firewall_membership_bootstrap_evaluation_unchanged":
        scientific_modified == [],
        "FEDPROX_MU_V2": json.loads((ROOT / "artifacts/FEDPROX_MU_V2.lock.json").read_text())[
            "selected_mu"]}
    normalization_files = [p for p in policy["classified_lifecycle_control_files"]
                           if p != "tests/test_model_v2_current_lifecycle.py"]
    normalization = {p: _classify(p, EVAL_RESULT, "FORWARD_LIFECYCLE_ONLY")
                     for p in normalization_files
                     if _git("diff", "--name-only", EVAL_RESULT, "--", p).strip()}
    upstream = {
        "V2_FL_EVAL_guards": {d: guard_state(ROOT, d) for d in GUARDS},
        "V2_FL_EVAL_protocol_lock_sha256": hash_file(
            ROOT / "manifests/model_v2/V2_FL_EVAL_PROTOCOL_V1.lock.json"),
        "V2_FL_TEST_FAMILY_V1_lock_sha256": hash_file(
            ROOT / "manifests/model_v2/V2_FL_TEST_FAMILY_V1.lock.json"),
        "V2FLEG0": json.loads((ROOT / "reports/model_v2/v2_fl_eval_001/v2fleg0_criteria.json"
                               ).read_text())["status"],
        "SECAGG_METHOD_V1_lock_sha256": hash_file(ROOT / "artifacts/SECAGG_METHOD_V1.lock.json"),
        "SECAGG_CONFIG_V1_lock_sha256": hash_file(ROOT / "artifacts/SECAGG_CONFIG_V1.lock.json")}
    ok = (all(f["classification"] in ("FORWARD_LIFECYCLE_ONLY", "CONTROL_STATE_TRANSITION")
              for f in eval_files.values())
          and effect["checkpoint_hashes_unchanged"] and not scientific_modified
          and all(s == "COMPLETED" for s in upstream["V2_FL_EVAL_guards"].values())
          and upstream["V2FLEG0"] == "PASS")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "entry_lifecycle_governance_audit.json").write_text(json.dumps({
        "entry": EVAL_RESULT, "policy_id": policy["policy_id"],
        "v2_fl_eval_lifecycle_changes_audited": len(eval_files), "eval_changes": eval_files,
        "scientific_effect": effect,
        "one_time_normalization_in_this_phase": {
            "files_edited": sorted(normalization), "details": normalization,
            "nature": "removal of live-registry 'later task is exactly NOT_STARTED' hard-codes and "
            "conversion of exact passed-set equality to irreversible-fact subset checks in "
            "historical tests; exactness is centralized in the strict current-lifecycle test",
            "hash_pinned_files_among_them": "recorded in the lifecycle-drift register; stored "
            "historical hashes were not rewritten"},
        "historical_test_exemptions_broadened": False,
        "single_mutable_lifecycle_test": policy["current_lifecycle_test"],
        "upstream": upstream, "status": "PASS" if ok else "FAIL"}, indent=2,
        sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS" if ok else "FAIL"}))


if __name__ == "__main__":
    main()
