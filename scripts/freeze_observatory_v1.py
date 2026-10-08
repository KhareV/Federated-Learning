# ruff: noqa: E501
"""Create the additive NHM_RESEARCH_OBSERVATORY_V1 successor lock (never edits CAPSTONE_UI_V1_9 or any historical lock).

Binds every Observatory file by SHA-256, records the exact delta against the accepted CAPSTONE_UI_V1_9 frontend bytes,
and records the protected-surface audit against the accepted entry commit. The lock states what is and is not delivered."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "artifacts/observatory/NHM_RESEARCH_OBSERVATORY_V1.lock.json"
UI_LOCK = ROOT / "artifacts/capstone/CAPSTONE_UI_V1_9.lock.json"
ENTRY = "dff28f6a7b7bd527def21cb9fd95d682aa60a667"
PATTERNS = ("api/product_app_observatory_v1.py", "api/observatory_model_inspect.py", "product/observatory", "frontend/src/routes/app/observatory", "frontend/src/lib/product/observatory",
            "frontend/src/lib/components/product/observatory", "tests/test_observatory_pipeline.py", "docs/observatory", "reports/observatory")
INTEGRATION = ("frontend/src/routes/app/+page.svelte", "frontend/src/routes/app/models/+page.svelte", "frontend/src/lib/product/api.ts", "frontend/src/lib/product/__tests__/support.ts", "frontend/src/lib/components/product/ProductShell.svelte")
PROTECTED = ("artifacts/capstone", "preprocessing", "federated", "product/federation", "product/monitoring", "product/models", "capstone_persistence", "evaluation",
             "datasets", "simulation", "src", "models", "checkpoints", "api/product_app_v1_1.py", "api/product_app_v1_2.py", "api/product_app_v1_3.py", "api/runtime_v2.py", "deployment", "fusion")
NOT_DELIVERED = [
    "Raw WFDB beat positions on research waveforms (raw MIT-BIH/INCART recordings are absent; nothing synthetic is substituted)",
    "Forward-hook activation maps and per-batch loss (only end-of-epoch local training readouts are recorded)",
    "Inside-gateway tensor capture (replaced by an exact-parity audit against the real runtime without modifying the frozen gateway)",
    "Full traces of historical runs that predate the capture sidecars",
    "Federation-sidecar overhead benchmark",
    "Formal accessibility (WCAG) audit, cross-browser testing, penetration testing, production-security claims",
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tracked(paths: tuple[str, ...]) -> list[str]:
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", *paths], cwd=ROOT, check=True, capture_output=True, text=True).stdout.split("\n")
    return sorted(p for p in out if p and (ROOT / p).is_file() and "__pycache__" not in p)


def scripts_bound() -> list[str]:
    return sorted(str(p.relative_to(ROOT)) for p in (ROOT / "scripts").glob("*observatory*") if p.is_file())


def protected_diff() -> list[str]:
    return [p for p in subprocess.run(["git", "diff", "--name-only", ENTRY, "--", *PROTECTED, ":(exclude)artifacts/capstone/*.amendment_*.json"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split("\n") if p]


def v19_delta() -> list[str]:
    bound = json.loads(UI_LOCK.read_text())["bound_artifacts"]
    return sorted(p for p, digest in bound.items() if (ROOT / p).exists() and sha(ROOT / p) != digest)


def frontend_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "frontend"], cwd=ROOT, check=True, capture_output=True, text=True).stdout.split("\n")
    return sorted({p for p in out if p and (ROOT / p).is_file()})


def freeze() -> dict[str, object]:
    files = sorted(set(tracked(PATTERNS)) | set(INTEGRATION) | set(scripts_bound()) | {"scripts/freeze_observatory_v1.py", "scripts/verify_observatory_v1.py"})
    files = [p for p in files if p != "artifacts/observatory/NHM_RESEARCH_OBSERVATORY_V1.lock.json"]
    delta = v19_delta()
    bound_frontend = {p: sha(ROOT / p) for p in frontend_files()}
    predecessor_bound = json.loads(UI_LOCK.read_text())["bound_artifacts"]
    lock = {
        "lock_id": "NHM_RESEARCH_OBSERVATORY_V1", "status": "FROZEN_IMPLEMENTED_SCOPE_NOT_FULL_MASTER_PROMPT_ACCEPTANCE",
        "predecessor_id": "CAPSTONE_UI_V1_9", "predecessor_sha256": sha(UI_LOCK), "entry_commit": ENTRY,
        "lock_kind": "SUCCESSOR_OF_CAPSTONE_UI_V1_9_AND_OBSERVATORY_BINDING",
        "bound_artifacts": bound_frontend,
        "changed_from_predecessor": sorted(path for path, digest in bound_frontend.items() if predecessor_bound.get(path) != digest),
        "predecessor_frontend_files_changed": delta, "allowed_predecessor_integration_files": list(INTEGRATION),
        "bound_files": {p: sha(ROOT / p) for p in files},
        "protected_surface_diff_against_entry": protected_diff(),
        "claim_boundary": "READ_ONLY_RESEARCH_OBSERVABILITY_OVER_EXISTING_BEHAVIOR_AND_FROZEN_EVIDENCE",
        "scientific_state_semantics_changed": False, "model_calibration_or_fl_math_changed": False, "new_scientific_experiment_run": False,
        "released_model_binding_changed": False, "candidate_promoted_or_deployed": False, "hardware_work_performed": False,
        "full_master_prompt_acceptance": False, "not_delivered": NOT_DELIVERED,
        "evidence": {"connected_clerk_two_user_e2e": "reports/observatory/clerk_e2e/observatory_clerk_e2e.json", "gateway_parity": "reports/observatory/gateway_parity_audit.json",
                     "overhead": "reports/observatory/overhead_benchmark.json", "browser_smoke": "reports/observatory/workstream_a/browser_smoke.json", "checkpoint": "docs/observatory/checkpoint.md"},
    }
    LOCK_PATH.write_text(json.dumps(lock, indent=1, sort_keys=True) + "\n")
    return {"status": "FROZEN", "bound_files": len(files), "predecessor_files_changed": delta, "protected_diff": lock["protected_surface_diff_against_entry"], "lock_sha256": sha(LOCK_PATH)}


if __name__ == "__main__":
    print(json.dumps(freeze(), sort_keys=True))
