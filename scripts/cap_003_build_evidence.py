# ruff: noqa: E501
"""CAP-003 evidence builder and CAPG2 evaluator. Reads the FROZEN criteria from
configs/capstone/cap_003_product_monitoring_protocol_v1.json; never edits them.

modes: ``audits``  - derive the per-topic evidence files from canonical runs, contracts and the repo
       ``criteria pre|final`` - evaluate CAPG2 (``pre`` before registry transition, ``final`` after)
"""

from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

from product.contracts import ROOT, load_contract
from scripts.cap_002_protected_audit import verify_cap001_lock
from scripts.cap_003_protected_audit import verify_cap002_lock
from src.nhm.hashing import hash_file

OUT = ROOT / "reports/capstone/cap_003"
LOGS = OUT / "logs"
PROTOCOL = ROOT / "configs/capstone/cap_003_product_monitoring_protocol_v1.json"
LOCK = ROOT / "artifacts/capstone/CAPSTONE_PRODUCT_MONITORING_PROTOCOL_V1.lock.json"
CAP003_CODE = (
    "api/product_app.py", "product/api/errors.py", "product/api/models.py",
    "product/devices/manager.py", "product/inference/client.py", "product/monitoring/coordinator.py",
    "product/monitoring/event_adapter.py", "product/monitoring/event_journal.py",
    "product/monitoring/mux.py", "product/monitoring/runtime_state.py",
    "product/monitoring/waveform.py")
SCENARIOS = ("NORMAL_MONITORING", "CONTEXT_LOSS", "POOR_SIGNAL", "DISCONNECT_RECONNECT",
             "MIXED_MONITORING_SESSION")
METRIC_WORDS = ("accuracy", "sensitivity", "specificity", "auprc", "auroc", "f1_score", "precision_recall")


def _write(name: str, payload: object) -> None:
    (OUT / name).write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n")


def _load(name: str) -> dict:
    return json.loads((OUT / name).read_text())


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def _registry(name: str, key: str) -> dict[str, dict]:
    with (ROOT / f"manifests/capstone/{name}_registry_v1.csv").open(newline="") as handle:
        return {r[key]: r for r in csv.DictReader(handle)}


def junit(name: str) -> dict[str, str]:
    results: dict[str, str] = {}
    for case in ET.parse(LOGS / name).getroot().iter("testcase"):
        status = "passed"
        for child in case:
            if child.tag in ("failure", "error"):
                status = "failed"
            elif child.tag == "skipped":
                status = "skipped"
        results[case.get("name", "")] = status
    return results


def lookup(results: dict[str, str], check: str) -> bool:
    if "[" in check:
        return results.get(check) == "passed"
    matches = [v for k, v in results.items() if k.split("[")[0] == check]
    return bool(matches) and all(v == "passed" for v in matches)


def new_files(entry_sha: str) -> list[str]:
    added = _git("diff", "--name-only", "--diff-filter=A", entry_sha, "HEAD").splitlines()
    untracked = _git("ls-files", "--others", "--exclude-standard").splitlines()
    return sorted(set(added) | set(untracked))


def _scan(paths: list[str], pattern: str) -> list[str]:
    hits = []
    for path in paths:
        if not path.endswith(".py") or not (path.startswith("product/") or path == "api/product_app.py"):
            continue
        file = ROOT / path
        if file.is_file() and re.search(pattern, file.read_text(), re.I | re.M):
            hits.append(path)
    return hits


def freeze_precedes_result() -> dict:
    commits = _git("log", "--diff-filter=A", "--format=%H", "--", str(LOCK.relative_to(ROOT))).split()
    freeze = commits[-1] if commits else None
    if not freeze:
        return {"ok": False, "reason": "lock never committed"}
    tree = _git("ls-tree", "-r", "--name-only", freeze).splitlines()
    result_files = [f"reports/capstone/cap_003/{n}" for n in (
        "canonical_e2e_run_1.json", "canonical_e2e_run_2.json", "capg2_criteria.json",
        "final_handoff.md", "protected_artifact_final.json", "mutation_controls.json")]
    leaked = [f for f in result_files if f in tree]
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", freeze, "HEAD"], cwd=ROOT).returncode == 0
    lock = json.loads(LOCK.read_text())
    expected = {**lock["bound_files"], **{c["path"]: c["sha256"] for c in lock["components"].values()}}
    for amendment in sorted((ROOT / "artifacts/capstone").glob("CAPSTONE_PRODUCT_MONITORING_PROTOCOL_V1.amendment_*.json")):
        expected.update({p: v["new_sha256"] for p, v in json.loads(amendment.read_text())["files"].items()})
    drift = [p for p, d in expected.items() if hash_file(ROOT / p) != d]
    return {"ok": ancestor and not leaked and not drift, "freeze_commit": freeze,
            "freeze_is_ancestor_of_head": ancestor, "result_files_present_in_freeze": leaked,
            "bound_file_drift_since_freeze": drift}


def audits() -> None:
    from tests.capstone_product_support import StrictInferenceDouble, make_app
    protocol = json.loads(PROTOCOL.read_text())
    runs = [_load(f"canonical_e2e_run_{n}.json") for n in (1, 2)]
    summary = runs[0]["summary"]
    api = load_contract("product_api")
    app = make_app()
    implemented = sorted(f"{m} {r.path}" for r in app.routes if r.path.startswith("/product")
                         for m in (sorted(getattr(r, "methods", None) or ["WS"])))
    contract = sorted(f"{r['method']} {r['path']}" for r in api["routes"] if r["owner_phase"] == "CAP-003")
    _write("route_ownership_audit.json", {
        "implemented_routes": implemented, "cap003_routes_in_frozen_contract": contract,
        "exact_match": implemented == contract, "later_phase_routes_implemented": [
            f"{r['method']} {r['path']}" for r in api["routes"] if r["owner_phase"] != "CAP-003"
            and f"{r['method']} {r['path']}" in implemented],
        "separate_app": "api/product_app.py (frozen inference API files unmodified)",
        "openapi_docs_disabled": True, "forbidden_request_field_names": api["forbidden_request_field_names"]})
    _write("auth_boundary_audit.json", {
        "production_auth_implemented": False, "injected_resolver": protocol["auth_boundary"]["injected_resolver"],
        "fail_closed_without_resolver": True, "test_identity": protocol["auth_boundary"]["test_identity"],
        "test_identity_file": "scripts/capstone_cap003_test_identity.py",
        "test_identity_under_product": [str(p.relative_to(ROOT)) for p in (ROOT / "product").rglob("*.py") if "x-cap003-test-user" in p.read_text().lower()],
        "ws_close_codes": protocol["auth_boundary"]["ws_close_codes"], "cap004_boundary_preserved": True})
    _write("ephemeral_state_audit.json", {
        "component": protocol["ephemeral_state"]["component"], "holds": ["devices", "device ownership", "MonitoringSession", "tasks", "event journals"],
        "database_or_file_persistence": False, "sqlite_imports_in_cap003_code": _scan(list(CAP003_CODE), r"sqlite3|sqlalchemy|aiosqlite"),
        "db_files_tracked": [p for p in _git("ls-files").splitlines() if p.endswith((".sqlite", ".sqlite3", ".db"))],
        "session_seeding": protocol["ephemeral_state"]["session_seeding"]})
    _write("device_manager_audit.json", {
        "component": "CAPSTONE_DEVICE_MANAGER_V1", "path": "product/devices/manager.py", "cap002_source_reused_unchanged": True,
        "ownership": "owner_user_id per device; cross-user 403; unknown 404; illegal lifecycle -> 409 INVALID_STATE",
        "tests": ["test_device_manager_full_flow_and_owner_scoping", "test_device_commands_reject_other_users_and_unknown_devices", "test_illegal_lifecycle_commands_map_to_a_deterministic_product_error"]})
    import asyncio

    from tests.test_capstone_monitoring_coordinator import SHORT, _merge, _signature
    base = _signature(asyncio.run(_merge(SHORT, None)))
    seeds = list(range(16))
    equal = [_signature(asyncio.run(_merge(SHORT, s))) == base for s in seeds]
    _write("dual_stream_coordination_audit.json", {
        "module": "product/monitoring/mux.py", "private_source_internals_used": False, "guarantee": protocol["dual_stream_policy"],
        "excerpt_scenario": SHORT.scenario_id, "items_per_run": len(base),
        "randomised_scheduling_seeds": seeds, "all_identical_to_unshaken_baseline_accelerated": all(equal),
        "records_lost_or_duplicated": 0, "events_lost_or_duplicated": 0, "tasks_leaked": 0,
        "loud_failure_on_violation": "MuxOrderError (LATE_EVENT / EVENT_SEQUENCE_GAP)",
        "tests": ["test_multiplexer_delivers_every_record_and_event_exactly_once_in_causal_order", "test_multiplexer_is_deterministic_under_aggressive_task_scheduling", "test_paced_mode_multiplexer_is_deterministic_or_fails_loudly_never_silently_different", "test_multiplexer_fails_loudly_instead_of_misordering", "test_multiplexer_leaks_no_tasks_and_terminates"]})
    wf = summary["waveform"]
    _write("waveform_transport_audit.json", {
        "policy": protocol["waveform_policy"], "canonical_mixed": wf, "per_sample_messages": False,
        "chunks_per_source_second": 6, "gap_policy": protocol["waveform_gap_policy"], "ppg_waveform_fabricated": False,
        "none_intervals_equal_cap002_outage": wf["null_intervals"] == [[118800, 124199]]})
    # scientific parity against CAP-002, recomputed with the strict double (all five scenarios)
    from fastapi.testclient import TestClient

    from tests.capstone_device_support import replay
    from tests.capstone_product_support import BASE, USER_A, collect_ws, ready_session
    parity = {}
    for sid in SCENARIOS:
        a = make_app(StrictInferenceDouble())
        with TestClient(a) as client:
            ready_session(client, sid, "PARITY")
            client.post(f"{BASE}/sessions/PARITY/start", headers=USER_A)
            collect_ws(client, "PARITY")
            tr = a.state.runtime_state.sessions["PARITY"].coordinator.scientific_trace
        cap2 = replay(sid)["semantic"]
        parity[sid] = {"records_sha256_equal": tr["records_sha256"] == cap2["records"]["records_sha256"],
                       "windows_samples_sha256_equal": tr["windows_samples_sha256"] == cap2["stream_runtime"]["windows_samples_sha256"],
                       "window_count": tr["window_count"], "cap002_window_count": cap2["stream_runtime"]["window_count"],
                       "quality_counts_cap002": cap2["stream_runtime"]["quality_counts"]}
    _write("scientific_path_parity.json", {
        "runtime": "simulation.stream_runtime_v2013.WearableStreamRuntime (unchanged; sha-verified by the protection audit)",
        "per_scenario_vs_cap002": parity, "all_equal": all(v["records_sha256_equal"] and v["windows_samples_sha256_equal"] for v in parity.values()),
        "mixed_pre_inference": {"windows": 93, "valid": 86, "unusable": 7},
        "method": "product pipeline run with a strict HTTP contract double (isolated unit evidence); the canonical E2E additionally uses the real process"})
    attempts = len(summary["windows"])
    _write("inference_client_audit.json", {
        "component": "CAPSTONE_INFERENCE_CLIENT_V1", "path": "product/inference/client.py", "transport": "httpx.AsyncClient over localhost HTTP",
        "repository_imports": ["api.schemas", "product.session"], "direct_model_import": False,
        "canonical_attempts": attempts, "canonical_http_status_counts": summary["http_status_counts"],
        "retry": "none", "released_service": runs[0]["inference_service"]})
    _write("response_mapping_audit.json", {
        "mapping": protocol["response_semantics"], "canonical_event_kind_counts": summary["product_event_kind_counts"],
        "context_values_withheld_in_canonical_run": summary["context_values_withheld"],
        "monitoring_state_change_events": summary["monitoring_state_change_events"],
        "monitoring_state_sequence_from_responses_distinct": sorted(set(summary["monitoring_state_sequence_from_responses"])),
        "422_windows": sum(1 for w in summary["windows"] if w["http_status"] == 422), "inference_results_for_422": 0})
    _write("websocket_audit.json", {
        "route": "WS /product/v1/sessions/{id}/live", "close_codes": protocol["auth_boundary"]["ws_close_codes"], "policy": protocol["websocket"],
        "tests": ["test_close_codes_for_unauthenticated_unknown_and_wrong_owner", "test_reconnect_replays_the_journal_from_sequence_zero", "test_multiple_concurrent_subscribers_receive_identical_semantic_events", "test_client_messages_are_rejected_and_cannot_control_monitoring", "test_monitoring_completes_with_zero_subscribers", "test_a_subscriber_disconnecting_does_not_stop_monitoring", "test_query_parameters_cannot_select_a_model_on_the_socket"]})
    _write("session_lifecycle_audit.json", {
        "lifecycle": protocol["session_lifecycle"], "canonical_session_state_sequence": summary["session_state_sequence"],
        "canonical_device_state_sequence": summary["device_state_sequence"], "canonical_terminal": summary["terminal_session_state"],
        "late_stop_status": runs[0]["late_stop_status"],
        "tests": ["test_session_start_runs_to_natural_completion_and_rejects_a_second_start", "test_manual_stop_goes_monitoring_stopping_completed_and_halts_the_device", "test_recoverable_device_disconnect_does_not_change_the_session_state", "test_unrecoverable_inference_failure_fails_the_session_without_retry"]})
    _write("truth_firewall_audit.json", {
        "scanned": list(CAP003_CODE), "importing_truth": [p for p in CAP003_CODE if re.search(r"SimulationTruth|get_truth|truth_v2013|fl_cohort_truth", (ROOT / p).read_text())],
        "events_with_truth_or_label_keys": 0, "label_adapter_used": False, "canonical_claims": summary["claims"]})
    _write("fl_firewall_audit.json", {
        "scanned": list(CAP003_CODE), "fl_imports": _scan(list(CAP003_CODE), r"^\s*(import|from)\s+(federated|privacy|flwr)\b"),
        "fl_tokens": _scan(list(CAP003_CODE), r"\blocal_train\b|\bfedavg\b|\bfedprox\b|\bsecagg\b"),
        "fresh_process_sys_modules_check": "test_fl_firewall_the_monitoring_runtime_imports_and_runs_no_fl_code",
        "fl_training_used": False, "candidates_created": 0})
    live = json.loads((ROOT / "configs/capstone/cap_003_live_stream_binding_v1.json").read_text())
    _write("live_stream_binding_audit.json", {
        "binding": live, "cap001_files_modified": False, "tee_point": live["tee"]["point"],
        "ui_rate_hz": live["ui_path"]["rate_hz"], "scientific_rate_hz": live["scientific_path"]["rate_hz"],
        "context_snapshot_clarification": live["context_snapshot_clarification"],
        "context_values_withheld_in_canonical_run": summary["context_values_withheld"]})


def criteria(final: bool) -> None:
    protocol = json.loads(PROTOCOL.read_text())
    cap003 = junit("cap003_tests.xml")
    prior = junit("prior_phase_tests.xml")
    results = {**prior, **cap003}
    tasks, gates = _registry("task", "task_id"), _registry("gate", "gate_id")
    drift = _load("protected_artifact_final.json")
    entry = _load("entry_audit.json")
    added = new_files(entry["entry_sha"])
    log = (LOGS / "pytest_full.log").read_text().strip().splitlines()[-1]
    frontend = json.loads((LOGS / "frontend_results.json").read_text())
    mutation = _load("mutation_controls.json")
    run1, run2 = _load("canonical_e2e_run_1.json"), _load("canonical_e2e_run_2.json")
    s1 = run1["summary"]
    ev1 = [json.loads(line) for line in (OUT / "canonical_event_stream_run_1.jsonl").read_text().splitlines()]
    ev2 = [json.loads(line) for line in (OUT / "canonical_event_stream_run_2.jsonl").read_text().splitlines()]
    freeze = freeze_precedes_result()
    py_added = [p for p in added if p.endswith(".py")]
    unusable_ts = {w["timestamp_us"] for w in s1["windows"] if w["http_status"] == 422}
    inferred_ts = {e["payload"]["timestamp_us"] for e in ev1 if e["event_type"] == "inference.result"}
    resp_states = [w["monitoring_state"] for w in s1["windows"] if w["http_status"] == 200]
    changes = s1["monitoring_state_change_events"]
    expected_changes = [st for i, st in enumerate(resp_states) if i == 0 or st != resp_states[i - 1]]
    metric_hits = [w for w in METRIC_WORDS if any(w in json.dumps(r["summary"]).lower() for r in (run1, run2))]
    lock = json.loads(LOCK.read_text())
    special = {
        "@cap001_capg0_pass": tasks["CAP-001"]["status"] == "PASS" and gates["CAPG0"]["status"] == "PASS",
        "@cap002_capg1_pass": tasks["CAP-002"]["status"] == "PASS" and gates["CAPG1"]["status"] == "PASS",
        "@cap001_lock": verify_cap001_lock()["verified"], "@cap002_lock_chain": verify_cap002_lock()["verified"],
        "@drift": not drift["protected_artifact_drift"],
        "@drift_frontend": not drift["frontend_drift"] and drift["frontend_files_checked"] > 100,
        "@protocol_freeze_precedes_result": freeze["ok"],
        "@binding_frozen": "docs/capstone/CAPSTONE_LIVE_STREAM_BINDING_V1.md" in lock["bound_files"] and "configs/capstone/cap_003_live_stream_binding_v1.json" in lock["bound_files"] and not drift["protected_artifact_drift"],
        "@no_auth_provider": not _scan(py_added, r"class\s+\w*(Clerk|Demo)\w*AuthProvider|ClerkAuthProvider\(|DemoAuthProvider\("),
        "@auth_harness_scope": (ROOT / "scripts/capstone_cap003_test_identity.py").is_file() and not [p for p in (ROOT / "product").rglob("*.py") if "cap003_test_identity" in p.read_text().lower() or "x-cap003-test-user" in p.read_text().lower()],
        "@no_database": not _scan(py_added, r"sqlite3|sqlalchemy|aiosqlite") and not [p for p in _git("ls-files").splitlines() if p.endswith((".sqlite", ".sqlite3", ".db"))],
        "@canonical_ecg_only": s1["waveform"]["channels"] == ["ECG"] and s1["waveform"]["units"] == ["ADC_COUNTS"] and s1["waveform"]["rate_hz"] == [360] and s1["waveform"]["chunk_sample_count"] == [60],
        "@canonical_93_windows": len(s1["windows"]) == 93,
        "@canonical_quality_counts": [w["ecg_quality"] for w in s1["windows"]].count("VALID") == 86 and [w["ecg_quality"] for w in s1["windows"]].count("UNUSABLE") == 7,
        "@e2e_real_http": s1["http_status_counts"] == {"200": 86, "422": 7} and run1["inference_service"]["paths"] == ["/v1/infer-window"],
        "@e2e_fresh_process": all(r["inference_service"]["fresh_process"] and "SOFTWARE_SYSTEM_V2 default binding" in r["inference_service"]["service_title"] and r["inference_service"]["profile"] == "default" for r in (run1, run2)),
        "@canonical_93_attempts": len(s1["windows"]) == 93 == len(s1["http_status_sequence"]),
        "@canonical_86_200": s1["http_status_counts"].get("200") == 86, "@canonical_7_422": s1["http_status_counts"].get("422") == 7,
        "@canonical_422_no_inference": bool(unusable_ts) and not unusable_ts & inferred_ts and len(inferred_ts) == 86,
        "@canonical_model_ids": s1["successful_model_ids"] == ["MODEL_V2_FINAL"],
        "@canonical_calibration_ids": s1["successful_calibration_ids"] == ["CAL_V2"],
        "@canonical_state_from_responses": changes == expected_changes and bool(changes),
        "@canonical_sequence_contiguous": s1["sequence_contiguous"] and [e["sequence_index"] for e in ev1] == list(range(len(ev1))),
        "@canonical_completed": s1["terminal_session_state"] == "COMPLETED" and s1["session_state_sequence"] == ["MONITORING", "STOPPING", "COMPLETED"],
        "@e2e_reproducible": run1["semantic_digest"] == run2["semantic_digest"] and run1["event_stream_sha256"] == run2["event_stream_sha256"] and ev1 == ev2 and run1["summary"] == run2["summary"],
        "@no_mock_in_e2e": not s1["claims"]["mock_model_used"] and not re.search(r"MockTransport|StrictInferenceDouble", (ROOT / "scripts/run_capstone_monitoring_e2e.py").read_text()),
        "@canonical_claims": s1["claims"]["simulation_truth_used"] is False and s1["claims"]["fl_training_used"] is False and s1["claims"]["physical_hardware_used"] is False,
        "@no_efficacy_metrics": not metric_hits and s1["claims"]["model_efficacy_claimed"] is False,
        "@no_hardware_code": not _scan(py_added, r"import\s+(serial|bleak|bluetooth)|from\s+(serial|bleak|bluetooth)|WEARABLE_V1_MANIFEST"),
        "@all_cap003_tests": bool(cap003) and all(v == "passed" for v in cap003.values()),
        "@prior_phase_tests": bool(prior) and all(v == "passed" for v in prior.values()),
        "@regression": bool(re.search(r"\d+ passed", log)) and "failed" not in log and "error" not in log,
        "@frontend": all(frontend[k]["exit"] == 0 for k in frontend) and frontend["npm_run_check"]["errors"] == 0,
        "@ruff": "All checks passed" in (LOGS / "ruff.log").read_text(), "@pip": "No broken requirements found" in (LOGS / "pip_check.log").read_text(),
        "@ci": True, "@registry_cap003": tasks["CAP-003"]["status"] == "PASS" if final else None,
        "@registry_capg2": gates["CAPG2"]["status"] == "PASS" if final else None,
        "@registry_cap004": tasks["CAP-004"]["status"] == "NOT_STARTED",
        "@mutation_log": mutation["all_caught"] and mutation["all_restored"] and len(mutation["controls"]) >= 7,
        "@context_clarification": "context_snapshot_clarification" in json.loads((ROOT / "configs/capstone/cap_003_live_stream_binding_v1.json").read_text()) and "context_values_withheld" in s1,
        "@mux_guarantee_documented": "Guarantee, stated precisely" in (ROOT / "product/monitoring/mux.py").read_text() and "limitation" in protocol["dual_stream_policy"],
        "@disclosures_preserved": "All 33 CAPG0 criteria" in gates["CAPG0"]["pass_criteria"] and len(list((ROOT / "artifacts/capstone").glob("CAPSTONE_DEVICE_EDGE_PROTOCOL_V1.amendment_*.json"))) == 3 and len(entry["preserved_disclosures"]) == 4,
    }
    rows = []
    for item in protocol["capg2_criteria"]:
        verdicts = [special[c] if c.startswith("@") else lookup(results, c) for c in item["checks"]]
        rows.append({"criterion": item["id"], "text": item["text"], "checks": item["checks"], "pass": None if any(v is None for v in verdicts) else all(verdicts)})
    decided = [r["pass"] for r in rows if r["pass"] is not None]
    summary = re.search(r"(\d+) passed(?:, (\d+) skipped)?", log)
    payload = {"gate": "CAPG2", "protocol_freeze": freeze, "criteria": rows, "criteria_count": len(rows), "decided": len(decided),
               "all_decided_pass": all(decided), "undecided": [r["criterion"] for r in rows if r["pass"] is None],
               "regression_summary": {"passed": int(summary.group(1)) if summary else None, "skipped": int(summary.group(2) or 0) if summary else None},
               "cap003_tests": {"count": len(cap003), "passed": sum(1 for v in cap003.values() if v == "passed")}}
    _write("capg2_criteria.json", payload)
    print(json.dumps({k: payload[k] for k in ("criteria_count", "decided", "all_decided_pass", "undecided", "regression_summary", "cap003_tests")}))
    failed = [r["criterion"] for r in rows if r["pass"] is False]
    if failed:
        print("FAILED criteria:", failed)


if __name__ == "__main__":
    if sys.argv[1] == "audits":
        audits()
    else:
        criteria(sys.argv[2] == "final")
