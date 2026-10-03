#!/usr/bin/env python3
"""V2-013 Sections 21/22: (A) the normal operational start path still resolves to MODEL_V1 /
GATEWAY_ARTIFACT_V1 / CAL_V1 and rejects V2 requests; (B) V1 and V2 runtimes do not influence one
another -- concurrent fresh processes run the same scripted sequence alone and interleaved, and
the per-process semantic digests are identical; in-process co-existence leaves both bindings
intact; no module-level mutable binding exists in the V2 modules. Synthetic fixtures only."""

from __future__ import annotations

import ast
import json
import subprocess

import httpx

import scripts._v2_013_lib as lib

ROOT = lib.ROOT
OUT = lib.OUT
ENTRY = "40e127308b50bb4d5943826639d467203b9b4b29"
MS = 1_000_000
SEQUENCE = [0, 6, 6, 0, 7, 7, 1, 2]  # synthetic corpus indices (includes the two 'above' windows)
V2_MODULES = ["api/runtime_v2.py", "api/app_v2.py", "deployment/gateway_v2.py",
              "fusion/alert_policy_v2_binding.py"]


def _events(model_id: str) -> list[dict]:
    windows = lib.synthetic_api_windows(300)
    return [{"sequence_index": n, "window_id": f"SYN_{idx}", "timestamp_us": (10 + 5 * n) * MS,
             "ecg_quality": "VALID", "model_id": model_id, "ppg_context": lib.PPG_CONTEXT,
             "ecg": {"samples": windows[idx].tolist()}} for n, idx in enumerate(SEQUENCE)]


def _run(base: str, session: str, events: list[dict]) -> list[dict]:
    return lib.direct_replay(base, session, events)


def v1_default_regression() -> dict:
    cal_v1 = json.loads((ROOT / "artifacts/CAL_V1.json").read_text())
    with lib.launch_api("v1") as (base, _pid), httpx.Client() as client:
        window = lib.synthetic_api_windows(10)[9]
        status, body = lib.post(client, base, lib.request_body(
            "V2-013-V1-DEFAULT", 10 * MS, window.tolist(), quality="VALID",
            model_id=lib.V1_MODEL_ID))
        s2, b2 = lib.post(client, base, lib.request_body(
            "V2-013-V1-DEFAULT", 15 * MS, window.tolist(), quality="VALID",
            model_id=lib.V2_MODEL_ID))
    diff = subprocess.run(
        ["git", "diff", "--name-only", ENTRY, "--", "api/app.py", "api/runtime.py",
         "api/schemas.py", "api/session.py", "fusion", "deployment/runtime.py",
         "deployment/export.py", "deployment/benchmark.py", "artifacts/API_RUNTIME_V1_1.lock.json",
         "artifacts/GATEWAY_ARTIFACT_V1.lock.json", "artifacts/CAL_V1.json",
         "artifacts/deployment/MODEL_V1_GATEWAY_FP32.ts", "checkpoints/MODEL_V1.pt",
         "contracts"], cwd=ROOT, capture_output=True, text=True, check=False).stdout.split()
    import api.app as production

    runtime = production.app.state.runtime
    source = (ROOT / "api/app.py").read_text()
    data = {
        "normal_start_command": "uvicorn api.app:app (unchanged production entry point)",
        "status_for_model_v1_request": status,
        "response_model_id": body.get("model_id"),
        "response_calibration_id": body.get("calibration_id"),
        "response_threshold_equals_cal_v1": body.get("threshold") == cal_v1["threshold"],
        "response_calibration_domain": body.get("calibration_domain"),
        "response_alert_policy_id": body.get("alert_policy_id"),
        "production_runtime_class": type(runtime).__name__,
        "production_gateway_artifact_path": str(runtime.gateway.artifact_path.relative_to(ROOT)),
        "production_policy_model_id": runtime.policy.model_id,
        "production_policy_calibration_id": runtime.policy.calibration_id,
        "v2_request_to_production_status": s2,
        "v2_request_to_production_error": b2.get("error_type"),
        "production_still_hard_binds_model_v1": 'payload.model_id != "MODEL_V1"' in source,
        "v1_files_changed_since_entry": diff,
        "resolves_to": "MODEL_V1/GATEWAY_ARTIFACT_V1/CAL_V1" if (
            body.get("model_id") == "MODEL_V1" and body.get("calibration_id") == "CAL_V1"
            and runtime.gateway.artifact_path.name == "MODEL_V1_GATEWAY_FP32.ts") else "UNEXPECTED",
        "scientific_evaluation_rerun": False,
    }
    data["status"] = "PASS" if (
        status == 200 and body.get("model_id") == "MODEL_V1"
        and body.get("calibration_id") == "CAL_V1"
        and data["response_threshold_equals_cal_v1"] and s2 == 400
        and b2.get("error_type") == "UNSUPPORTED_MODEL_ID" and not diff
        and data["resolves_to"] != "UNEXPECTED" and data["production_still_hard_binds_model_v1"]
    ) else "FAIL"
    (OUT / "v1_default_regression.json").write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return data


def _module_level_mutables(rel: str) -> list[str]:
    tree = ast.parse((ROOT / rel).read_text())
    bad = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(
                node.value, ast.Dict | ast.List | ast.Set | ast.Call):
            for target in node.targets:
                if (isinstance(target, ast.Name) and not target.id.isupper()
                        and not target.id.startswith("__")):
                    bad.append(f"{rel}:{target.id}")
        if isinstance(node, ast.Global):
            bad.append(f"{rel}:global")
    for node in ast.walk(tree):
        if isinstance(node, ast.Global):
            bad.append(f"{rel}:global-statement")
    return bad


def isolation() -> dict:
    cal_v1 = json.loads((ROOT / "artifacts/CAL_V1.json").read_text())
    cal_v2 = json.loads((ROOT / "artifacts/CAL_V2.json").read_text())
    v1_events, v2_events = _events(lib.V1_MODEL_ID), _events(lib.V2_MODEL_ID)
    shared_session = "V2-013-ISOLATION-SHARED-SESSION-ID"

    with lib.launch_api("v1") as (b1, _p1):
        alone_v1 = _run(b1, shared_session, v1_events)
    with lib.launch_api("v2") as (b2, _p2):
        alone_v2 = _run(b2, shared_session, v2_events)

    with lib.launch_api("v1") as (b1, p1), lib.launch_api("v2") as (b2, p2), httpx.Client() as c:
        inter_v1, inter_v2 = [], []
        for e1, e2 in zip(v1_events, v2_events, strict=True):  # interleaved request by request
            s1, r1 = lib.post(c, b1, lib.request_body(
                shared_session + "-I", e1["timestamp_us"], e1["ecg"]["samples"], quality="VALID",
                model_id=e1["model_id"], ppg_context=e1["ppg_context"]))
            s2, r2 = lib.post(c, b2, lib.request_body(
                shared_session + "-I", e2["timestamp_us"], e2["ecg"]["samples"], quality="VALID",
                model_id=e2["model_id"], ppg_context=e2["ppg_context"]))
            inter_v1.append(lib.semantic_row(e1, s1, r1))
            inter_v2.append(lib.semantic_row(e2, s2, r2))
        distinct_pids = p1 != p2

    d = lib.canonical_digest
    cross = {
        "v1_alone_equals_v1_interleaved": d(alone_v1)["sha256"] == d(inter_v1)["sha256"],
        "v2_alone_equals_v2_interleaved": d(alone_v2)["sha256"] == d(inter_v2)["sha256"],
        "v1_identities": {"model_id": {r["response"]["model_id"] for r in inter_v1},
                          "calibration_id": {r["response"]["calibration_id"] for r in inter_v1},
                          "threshold": {r["response"]["threshold"] for r in inter_v1}},
        "v2_identities": {"model_id": {r["response"]["model_id"] for r in inter_v2},
                          "calibration_id": {r["response"]["calibration_id"] for r in inter_v2},
                          "threshold": {r["response"]["threshold"] for r in inter_v2}},
        "episode_state_independent": [r["response"]["monitoring_state"] for r in inter_v1]
        != [r["response"]["monitoring_state"] for r in inter_v2]
        or d(inter_v1)["sha256"] != d(inter_v2)["sha256"],
    }
    cross_ok = (
        cross["v1_alone_equals_v1_interleaved"] and cross["v2_alone_equals_v2_interleaved"]
        and cross["v1_identities"] == {"model_id": {"MODEL_V1"}, "calibration_id": {"CAL_V1"},
                                       "threshold": {cal_v1["threshold"]}}
        and cross["v2_identities"] == {"model_id": {"MODEL_V2_FINAL"},
                                       "calibration_id": {"CAL_V2"},
                                       "threshold": {cal_v2["threshold"]}}
        and distinct_pids)

    # in-process co-existence
    from fastapi.testclient import TestClient

    import api.app as production
    from api.app_v2 import create_research_app
    from api.runtime import ProductionRuntime
    from api.runtime_v2 import ResearchRuntimeV2

    v1_runtime = ProductionRuntime()
    v2_runtime = ResearchRuntimeV2(verify="manifest")
    v2_client = TestClient(create_research_app(runtime=v2_runtime))
    v1_app = production.create_app(runtime=v1_runtime)
    v1_client = TestClient(v1_app)
    for e in v2_events:
        v2_client.post(lib.ROUTE, json=lib.request_body(
            "SHARED", e["timestamp_us"], e["ecg"]["samples"], quality="VALID",
            model_id=e["model_id"], ppg_context=e["ppg_context"]))
    fresh_v1 = v1_client.post(lib.ROUTE, json=lib.request_body(
        "SHARED", 10 * MS, v1_events[0]["ecg"]["samples"], quality="VALID",
        model_id=lib.V1_MODEL_ID, ppg_context=lib.PPG_CONTEXT)).json()
    in_process = {
        "gateway_artifacts_distinct": v1_runtime.gateway.artifact_path
        != v2_runtime.gateway.artifact_path,
        "gateway_artifact_ids": [v1_runtime.gateway.artifact_path.name,
                                 v2_runtime.gateway.artifact_path.name],
        "calibrations_distinct": v1_runtime.gateway.calibration["calibration_id"]
        != v2_runtime.gateway.calibration["calibration_id"],
        "thresholds_distinct": v1_runtime.policy.threshold != v2_runtime.policy.threshold,
        "v1_policy_ids": [v1_runtime.policy.model_id, v1_runtime.policy.calibration_id],
        "v2_policy_ids": [v2_runtime.policy.model_id, v2_runtime.policy.calibration_id],
        "v1_session_store_untouched_by_v2_traffic": v1_app.state.session_store.session_count() == 1,
        "v1_response_after_v2_traffic": {k: fresh_v1.get(k) for k in (
            "model_id", "calibration_id", "threshold", "monitoring_state")},
        "v1_calibration_still_cal_v1": v1_runtime.gateway.calibration["calibration_id"] == "CAL_V1",
        "v2_calibration_still_cal_v2": v2_runtime.gateway.calibration["calibration_id"] == "CAL_V2",
    }
    mutables = [m for rel in V2_MODULES for m in _module_level_mutables(rel)]
    in_ok = (in_process["gateway_artifacts_distinct"] and in_process["calibrations_distinct"]
             and in_process["thresholds_distinct"] and in_process["v1_calibration_still_cal_v1"]
             and in_process["v2_calibration_still_cal_v2"]
             and fresh_v1.get("model_id") == "MODEL_V1"
             and fresh_v1.get("calibration_id") == "CAL_V1"
             and in_process["v1_session_store_untouched_by_v2_traffic"] and not mutables)
    serial = lambda o: json.loads(json.dumps(o, default=sorted))  # noqa: E731
    data = {
        "fresh_process_cross_contamination": serial(cross),
        "same_session_id_used_in_both_processes": True,
        "in_process_coexistence": serial(in_process),
        "module_level_mutable_bindings_in_v2_modules": mutables,
        "singleton_or_global_model_binding": False,
        "status": "PASS" if (cross_ok and in_ok) else "FAIL",
    }
    (OUT / "runtime_isolation_audit.json").write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return data


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    a = v1_default_regression()
    b = isolation()
    print(a["status"], b["status"])
    if a["status"] != "PASS" or b["status"] != "PASS":
        raise SystemExit("V2_013_V1_REGRESSION_OR_ISOLATION_FAILED")


if __name__ == "__main__":
    main()
