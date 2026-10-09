# ruff: noqa: E501
"""Create the additive NHM_UNIFIED_LIVE_FEDERATION_STUDIO_001 successor lock only after every local gate has passed.

Never edits a historical lock. Run after the implementation commit; commit the generated lock separately, then verify it against the final worktree
(`python -m scripts.verify_unified_studio_001 --lock`)."""

from __future__ import annotations

import json
import subprocess

from scripts.freeze_observatory_v1 import frontend_files
from scripts.verify_unified_studio_001 import EVIDENCE, FL10_COMMIT, LOCK_PATH, PREDECESSOR, ROOT, sha, verify_evidence

BOUND_PREFIXES = ("studio/", "docs/unified_live_fl/", "reports/unified_live_fl/", "frontend/src/")
BOUND_EXACT = {
    "api/observatory_studio.py", "api/observatory_fl10.py", "api/product_app_observatory_v1.py", "fl10/runner.py",
    "scripts/successor_chain.py", "scripts/studio_successor_compat.py", "scripts/fl10_successor_compat.py", "scripts/capstone_ui_v1_8_successor.py", "scripts/reconcile_ui_lock_chain.py",
    "scripts/verify_fl10_001.py", "scripts/verify_unified_studio_001.py", "scripts/freeze_unified_studio_001.py", "scripts/run_studio_local_gates.py",
    "scripts/studio_cdp.mjs", "scripts/studio_baseline_capture.mjs", "scripts/studio_browser_verify.mjs", "scripts/run_studio_browser.py", "scripts/studio_collect_evidence.py",
    "tests/test_studio_specs.py", "tests/test_studio_isolation.py", "tests/test_studio_observer.py", "tests/test_studio_api.py", "tests/test_studio_successor.py", "tests/test_successor_chain_governance.py",
}


def tracked_files() -> list[str]:
    paths = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.splitlines()
    return sorted(p for p in paths if p != str(LOCK_PATH.relative_to(ROOT)) and (p in BOUND_EXACT or p.startswith(BOUND_PREFIXES)) and (ROOT / p).is_file())


def freeze() -> dict:
    evidence = verify_evidence()
    browser = json.loads((ROOT / EVIDENCE / "browser/studio_browser_verification.json").read_text())
    tests = json.loads((ROOT / EVIDENCE / "local_test_report.json").read_text())
    launcher = json.loads((ROOT / EVIDENCE / "launcher_preflight.json").read_text())
    if not browser["passed"] or not tests["passed"] or not launcher["passed"]:
        raise ValueError("STUDIO_GATE_NOT_PASSED")
    predecessor = json.loads((ROOT / PREDECESSOR).read_text())
    repins = sorted(path for path, old in predecessor["bound_files"].items() if (ROOT / path).is_file() and sha(ROOT / path) != old)
    files = tracked_files()
    if len(files) < 100:
        raise ValueError("STUDIO_BOUND_FILE_INVENTORY_TOO_SMALL")
    lock = {
        "lock_id": "NHM_UNIFIED_LIVE_FEDERATION_STUDIO_001", "status": "PASS",
        "predecessor_id": "NHM_FL10_001", "predecessor_commit": FL10_COMMIT, "predecessor_lock_sha256": evidence["predecessor_lock_sha256"],
        "predecessor_chain": ["CAPSTONE_UI_V1", "CAPSTONE_UI_V1_1", "CAPSTONE_UI_V1_2", "CAPSTONE_UI_V1_3", "CAPSTONE_UI_V1_4", "CAPSTONE_UI_V1_5", "CAPSTONE_UI_V1_6", "CAPSTONE_UI_V1_7", "CAPSTONE_UI_V1_8", "CAPSTONE_UI_V1_9",
                              "NHM_RESEARCH_OBSERVATORY_V1", "NHM_OBS_DIAG_001", "NHM_FINAL_SHOWCASE_001", "NHM_FL10_001"],
        "repins_predecessor_files": repins,
        "frontend_files": {path: sha(ROOT / path) for path in frontend_files()},
        "bound_files": {path: sha(ROOT / path) for path in files},
        "live_runs": evidence["live_runs"],
        "evidence": {"tests_sha256": evidence["tests_sha256"], "browser_report_sha256": sha(ROOT / EVIDENCE / "browser/studio_browser_verification.json"), "launcher_preflight_sha256": sha(ROOT / EVIDENCE / "launcher_preflight.json")},
        "test_results": tests, "browser_result": {"passed": browser["passed"], "total": browser["total"], "failed": browser["failed"]}, "launcher_preflight": launcher,
        "claim_boundary": "SYNTHETIC_ENGINEERING_EVENT_EVALUATION_ONLY_NOT_AAMI_SVF_OR_CLINICAL",
        "evaluation_cohort_use": "REUSED SYNTHETIC DIAGNOSTIC EVALUATION — NOT A NEW UNTOUCHED FINAL TEST",
        "released_model_changed": False, "calibration_applied_to_candidate": False, "candidate_promoted_or_deployed": False, "hardware_work_performed": False,
        "historical_locks_edited": False, "automatically_pushed": False, "frozen_scientific_evidence_edited": False,
        "connected_clerk_two_user_e2e": "NOT EXECUTED",
        "pre_existing_defects_corrected": [
            {"id": "DEMO_LAUNCHER_PREFLIGHT_FAILED_AT_06bd9a0", "description": "`python -m scripts.run_nhm --demo` failed preflight (CAPSTONE_UI_V1_TAMPER / UNBOUND_OR_MISSING_FRONTEND_FILE) because the shared resolver stopped at NHM_FINAL_SHOWCASE_001 and never resolved the additive NHM_FL10_001 successor.",
             "correction": "scripts/successor_chain.py (exact-identity, append-only chain registry) + scripts/capstone_ui_v1_8_successor.py delegating to it; no historical lock, amendment or accepted verifier was edited.", "document": "docs/unified_live_fl/governance_repair.md"},
            {"id": "TRAINING_PERTURBED_BY_CONCURRENT_SCORING", "description": "Scoring a checkpoint on another thread with final_showcase.evaluate.logits_for builds a model, which draws from torch's process-wide RNG that the frozen trainer also uses (Dropout), silently changing the committed state.",
             "correction": "studio/isolated_eval.py builds one template model before any run and deep-copies it (no random draws); proved by tests/test_studio_isolation.py including a control.", "document": "docs/unified_live_fl/evaluation_policy.md"},
            {"id": "FL10_ONE_RUN_GUARD_PATH_NEVER_MATCHED", "description": "api/observatory_fl10.py guarded POST /product/v1/observatory/federation/runs, a path that does not exist, so an active FL10 job never blocked the product federation route.",
             "correction": "the Studio guard is registered on the real POST /product/v1/federation/runs path (409 while a Studio 10-round run executes); the old FL10 route also refuses while a Studio run is active.", "document": "api/observatory_studio.py"},
            {"id": "FL10_PROVENANCE_EXPORT_FORMAT_NOT_SERVED", "description": "The FL10 export route served only svg/png/csv/json/md; the provenance format the UI requests had no media type.",
             "correction": "the Studio export route serves `provenance` (JSON) for every run and recorded evidence.", "document": "api/observatory_studio.py"},
        ],
        "known_limitations": [
            "Eight logical clients on one machine, not a hospital federation",
            "Source mode B uses a live-monitored simulated ECG stream, not real patient physiology",
            "The 16-participant diagnostic holdout is reused (already exposed): live scores are diagnostic, not a new untouched final test",
            "Nominal uncertainty from only 16 synthetic participant clusters; no significance claim",
            "10-round runs support FedAvg with plain aggregation only; FedProx and SecAgg shadow stay 3-round features",
            "An interrupted 10-round run fails closed and restarts from R0; unfinished evaluations are marked failed, never re-scored silently",
            "Runs started before the evaluation observer existed carry no per-round metrics ('RUN_PREDATES_LIVE_EVALUATION')",
            "Browser verification used DemoAuth; connected Clerk two-user E2E was NOT EXECUTED (two Clerk TEST user credentials unavailable). Two-identity isolation is covered by API/WebSocket tests; the owner-star presentation by component tests",
            "The offline --demo faculty launcher serves the older product app without Observatory/Studio routes (as before): there the 10-round option is disabled with an explanation",
            "A pre-existing monitoring race flake in the backend suite (named in the master prompt) is reported separately and not modified",
        ],
    }
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCK_PATH.write_text(json.dumps(lock, sort_keys=True, indent=1) + "\n")
    return lock


if __name__ == "__main__":
    print(json.dumps({"status": freeze()["status"], "lock": str(LOCK_PATH)}))
