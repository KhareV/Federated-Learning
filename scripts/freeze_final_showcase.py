# ruff: noqa: E501
"""Create the additive NHM_FINAL_SHOWCASE_001 lock. Binds only DELIVERED capabilities; chains to the exact bytes of NHM_OBS_DIAG_001 (never edited here).
  python -m scripts.freeze_final_showcase"""

from __future__ import annotations

import json
import subprocess

from scripts.freeze_observatory_v1 import (
    ROOT,
    UI_LOCK,
    frontend_files,
    protected_diff,
    sha,
    tracked,
)
from scripts.verify_final_showcase import ENTRY, METHOD_COMMIT

OBS_DIAG_LOCK = ROOT / "artifacts/observatory/NHM_OBS_DIAG_001.lock.json"
LOCK_PATH = ROOT / "artifacts/final_showcase/NHM_FINAL_SHOWCASE_001.lock.json"
OBS_DIAG_COMMIT = "aa36f53b26834f88e6ac41482e7190f1fa2086d8"   # the pushed origin/main tip whose NHM_OBS_DIAG_001 bytes this lock chains to
PATTERNS = ("final_showcase", "configs/final_showcase", "reports/final_showcase", "docs/final_showcase", "tests/test_final_showcase_eval.py", "tests/test_final_showcase_research.py", "tests/test_final_showcase_live_link.py",
            "api/observatory_showcase.py", "api/product_app_observatory_v1.py", "frontend/src/routes/app/observatory/outcomes", "frontend/src/routes/app/observatory/storyboard",
            "frontend/src/lib/product/observatory/showcase.ts", "frontend/src/lib/product/observatory/__tests__/showcase.test.ts", "frontend/src/lib/product/api.ts", "frontend/src/lib/product/__tests__/support.ts")
SCRIPTS = ("scripts/freeze_synth_fl_eval_protocol.py", "scripts/run_synth_fl_eval.py", "scripts/run_live_link.py", "scripts/build_final_showcase_docs.py", "scripts/final_showcase_smoke.mjs",
           "scripts/run_final_showcase_browsers.py", "scripts/verify_final_showcase.py", "scripts/freeze_final_showcase.py")
NOT_DELIVERED = [
    "Firefox and WebKit/Safari verification (Firefox not installed; Safari remote automation disabled); Chromium builds only",
    "Any clinical, AAMI-SVF or device validation of the synthetic sandbox candidate; the synthetic holdout is simulated, 8 clusters, nominal intervals only",
    "Paired statistical comparison between historical centralized and federated models (no such artifact exists; point differences only)",
    "A persisted product-history session for the live-monitored SITE_00 (hosted in memory by the Observatory; the frozen scenario registry rejects unknown persisted scenario ids on restart)",
    "Verified bibliography: all citations are marked REFERENCE_REQUIRED",
    "Hardware work, model replacement, retraining, threshold tuning, promotion or deployment (none authorised, none performed)",
    "Full master-prompt acceptance of NHM_RESEARCH_OBSERVATORY_V1 (unchanged status)",
]


def freeze() -> dict[str, object]:
    diag = json.loads(OBS_DIAG_LOCK.read_text())
    repins = sorted(p for p, d in diag["bound_files"].items() if sha(ROOT / p) != d)      # files NHM_OBS_DIAG_001 binds whose bytes this successor changed
    files = sorted(set(tracked(PATTERNS)) | set(SCRIPTS) | set(repins))
    bound = {p: sha(ROOT / p) for p in files if (ROOT / p).is_file()}
    front = {p: sha(ROOT / p) for p in frontend_files()}
    v19 = json.loads(UI_LOCK.read_text())["bound_artifacts"]
    lock = {
        "lock_id": "NHM_FINAL_SHOWCASE_001", "status": "FROZEN_DELIVERED_CAPABILITIES_ONLY", "predecessor_id": "NHM_OBS_DIAG_001", "predecessor_sha256": sha(OBS_DIAG_LOCK), "predecessor_commit": OBS_DIAG_COMMIT,
        "predecessor_status": diag["status"], "predecessor_lock_edited": False,
        "predecessor_governance_note": "NHM_OBS_DIAG_001 bytes were re-frozen in place at 7debd49 and aa36f53 (disclosed in those pushed commits). This lock chains to the aa36f53 bytes and repins later changes additively; the predecessor file is not edited here.",
        "repins_predecessor_files": repins, "bound_artifacts": front, "changed_from_predecessor": sorted(p for p, d in front.items() if v19.get(p) != d),
        "ui_baseline_id": "CAPSTONE_UI_V1_9", "ui_baseline_sha256": sha(UI_LOCK),
        "entry_commit": ENTRY, "stated_starting_reference": "7d8a90a (two later pushed commits of the same line of work precede the actual start; see docs/final_showcase/implementation_map.md)",
        "synthetic_evaluation_method_freeze_commit": METHOD_COMMIT, "protocol_sha256": sha(ROOT / "configs/final_showcase/synth_fl_eval_protocol_v1.json"), "holdout_manifest_sha256": sha(ROOT / "configs/final_showcase/synth_fl_eval_holdout_manifest_v1.json"),
        "bound_files": bound, "protected_surface_diff_against_entry": protected_diff(),
        "canonical_candidate_digest": "3f0b7762ae7e05f21eb1709521404ed4d7968cae34f89e1797a0cbabd47c70e4",
        "claim_boundary": "ADDITIVE_PRESENTATION_AND_SYNTHETIC_ENGINEERING_EVALUATION_NO_SCIENTIFIC_RUNTIME_OR_LOCK_CHANGE",
        "scientific_state_semantics_changed": False, "model_calibration_or_fl_math_changed": False, "frozen_evidence_edited": False, "historical_locks_edited": False, "new_scientific_experiment_run": False,
        "released_model_binding_changed": False, "candidate_promoted_or_deployed": False, "hardware_work_performed": False, "held_out_data_accessed": False, "calibration_applied_to_synthetic_candidates": False,
        "automatically_pushed": False,
        "delivered": {"A_live_monitored_site00": "OPT_IN_REAL_MONITORING_SESSION_REAL_INFERENCE_PARITY_OBSERVED", "B_synthetic_independent_evaluation": "TWO_COMMIT_METHOD_FREEZE_RESULT_SEQUENCE_ROUNDS_0_TO_3",
                      "C_scientific_outcomes_dashboard": "FROZEN_EVIDENCE_READ_ONLY_DESCRIPTIVE", "D_figures_tables_exports": "SIX_FIGURES_FOUR_TABLES_HASHED", "E_storyboard": "ONE_SCREEN_CHROMIUM_VERIFIED",
                      "F_demo_runbook": "WITH_RECORDED_VERIFIED_RUN_FALLBACK", "G_manuscript_material": "DRAFT_WITH_REFERENCE_REQUIRED_MARKERS"},
        "not_delivered": NOT_DELIVERED,
        "evidence": {"gates": "reports/final_showcase/gates.json", "synthetic_results": "reports/final_showcase/synth_fl_eval/synth_fl_eval_results.json", "live_link": "reports/final_showcase/live_link/live_link_result.json",
                     "exports": "reports/final_showcase/publication/export_manifest.json", "browser": "reports/final_showcase/browser"},
    }
    LOCK_PATH.write_text(json.dumps(lock, indent=1, sort_keys=True) + "\n")
    return {"status": "FROZEN", "bound_files": len(bound), "lock_sha256": sha(LOCK_PATH), "git_head": subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()}


if __name__ == "__main__":
    print(json.dumps(freeze(), sort_keys=True))
