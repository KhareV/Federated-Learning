"""Create an additive FL10 successor lock only after local gates have passed.

This never edits historical locks. Run after implementation and pure compatibility commits;
commit the generated lock separately, then verify it against the final worktree.
"""

from __future__ import annotations

import json
import subprocess

from scripts.freeze_observatory_v1 import frontend_files
from scripts.verify_fl10_001 import LOCK_PATH, PREDECESSOR, ROOT, sha, verify_evidence

BOUND_PREFIXES = (
    "fl10/", "configs/fl10/", "docs/fl10/", "reports/fl10/", "frontend/src/",
)
BOUND_EXACT = {
    "api/observatory_fl10.py", "api/product_app_observatory_v1.py",
    "scripts/run_fl10.py", "scripts/evaluate_fl10.py",
    "scripts/run_fl10_browser_smoke.py", "scripts/fl10_browser_smoke.mjs",
    "scripts/verify_fl10_001.py", "scripts/freeze_fl10_001.py",
    "scripts/fl10_successor_compat.py", "scripts/verify_final_showcase.py",
    "scripts/verify_obs_diag_001.py", "scripts/verify_observatory_v1.py",
    "tests/test_fl10_api.py", "tests/test_fl10_evaluation.py",
    "tests/test_fl10_training.py", "tests/test_final_showcase_audit.py",
    "tests/test_observatory_pipeline.py",
    "artifacts/capstone/CAPSTONE_FEDERATION_UX_PROTOCOL_V1.amendment_9_1_1_2.json",
    "artifacts/capstone/CAPSTONE_FRONTEND_PRODUCT_PROTOCOL_V1.amendment_9_6_1_1_2.json",
}


def tracked_files() -> list[str]:
    paths = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    return sorted(path for path in paths if path != str(LOCK_PATH.relative_to(ROOT))
                  and (path in BOUND_EXACT or path.startswith(BOUND_PREFIXES))
                  and (ROOT / path).is_file())


def freeze() -> dict:
    evidence = verify_evidence()
    browser = json.loads((ROOT / "reports/fl10/browser/fl10_browser_smoke.json").read_text())
    tests = json.loads((ROOT / "reports/fl10/local_test_report.json").read_text())
    if not browser.get("passed") or not tests.get("passed"):
        raise ValueError("FL10_GATE_NOT_PASSED")
    predecessor = json.loads((ROOT / PREDECESSOR).read_text())
    repins = sorted(path for path, old in predecessor["bound_files"].items()
                    if (ROOT / path).is_file() and sha(ROOT / path) != old)
    files = tracked_files()
    if len(files) < 100:
        raise ValueError("FL10_BOUND_FILE_INVENTORY_TOO_SMALL")
    lock = {
        "lock_id": "NHM_FL10_001", "status": "PASS",
        "predecessor_id": "NHM_FINAL_SHOWCASE_001",
        "predecessor_commit": evidence["baseline"],
        "predecessor_lock_sha256": evidence["predecessor_lock_sha256"],
        "method_commit": evidence["method_commit"],
        "method_hashes": evidence["method_hashes"],
        "mode_evidence": evidence["modes"],
        "repins_predecessor_files": repins,
        "frontend_files": {path: sha(ROOT / path) for path in frontend_files()},
        "bound_files": {path: sha(ROOT / path) for path in files},
        "test_results": tests,
        "browser_result": {key: browser[key] for key in
                           ("passed", "desktop", "intermediate", "mobile",
                            "reducedMotion", "keyboard", "errors")},
        "claim_boundary": "SYNTHETIC_ENGINEERING_EVENT_EVALUATION_ONLY_NOT_AAMI_SVF_OR_CLINICAL",
        "released_model_changed": False,
        "calibration_applied_to_candidate": False,
        "candidate_promoted_or_deployed": False,
        "hardware_work_performed": False,
        "historical_locks_edited": False,
        "automatically_pushed": False,
        "known_limitations": [
            "Eight logical clients on one machine, not hospital federation",
            "Mode B uses a live-monitored simulated ECG, not a real patient",
            "R3 and R10 both predict every fresh-holdout window positive at fixed 0.5",
            "Nominal uncertainty from only 16 synthetic participant clusters",
            "The new holdout is now exposed; future tuning needs a new protocol and cohort",
            "No candidate calibration, clinical efficacy, promotion or deployment",
            "New FL10 run resumes fail closed from R0 after interruption",
            "FL10 browser smoke used DemoAuth; real Clerk two-user FL10 E2E not claimed",
        ],
    }
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCK_PATH.write_text(json.dumps(lock, sort_keys=True, indent=1) + "\n")
    return lock


if __name__ == "__main__":
    print(json.dumps({"status": freeze()["status"], "lock": str(LOCK_PATH)}))
