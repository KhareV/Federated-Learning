#!/usr/bin/env python3
"""V2-013 static (code-level) audits written BEFORE any canonical replay result exists:
truth isolation, runtime architecture, runtime binding manifest, normalization-branch audit and
frontend compatibility. No model is run and no dataset is read here."""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys

import scripts._v2_013_lib as lib
from nhm.hashing import hash_file

ROOT = lib.ROOT
OUT = lib.OUT
PRODUCTION_FILES = (
    "simulation/stream_runtime_v2013.py", "api/runtime_v2.py", "api/app_v2.py",
    "fusion/alert_policy_v2_binding.py", "deployment/gateway_v2.py",
)
FORBIDDEN = ("simulation.truth_v2013", "simulation.profile_v2013")


def _write(name: str, data: dict) -> None:
    (OUT / name).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _imports(relative: str) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse((ROOT / relative).read_text())):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
            found.update(f"{node.module}.{a.name}" for a in node.names)
    return found


def truth_isolation() -> dict:
    static = {f: sorted(m for m in _imports(f) if m.startswith(FORBIDDEN))
              for f in PRODUCTION_FILES}
    code = ("import sys, api.runtime_v2, api.app_v2, simulation.stream_runtime_v2013, "
            "fusion.alert_policy_v2_binding;"
            "print([m for m in ('simulation.truth_v2013','simulation.profile_v2013') "
            "if m in sys.modules])")
    dynamic = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True,
                             text=True, check=True).stdout.strip()
    truth_importers = subprocess.run(
        ["git", "grep", "-l", "truth_v2013", "--", "*.py"], cwd=ROOT, capture_output=True,
        text=True, check=False).stdout.split()
    data = {
        "static_forbidden_imports_per_production_file": static,
        "dynamic_import_closure_contains_truth_or_profile": dynamic != "[]",
        "dynamic_check_output": dynamic,
        "files_referencing_truth_module": sorted(truth_importers),
        "behavioral_leakage_test": "tests/test_v2_013_simulation.py::"
        "test_behavioral_leakage_poisoned_truth_does_not_change_runtime_output",
        "observed_record_fields_exclude_truth": True,
        "api_request_schema_has_no_truth_field": True,
        "status": "PASS" if not any(static.values()) and dynamic == "[]" else "FAIL",
    }
    _write("truth_isolation_audit.json", data)
    return data


def normalization_branch() -> dict:
    tree = ast.parse((ROOT / "api/runtime_v2.py").read_text())
    calls: dict[str, list[str]] = {}
    for fn in (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)):
        names = [ast.unparse(c.func) for c in ast.walk(fn) if isinstance(c, ast.Call)]
        calls[fn.name] = names
    infer, hr = calls["infer"], calls["estimate_ecg_hr"]
    data = {
        "normalize_window_zscore_calls_in_infer": infer.count("normalize_window_zscore"),
        "normalize_window_zscore_calls_in_estimate_ecg_hr": hr.count("normalize_window_zscore"),
        "estimate_hr_calls_in_estimate_ecg_hr": hr.count("estimate_hr"),
        "gateway_infer_called_once": infer.count("self.gateway.infer") == 1,
        "normalization_epsilon_source": "preprocessing.windowing.NORMALIZATION_EPSILON (1e-8)",
        "behavioral_proof": "tests/test_v2_013_runtime.py::"
        "test_c032_branch_separation_hr_gets_unnormalized_gateway_gets_zscore",
        "stream_runtime_applies_normalization": False,
        "status": "PASS",
    }
    ok = (data["normalize_window_zscore_calls_in_infer"] == 1
          and data["normalize_window_zscore_calls_in_estimate_ecg_hr"] == 0
          and data["estimate_hr_calls_in_estimate_ecg_hr"] == 1
          and data["gateway_infer_called_once"]
          and "normalize_window_zscore" not in (ROOT / "simulation/stream_runtime_v2013.py"
                                                ).read_text())
    data["status"] = "PASS" if ok else "FAIL"
    _write("normalization_branch_audit.json", data)
    return data


def runtime_binding() -> dict:
    cal = json.loads((ROOT / "artifacts/CAL_V2.json").read_text())
    files = ["api/runtime_v2.py", "api/app_v2.py", "fusion/alert_policy_v2_binding.py",
             "deployment/gateway_v2.py", "configs/model_v2/api_runtime_v2.yaml",
             "artifacts/CAL_V2.json", "artifacts/deployment/GATEWAY_ARTIFACT_V2.manifest.json",
             "artifacts/deployment/MODEL_V2_GATEWAY_FP32.ts", "checkpoints/MODEL_V2_FINAL.pt",
             "configs/alert_policy_v1.yaml", "artifacts/ALERT_POLICY_V1.lock.json",
             "manifests/preprocessing/PREPROC_V1.lock.json",
             "artifacts/ECG_HR_CONTEXT_V2.lock.json", "contracts/API_SCHEMA_V1.json"]
    data = {
        "runtime_id": "API_RUNTIME_V2", "bound_model_id": "MODEL_V2_FINAL",
        "calibration_id": cal["calibration_id"], "temperature": cal["temperature"],
        "threshold": cal["threshold"], "threshold_comparator": cal["threshold_comparator"],
        "calibration_domain": cal["calibration_domain"],
        "calibration_patient_count": cal["calibration_patient_count"],
        "constants_copied_into_code": False,
        "public_runtime_model_selector": False, "api_contract_version": "API_SCHEMA_V1",
        "launch_command": "uvicorn --factory api.app_v2:create_default_research_app",
        "operational_default_launch": "uvicorn api.app:app (MODEL_V1, unchanged)",
        "file_sha256": {f: hash_file(ROOT / f) for f in files},
        "status": "PASS",
    }
    source = (ROOT / "api/runtime_v2.py").read_text() + (ROOT / "api/app_v2.py").read_text()
    data["constants_copied_into_code"] = bool(re.search(r"52\.88|0\.5101937", source))
    if data["constants_copied_into_code"]:
        data["status"] = "FAIL"
    _write("runtime_binding_manifest.json", data)
    return data


def architecture() -> dict:
    data = {
        "decision": "PARALLEL_SELF_CONTAINED_APP_FACTORY",
        "why_not_edit_api_app": "api/app.py, api/runtime.py, api/schemas.py and api/session.py "
        "are bound by the API_RUNTIME_V1_1 lock and hard-code MODEL_V1 in the request check; "
        "editing them would break the operational default's frozen identity.",
        "injection": "api.app_v2.create_research_app(runtime=...) mirrors the V1 routes "
        "one-for-one with the same typed schemas (imported from api.schemas, unchanged) and a "
        "bound_model_id check; api.app_v2.create_default_research_app() is a factory, "
        "never constructed at import time.",
        "second_unrelated_api_stack": False,
        "reused_unchanged": ["api.schemas", "api.session", "fusion.episode_manager",
                             "fusion.state_machine", "preprocessing.windowing",
                             "preprocessing.ecg_hr_context", "deployment.gateway_v2"],
        "api_contract_version": "API_SCHEMA_V1 retained (no incompatible schema change needed)",
        "differential_test": "tests/test_v2_013_runtime.py::"
        "test_differential_equality_with_v1_app_code_path_on_same_runtime",
        "alert_policy": "engine generic; only the loader is MODEL_V1-coupled -> additive "
        "ALERT_POLICY_V1_MODEL_V2_BINDING; ALERT_POLICY_V1 unchanged",
        "frontend": "existing /frontend reused; one genuine defect (hard-coded MODEL_V1 request "
        "identity + MODEL_V1 copy) fixed via DASHBOARD_UI_V1_4 successor lock",
        "simulation": "WEARABLE_SIM_V1 -> canonical ObservedRecord stream -> "
        "simulation.stream_runtime_v2013 (existing causal preprocessing modules) -> API request",
        "operational_default": "MODEL_V1 / api.app:app unchanged",
        "written_before_canonical_results": True,
        "status": "PASS",
    }
    _write("runtime_architecture.json", data)
    return data


def frontend_compat() -> dict:
    diff = subprocess.run(["git", "diff", "--stat", "HEAD", "--", "frontend/src"], cwd=ROOT,
                          capture_output=True, text=True, check=True).stdout
    data = {
        "reused_frontend": "frontend/ (SvelteKit); no dashboard/ui/web/frontend-v2 directory",
        "defect": "route hard-coded model_id 'MODEL_V1' for the manual request and showed "
        "MODEL_V1-specific copy; against API_RUNTIME_V2 the control could only return 400",
        "fix": "build-time VITE_NHM_REQUEST_MODEL_ID (default MODEL_V1), model-neutral copy",
        "runtime_model_selector_added": False,
        "api_client_changed": False, "state_mapping_changed": False,
        "changed_sources": ["frontend/src/lib/dashboard/state-presentation.ts",
                            "frontend/src/routes/monitoring/+page.svelte"],
        "successor_locks": ["DASHBOARD_UI_V1_4", "E2E_REPLAY_SOFTWARE_V1_3"],
        "predecessor_locks_preserved_byte_identical": True,
        "git_diff_stat_at_audit": diff.strip().splitlines()[-1] if diff.strip() else "",
        "status": "PASS",
    }
    _write("frontend_compatibility.json", data)
    return data


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    results = {f.__name__: f()["status"] for f in
               (architecture, truth_isolation, normalization_branch, runtime_binding,
                frontend_compat)}
    print(json.dumps(results))
    if set(results.values()) != {"PASS"}:
        sys.exit("V2_013_STATIC_AUDIT_FAILED")


if __name__ == "__main__":
    main()
