# ruff: noqa: E501
"""Create the additive NHM_OBS_DIAG_001 successor lock. The accepted NHM_RESEARCH_OBSERVATORY_V1 lock file is never edited: this lock chains to its exact bytes,
binds every Observatory file by SHA-256 and records which V1-bound files changed. Status states what is and is not delivered."""

from __future__ import annotations

import json
import subprocess

from scripts.freeze_observatory_v1 import (
    ENTRY,
    PROTECTED,
    ROOT,
    UI_LOCK,
    frontend_files,
    protected_diff,
    sha,
    tracked,
)

V1_LOCK = ROOT / "artifacts/observatory/NHM_RESEARCH_OBSERVATORY_V1.lock.json"
LOCK_PATH = ROOT / "artifacts/observatory/NHM_OBS_DIAG_001.lock.json"
V1_COMMIT = "7e91690e21ba4bde71ac5391d0843844ca71ef11"
PATTERNS = ("api/product_app_observatory_v1.py", "api/observatory_model_inspect.py", "api/observatory_batch_capture.py", "api/observatory_activation.py", "product/observatory",
            "frontend/src/routes/app/observatory", "frontend/src/lib/product/observatory", "frontend/src/lib/components/product/observatory", "tests/test_observatory_pipeline.py",
            "tests/test_observatory_diag.py", "docs/observatory", "reports/observatory")
INTEGRATION_V1 = ("frontend/src/routes/app/+page.svelte", "frontend/src/routes/app/models/+page.svelte", "frontend/src/lib/product/api.ts", "frontend/src/lib/product/__tests__/support.ts", "frontend/src/lib/components/product/ProductShell.svelte")
NOT_DELIVERED = [
    "Raw WFDB beat positions on research waveforms (raw recordings absent; nothing synthetic substituted)",
    "Traces of historical runs that predate the capture sidecars; per-batch capture exists only for newly executed runs with the opt-in flag",
    "Firefox and WebKit/Safari browser verification (Firefox not installed; Safari remote automation disabled)",
    "Screen-reader testing with real assistive technology, WCAG 1.4.11 non-text contrast, and any formal accessibility certification",
    "Memory overhead conclusions for the sidecar (peak RSS noise exceeds any effect)",
    "Network or distributed-deployment performance claims",
]


def scripts_bound() -> list[str]:
    out = {str(p.relative_to(ROOT)) for pattern in ("*observatory*", "*obs_diag*") for p in (ROOT / "scripts").glob(pattern) if p.is_file()}
    return sorted(out)


def freeze() -> dict[str, object]:
    v1 = json.loads(V1_LOCK.read_text())
    files = sorted(set(tracked(PATTERNS)) | set(scripts_bound()) | set(INTEGRATION_V1))
    files = [p for p in files if "artifacts/observatory/" not in p]
    bound = {p: sha(ROOT / p) for p in files}
    changed = sorted(p for p, d in bound.items() if v1["bound_files"].get(p) != d)
    front = {p: sha(ROOT / p) for p in frontend_files()}
    v19 = json.loads(UI_LOCK.read_text())["bound_artifacts"]
    lock = {
        "lock_id": "NHM_OBS_DIAG_001", "status": "FROZEN_DELIVERED_CAPABILITIES_ONLY", "predecessor_id": "NHM_RESEARCH_OBSERVATORY_V1", "predecessor_sha256": sha(V1_LOCK),
        "predecessor_commit": V1_COMMIT, "predecessor_status": v1["status"], "ui_baseline_id": "CAPSTONE_UI_V1_9", "ui_baseline_sha256": sha(UI_LOCK), "entry_commit": ENTRY,
        "bound_files": bound, "changed_from_predecessor_files": changed, "bound_artifacts": front,
        "changed_from_predecessor": sorted(p for p, d in front.items() if v19.get(p) != d),
        "protected_surface_diff_against_entry": protected_diff(), "protected_surface_paths": list(PROTECTED),
        "claim_boundary": "READ_ONLY_OBSERVABILITY_OF_EXISTING_BEHAVIOR_NO_SCIENTIFIC_OR_RUNTIME_CHANGE",
        "scientific_state_semantics_changed": False, "model_calibration_or_fl_math_changed": False, "new_scientific_experiment_run": False, "released_model_binding_changed": False,
        "candidate_promoted_or_deployed": False, "hardware_work_performed": False, "held_out_data_accessed": False, "calibration_applied_to_candidate": False,
        "delivered": {"per_batch_fl_capture": "OPT_IN_READ_ONLY_PARITY_VERIFIED", "activation_inspection": "OPT_IN_SERVER_SIDE_SYNTHETIC_WINDOW_PARITY_VERIFIED", "sidecar_overhead_benchmark": "MEASURED_ONE_MACHINE",
                      "browser_accessibility_assessment": "CHROMIUM_ONLY_DOCUMENTED_NOT_CERTIFICATION"},
        "not_delivered": NOT_DELIVERED,
        "evidence": {"fl_parity": "reports/observatory/obs_diag_001/fl_batch_parity.json", "benchmark": "reports/observatory/obs_diag_001/sidecar_benchmark.json", "a11y": "reports/observatory/obs_diag_001/a11y_chrome_stable.json",
                     "browser_runner": "reports/observatory/obs_diag_001/browser_runner.json", "checkpoint": "docs/observatory/obs_diag_001.md"},
    }
    LOCK_PATH.write_text(json.dumps(lock, indent=1, sort_keys=True) + "\n")
    return {"status": "FROZEN", "bound_files": len(bound), "changed_from_v1": len(changed), "lock_sha256": sha(LOCK_PATH), "git_head": subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()}


if __name__ == "__main__":
    print(json.dumps(freeze(), sort_keys=True))
