# ruff: noqa: E501
"""Build artifacts/capstone/CAPSTONE_RELEASE_MANIFEST_V1.json (deterministic; excludes its own future commit SHA)."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.capstone_release_lib import MANIFEST_PATH, sha256_file

ROOT = Path(__file__).resolve().parents[1]
POLICY = json.loads((ROOT / "configs/capstone/cap_011_release_policy_v1.json").read_text())
KEY_ARTIFACTS = (
    "checkpoints/MODEL_V2_FINAL.pt", "checkpoints/MODEL_V2_FINAL.manifest.json", "artifacts/CAL_V2.json", "artifacts/deployment/GATEWAY_ARTIFACT_V2.manifest.json", "artifacts/deployment/MODEL_V2_GATEWAY_FP32.ts",
    "artifacts/DEFAULT_RUNTIME_BINDING_V2.lock.json", "artifacts/ROLLBACK_RUNTIME_BINDING_V1.lock.json", "artifacts/SOFTWARE_SYSTEM_V2.lock.json", "artifacts/FEDPROX_MU_V2.lock.json",
    "configs/model_v2/fl_init_v2.yaml", "artifacts/V2_FL_WEARABLE_SYSTEM_PROTOCOL_V1.lock.json", "configs/model_v2/wearable_sim_fl_secagg_compat_v1.yaml", "artifacts/MODEL_V2_COMPLETE_REPRO_V1.lock.json",
    "artifacts/SYSTEM_V2_RELEASE_DECISION_V1.lock.json", "api/product_app_v1_3.py", "artifacts/capstone/CAPSTONE_UI_V1_2.lock.json", "artifacts/capstone/CAPSTONE_RESEARCH_EVIDENCE_CATALOG_V1.json",
    "artifacts/capstone/CAPSTONE_RESEARCH_EVIDENCE_CATALOG_V1.lock.json", "artifacts/capstone/CAPSTONE_FACULTY_DEMO_PROTOCOL_V1.lock.json", "artifacts/capstone/CAPSTONE_FACULTY_DEMO_PROTOCOL_V1.amendment_1.json",
    "configs/capstone/cap_010_full_demo_binding_v1.json", "scripts/run_capstone_faculty_demo.py", "scripts/capstone_demo_preflight.py", "scripts/capstone_demo_workspace.py",
    "scripts/run_capstone_full_demo_e2e.py", "docs/capstone/FACULTY_DEMO_RUNBOOK_V1.md",
)
DEPENDENCY_LOCKS = ("requirements-dev.lock", "requirements-capstone-auth.lock", "pyproject.toml", "frontend/package.json", "frontend/package-lock.json", "frontend/clerk-sdk/package.json", "frontend/clerk-sdk/package-lock.json")
COMPONENTS = ("CAPSTONE_RELEASE_PROTOCOL_V1", "CAPSTONE_RELEASE_POLICY_V1", "CAPSTONE_RELEASE_MANIFEST_V1", "CAPSTONE_RELEASE_VERIFIER_V1", "CAPSTONE_CLEAN_CLONE_PROTOCOL_V1", "CAPSTONE_RELEASE_GUIDE_V1", "CAPSTONE_RELEASE_V1")


def build() -> dict:
    return {
        "release_id": "CAPSTONE_RELEASE_V1", "manifest_id": "CAPSTONE_RELEASE_MANIFEST_V1", "status": "FROZEN_PRE_RELEASE_MANIFEST",
        "release_scope": "ONE-LAPTOP CAPSTONE SOFTWARE / FACULTY-DEMO RELEASE (not the historical RELEASE_V1 / T036 / G22 / F15 lineage)",
        "release_vehicle": "the exact Git repository state at RELEASE_TARGET_SHA (recorded in the release decision evidence; this manifest cannot contain its own commit SHA)",
        "components": list(COMPONENTS), "key_artifacts": {p: sha256_file(ROOT / p) for p in KEY_ARTIFACTS}, "dependency_locks": {p: sha256_file(ROOT / p) for p in DEPENDENCY_LOCKS},
        "launch_command": ".venv/bin/python -m scripts.run_capstone_faculty_demo --acknowledge-demo-auth --build --prewarm-federation --workspace <WORKSPACE_OUTSIDE_REPO>",
        "service_identities": {"inference": {"command": "run_nhm_default --profile default", "port": 8001, "identity": "SOFTWARE_SYSTEM_V2 default binding"},
                               "product": {"command": "run_capstone_product_v1_3", "port": 8002, "identity": "CAPSTONE_PRODUCT_API_V1_3 / PRODUCT_API_V2"}, "frontend": {"command": "npm run preview after npm run build", "port": 4173, "identity": "CAPSTONE_UI_V1_2"}},
        "released_monitoring": {"software_system": "SOFTWARE_SYSTEM_V2", "default_model": "MODEL_V2_FINAL", "calibration": "CAL_V2", "gateway": "GATEWAY_ARTIFACT_V2", "binding": "DEFAULT_RUNTIME_BINDING_V2",
                                "alert_policy": "ALERT_POLICY_V1_MODEL_V2_BINDING", "api_schema": "API_SCHEMA_V1", "candidate_used_for_monitoring": False, "candidate_inference": False},
        "candidate": {"id_in_demo_workspace": "CAPSTONE_FL_CANDIDATE_0001", "governance": "ACCEPTED_TO_SANDBOX", "sandbox": "IN_SANDBOX", "production_deployed": False},
        "hardware": {"hardware_mode": "SIMULATED_ONLY", "physical_hardware_available": False, "future_physical_hardware": "VERIFICATION_REQUIRED"},
        "required_environment_family": {"python": "3.11.x (pyproject: >=3.11,<3.12)", "node_npm": "Node.js with npm; tested versions recorded in the clean-clone environment inventory", "browser": "Google Chrome (browser verification only)",
                                         "tested_platform": "recorded per clone in the environment inventory (expected: macOS/Darwin arm64); no other OS is claimed"},
        "release_claim": POLICY["release_claim"], "release_claim_excludes": POLICY["release_claim_excludes"], "clean_clone_claim": POLICY["clean_clone_claim"],
        "installation_claim": POLICY["installation_vs_runtime"]["installation"], "runtime_offline_claim": POLICY["installation_vs_runtime"]["runtime"], "raw_data_boundary": POLICY["raw_data_boundary"],
        "scientific_boundary": "frozen scientific artifacts and evidence are tracked; no raw-data retraining/evaluation is claimed from a clean clone",
        "decision_separation": POLICY["decision_separation"], "limitations": [x["text"] for x in POLICY["limitations"]], "manual_override_allowed": False,
        "no_security_overclaim": POLICY["no_security_overclaim"], "ci": "not queried, not triggered",
    }


if __name__ == "__main__":
    (ROOT / MANIFEST_PATH).write_text(json.dumps(build(), indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"key_artifacts": len(KEY_ARTIFACTS), "dependency_locks": len(DEPENDENCY_LOCKS)}))
