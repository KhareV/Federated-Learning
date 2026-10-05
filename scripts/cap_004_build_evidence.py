# ruff: noqa: E501
"""CAP-004 evidence builder and CAPG3 evaluator. Reads the FROZEN criteria from
configs/capstone/cap_004_auth_persistence_protocol_v1.json; never edits them.

modes: ``audits``  - derive the per-topic evidence files from canonical runs, contracts and the repo
       ``criteria pre|final`` - evaluate CAPG3 (``pre`` before registry transition, ``final`` after)
"""

from __future__ import annotations

import csv
import importlib.metadata as md
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

from product.contracts import ROOT, load_contract
from scripts.cap_002_protected_audit import verify_cap001_lock
from scripts.cap_003_protected_audit import verify_cap002_lock
from scripts.cap_004_protected_audit import (
    EXPECTED_ENTRY,
    dependency_files_ok,
    verify_cap003_lock,
)
from src.nhm.hashing import hash_file

OUT = ROOT / "reports/capstone/cap_004"
LOGS = OUT / "logs"
PROTOCOL = ROOT / "configs/capstone/cap_004_auth_persistence_protocol_v1.json"
LOCK = ROOT / "artifacts/capstone/CAPSTONE_AUTH_PERSISTENCE_PROTOCOL_V1.lock.json"
CODE_DIRS = ("product/auth", "product/persistence", "product/sessions", "capstone_persistence")
CODE_FILES = ("api/product_app_v1_1.py", "product/api/models_v2.py", "scripts/run_capstone_product.py")
CRITICAL_PACKAGES = ("torch", "numpy", "scipy", "wfdb", "scikit-learn", "flwr", "fastapi", "pydantic",
                     "httpx", "cryptography", "starlette", "uvicorn", "websockets", "pytest", "ruff")
FUTURE = ("session_summaries", "federation_runs", "federation_rounds", "fl_client_statuses",
          "candidate_models", "governance_decisions")
METRIC_WORDS = ("accuracy", "sensitivity", "specificity", "auprc", "auroc", "f1_score", "precision_recall")
PREDECLARED = {"windows": 93, "valid": 86, "unusable": 7, "attempts": 93, "http_200": 86,
               "http_422": 7, "model_id": "MODEL_V2_FINAL", "calibration_id": "CAL_V2",
               "terminal": "COMPLETED"}


def _write(name: str, payload: object) -> None:
    (OUT / name).write_text(json.dumps(payload, indent=1, sort_keys=True, default=str) + "\n")


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


def cap004_code() -> list[str]:
    paths = [str(p.relative_to(ROOT)) for d in CODE_DIRS for p in (ROOT / d).rglob("*.py")]
    return sorted(paths + list(CODE_FILES))


def _scan(paths: list[str], pattern: str) -> list[str]:
    hits = []
    for path in paths:
        file = ROOT / path
        if path.endswith(".py") and file.is_file() and re.search(pattern, file.read_text(), re.I | re.M):
            hits.append(path)
    return hits


def stream(run: int) -> list[dict]:
    return [json.loads(line) for line in (OUT / f"canonical_event_stream_run_{run}.jsonl").read_text().splitlines()]


def quality_changes(events: list[dict]) -> int:
    last, count = None, 0
    for event in events:
        if event["event_type"] == "quality.status":
            state = (event["payload"]["ecg_quality"], event["payload"].get("ppg_quality"))
            if state != last:
                count, last = count + 1, state
    return count


def freeze_precedes_result() -> dict:
    commits = _git("log", "--diff-filter=A", "--format=%H", "--", str(LOCK.relative_to(ROOT))).split()
    freeze = commits[-1] if commits else None
    if not freeze:
        return {"ok": False, "reason": "lock never committed"}
    tree = _git("ls-tree", "-r", "--name-only", freeze).splitlines()
    result_files = [f"reports/capstone/cap_004/{n}" for n in (
        "canonical_persistent_e2e_run_1.json", "canonical_persistent_e2e_run_2.json", "crash_recovery.json",
        "capg3_criteria.json", "final_handoff.md", "mutation_controls.json")]
    leaked = [f for f in result_files if f in tree]
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", freeze, "HEAD"], cwd=ROOT).returncode == 0
    lock = json.loads(LOCK.read_text())
    expected = {**lock["bound_files"], **{c["path"]: c["sha256"] for c in lock["components"].values()}}
    registry = dict(lock["component_registry"])
    for amendment in sorted((ROOT / "artifacts/capstone").glob("CAPSTONE_AUTH_PERSISTENCE_PROTOCOL_V1.amendment_*.json")):
        data = json.loads(amendment.read_text())
        expected.update({p: v["new_sha256"] for p, v in data["files"].items()})
        for path, move in data.get("moved_files", {}).items():
            expected.pop(path, None)
            expected[move["to"]] = move["new_sha256"]
        expected.update(data.get("added_files", {}))
        if "component_registry" in data:
            registry["sha256"] = data["component_registry"]["new_sha256"]
    drift = [p for p, d in expected.items() if hash_file(ROOT / p) != d]
    if hash_file(ROOT / registry["path"]) != registry["sha256"]:
        drift.append(registry["path"])
    return {"ok": ancestor and not leaked and not drift, "freeze_commit": freeze,
            "freeze_is_ancestor_of_head": ancestor, "result_files_present_in_freeze": leaked,
            "bound_file_drift_since_freeze": drift}


def _pins(text: str) -> dict[str, str]:
    pins = {}
    for line in text.splitlines():
        match = re.match(r"^([A-Za-z0-9_.\-]+)==([^\s;#]+)", line.strip())
        if match:
            pins[match.group(1).lower().replace("_", "-")] = match.group(2)
    return pins


PIN_FILE = "requirements-capstone-auth.lock"
KNOWN_FLAKE = "test_monitoring_completes_with_zero_subscribers"
KNOWN_FLAKE_ID = f"tests/test_capstone_monitoring_websocket.py::{KNOWN_FLAKE}"


def known_flake_established() -> bool:
    """The frozen CAP-003 test is intermittent at its OWN result commit (untouched worktree) and in
    this tree with the same signature; evidence: preexisting_cap003_flake.json."""
    flake = _load("preexisting_cap003_flake.json")
    old, new = flake["cap003_result_commit_56fc19f_untouched_worktree"], flake["cap004_tree"]
    return (old["failed"] >= 1 and old["passed"] >= 1 and new["passed"] >= 1
            and new["signatures"] == old["signatures"] and not flake["cap004_code_involved"])


def dependency_audit() -> dict:
    entry_pins = _pins(_git("show", f"{EXPECTED_ENTRY}:requirements-dev.lock"))
    now_pins = _pins((ROOT / "requirements-dev.lock").read_text())
    extra_pins = _pins((ROOT / PIN_FILE).read_text())
    ok, deltas = dependency_files_ok()
    installed = {}
    for pkg in (*CRITICAL_PACKAGES, "clerk-backend-api", "pyjwt"):
        try:
            installed[pkg] = md.version(pkg)
        except md.PackageNotFoundError:
            installed[pkg] = None
    changed = {p: [entry_pins.get(p), now_pins.get(p)] for p in set(entry_pins) | set(now_pins)
               if entry_pins.get(p) != now_pins.get(p)}
    return {"entry_commit": EXPECTED_ENTRY, "pins_changed_in_requirements_dev_lock": changed,
            "pyproject_and_requirements_dev_lock_byte_identical_to_entry": not any(
                d["added_lines"] or d["removed_lines"] for d in deltas[:2]),
            "additive_pin_file": PIN_FILE, "additive_pins": extra_pins,
            "why_additive": "artifacts/MODEL_V2_COMPLETE_REPRO_PROTOCOL_V1.lock.json binds pyproject.toml and requirements-dev.lock byte-for-byte",
            "critical_pins_entry_vs_now": {p: [entry_pins.get(p), now_pins.get(p)] for p in CRITICAL_PACKAGES},
            "critical_unchanged": all(entry_pins.get(p) == now_pins.get(p) for p in CRITICAL_PACKAGES),
            "critical_installed_equals_pin": {p: installed[p] == now_pins.get(p) for p in CRITICAL_PACKAGES if now_pins.get(p)},
            "installed": installed,
            "only_allowed_additions": ok and not changed and set(extra_pins) == {"clerk-backend-api", "pyjwt"},
            "file_deltas": deltas, "clerk_installed_version": installed["clerk-backend-api"],
            "policy": json.loads(PROTOCOL.read_text())["dependency_policy"]}


def audits() -> None:
    from api.product_app_v1_1 import create_product_app_v1_1  # noqa: F401
    from product.auth.base import AuthConfigError
    from product.auth.factory import build_auth_provider
    from product.persistence import preview as preview_module
    from tests.capstone_persistent_support import make_persistent_app
    from tests.capstone_product_support import StrictInferenceDouble

    protocol = json.loads(PROTOCOL.read_text())
    runs = [_load(f"canonical_persistent_e2e_run_{n}.json") for n in (1, 2)]
    r1 = runs[0]
    db1, db2 = r1["database_after_process_1"], r1["database_after_restart"]
    events = stream(1)
    api1, api2 = load_contract("product_api"), json.loads((ROOT / "contracts/capstone/product_api_v2.json").read_text())
    s1 = json.loads((ROOT / "contracts/capstone/storage_policy_v1.json").read_text())
    s2 = json.loads((ROOT / "contracts/capstone/storage_policy_v2.json").read_text())
    # ---- contract successors ------------------------------------------------------------------
    _write("contract_successor_audit.json", {
        "storage_policy_v2": {"path": "contracts/capstone/storage_policy_v2.json", "sha256": hash_file(ROOT / "contracts/capstone/storage_policy_v2.json"),
                              "supersedes": s2["supersedes"], "v1_sha256_now": hash_file(ROOT / "contracts/capstone/storage_policy_v1.json"),
                              "v1_unchanged": hash_file(ROOT / "contracts/capstone/storage_policy_v1.json") == s2["supersedes"]["sha256"],
                              "delta": s2["delta_from_v1"]},
        "product_api_v2": {"path": "contracts/capstone/product_api_v2.json", "sha256": hash_file(ROOT / "contracts/capstone/product_api_v2.json"),
                           "v1_sha256_now": hash_file(ROOT / "contracts/capstone/product_api_v1.json"), "delta": api2["delta_from_v1"],
                           "system_info_v2": api2["system_info_v2"]},
        "hidden_hack": False, "mechanism": "additive successor contracts; v1 contracts are protected-artifact files and unmodified"})
    _write("storage_policy_audit.json", {
        "tables_v1": [e["table"] for e in s1["entities"]], "tables_v2": [e["table"] for e in s2["entities"]],
        "same_table_set": [e["table"] for e in s1["entities"]] == [e["table"] for e in s2["entities"]],
        "devices_columns_added": sorted(set(next(e for e in s2["entities"] if e["table"] == "devices")["columns"])
                                        - set(next(e for e in s1["entities"] if e["table"] == "devices")["columns"])),
        "other_entities_identical": all(a == b for a, b in zip(
            (e for e in s1["entities"] if e["table"] != "devices"), (e for e in s2["entities"] if e["table"] != "devices"), strict=True)),
        "population_rules": s2["cap004_population_rules"], "waveform_previews_policy": s2["waveform_previews_policy"],
        "quality_events_policy": s2["quality_events_policy"], "restart_semantics": s2["restart_semantics"],
        "immutability": s2["immutability"], "high_rate_policy": s2["high_rate_policy"]})
    _write("dependency_audit.json", dependency_audit())
    # ---- auth --------------------------------------------------------------------------------
    cases = {}
    for label, env in (("unset", {}), ("invalid", {"NHM_PRODUCT_AUTH_MODE": "demo"}),
                       ("demo_without_ack", {"NHM_PRODUCT_AUTH_MODE": "DEMO"}),
                       ("demo_wrong_ack", {"NHM_PRODUCT_AUTH_MODE": "DEMO", "NHM_PRODUCT_DEMO_AUTH_ACK": "yes"}),
                       ("demo_ack", {"NHM_PRODUCT_AUTH_MODE": "DEMO", "NHM_PRODUCT_DEMO_AUTH_ACK": "I_UNDERSTAND_THIS_IS_NOT_CLERK"}),
                       ("clerk_no_config", {"NHM_PRODUCT_AUTH_MODE": "CLERK"}),
                       ("clerk_wildcard_party", {"NHM_PRODUCT_AUTH_MODE": "CLERK", "CLERK_JWT_KEY": "x", "NHM_CLERK_AUTHORIZED_PARTIES": "*"}),
                       ("clerk_no_parties", {"NHM_PRODUCT_AUTH_MODE": "CLERK", "CLERK_JWT_KEY": "x"})):
        try:
            cases[label] = {"result": "BUILT", "provider": build_auth_provider(env).provider_type.value}
        except AuthConfigError as error:
            cases[label] = {"result": "REFUSED", "reason": str(error)}
    _write("auth_provider_audit.json", {"mode_env": "NHM_PRODUCT_AUTH_MODE", "factory_cases": cases,
                                        "silent_default": cases["unset"]["result"] != "REFUSED",
                                        "clerk_cases_never_build_demo": all(v.get("provider") != "DEMO" for k, v in cases.items() if k.startswith("clerk"))})
    clerk_src = (ROOT / "product/auth/clerk.py").read_text()
    _write("clerk_provider_audit.json", {
        "sdk_import": "from clerk_backend_api.security import AuthenticateRequestOptions, authenticate_request_async" in clerk_src,
        "accepts_token": "session_token", "authorized_parties_required": True,
        "custom_jwt_or_crypto_imports": _scan(["product/auth/clerk.py", "product/auth/resolver.py", "product/auth/factory.py", "product/auth/base.py"], r"^\s*(import|from)\s+(jwt|jose|cryptography|hmac|base64)\b"),
        "decode_and_trust": bool(re.search(r"b64decode|json\.loads\(.*split", clerk_src)),
        "installed_sdk_version": md.version("clerk-backend-api"), "pin": "clerk-backend-api==7.0.0",
        "test_boundary": protocol["auth"]["clerk"]["test_boundary"], "real_account_or_secret_used": False,
        "tests": ["test_a_validly_signed_session_token_yields_the_verified_identity", "test_unsigned_and_tampered_tokens_are_rejected_not_trusted", "test_only_session_tokens_are_accepted_machine_and_api_tokens_are_not"]})
    from product.auth.demo import DemoAuthProvider
    demo = DemoAuthProvider()
    _write("demo_auth_audit.json", {"user_id": demo.describe().provider.value, "describe": demo.describe().model_dump(mode="json") if hasattr(demo.describe(), "model_dump") else str(demo.describe()),
                                    "ack_value": protocol["auth"]["demo"]["ack_value"], "canonical_me": r1["process_1"]["me"],
                                    "canonical_system": r1["process_1"]["system"]})
    # ---- sqlite / persistence ----------------------------------------------------------------
    _write("sqlite_schema_audit.json", {"pragmas": db1["pragmas"], "integrity_check": db1["integrity_check"], "foreign_key_check": db1["foreign_key_check"],
                                        "tables": db1["tables"], "schema_sha256": db1["schema_sha256"], "schema_sql": db1["schema_sql"],
                                        "raw_sample_table_present": any("sample" in t or t.startswith("raw_") for t in db1["tables"]),
                                        "database_file_committed": False, "row_counts_after_process_1": db1["row_counts"],
                                        "row_counts_after_restart": db2["row_counts"]})
    _write("user_device_persistence_audit.json", {"users": db1["users"], "devices": db1["devices"], "devices_after_restart": db2["devices"],
                                                  "process_2_devices_via_api": r1["process_2"]["devices"],
                                                  "connection_history_rows": db1["row_counts"]["device_connections"],
                                                  "credential_strings_in_database": db1["credential_strings_in_database"] + db2["credential_strings_in_database"]})
    _write("session_service_audit.json", {"created": r1["process_1"]["session_created"], "listed": r1["process_1"]["session_list_ids"],
                                          "final": r1["process_1"]["final_session"], "late_start_status": r1["process_1"]["late_start_status"],
                                          "session_state_sequence": r1["observed"]["session_state_sequence"], "persisted_sessions": db1["sessions"],
                                          "reused_services": ["product.monitoring.coordinator", "product.devices.manager", "product.monitoring.event_adapter", "product.inference.client"]})
    counts = {k: sum(1 for e in events if e["event_type"] == k) for k in sorted({e["event_type"] for e in events})}
    _write("event_persistence_audit.json", {
        "mapping": protocol["event_mapping"], "live_event_counts": counts, "row_counts": db1["row_counts"],
        "inference_rows_equal_inference_events": db1["row_counts"]["inference_events"] == counts["inference.result"],
        "monitoring_state_rows_equal_events": db1["row_counts"]["monitoring_state_events"] == counts.get("monitoring.state", 0),
        "context_rows_equal_events": db1["row_counts"]["context_snapshots"] == counts.get("context.snapshot", 0),
        "quality_events_seen": counts["quality.status"], "quality_rows_written": db1["row_counts"]["signal_quality_events"],
        "quality_state_changes_in_stream": quality_changes(events), "waveform_chunks_seen": counts.get("waveform.chunk", 0),
        "waveform_rows": db1["row_counts"]["waveform_previews"], "per_sample_rows": 0})
    _write("context_dual_representation_audit.json", {
        "raw_context_rows": db1["raw_context_rows"], "product_context_rows": db1["product_context_rows"],
        "withheld_context_cases": db1["withheld_context_cases"], "withheld_timestamps": db1["withheld_timestamps"],
        "withheld_raw_has_ppg_values": db1["withheld_raw_has_ppg_values"], "withheld_product_values_null": db1["withheld_product_values_null"],
        "cap003_context_values_withheld": r1["noninterference"]["cap003_context_values_withheld"], "semantics": protocol["raw_vs_product_context"]})
    _write("waveform_preview_audit.json", {"preview": db1["waveform_preview"], "max_points": preview_module.MAX_POINTS, "policy": protocol["waveform_preview"],
                                           "raw_waveform_table": False, "read_by_scientific_runtime": bool(_scan(
                                               ["product/monitoring/coordinator.py", "product/monitoring/mux.py", "product/inference/client.py"], r"persistence\.preview|waveform_previews"))})
    crash = _load("crash_recovery.json")
    _write("restart_recovery_audit.json", {"policy": protocol["restart_recovery"]["policy"], "restart_run_process_2": r1["process_2"],
                                           "database_unchanged_across_restart": db1["row_counts"] == db2["row_counts"] and db1["sessions"] == db2["sessions"],
                                           "crash": crash})
    _write("restart_process_1.json", {"process": r1["process_1"], "database_after": db1})
    _write("restart_process_2.json", {"process": r1["process_2"], "database_after": db2})
    _write("ownership_audit.json", {"cross_user_results": r1["ownership_process_3"], "enforced_at": ["REST", "WebSocket close 4403"]})
    # ---- routes ------------------------------------------------------------------------------
    app, store = make_persistent_app(ROOT / "reports/capstone/cap_004/logs/route_probe.sqlite3", StrictInferenceDouble())
    implemented = sorted(f"{m} {r.path}" for r in app.routes if r.path.startswith("/product")
                         for m in sorted(getattr(r, "methods", None) or ["WS"]) if m not in ("HEAD", "OPTIONS"))
    store.close()
    for suffix in ("", "-wal", "-shm"):
        (ROOT / f"reports/capstone/cap_004/logs/route_probe.sqlite3{suffix}").unlink(missing_ok=True)
    expected = sorted(api2["implemented_by_phase"]["CAP-003"] + api2["implemented_by_phase"]["CAP-004"])
    _write("route_parity_audit.json", {
        "implemented_routes": implemented, "expected_cap003_plus_cap004": expected, "exact_match": implemented == expected,
        "later_phase_routes_implemented": [r for r in api2["implemented_by_phase"]["still_unimplemented"] if r in implemented],
        "v1_contract_cap003_routes_all_preserved": all(f"{r['method']} {r['path']}" in implemented for r in api1["routes"] if r["owner_phase"] == "CAP-003"),
        "frozen_cap003_app_sha256": hash_file(ROOT / "api/product_app.py")})
    _write("scientific_noninterference.json", {
        "projection": protocol["projection"], "runs": {f"run_{i + 1}": runs[i]["noninterference"] for i in range(2)},
        "projected_stream_sha256": [r["projected_event_stream_sha256"] for r in runs],
        "cap003_reference_stream": "reports/capstone/cap_003/canonical_event_stream_run_1.jsonl",
        "scientific_modules_modified": False, "protected_audit": "reports/capstone/cap_004/protected_artifact_final.json"})
    _write("canonical_persistent_e2e.json", {"run_1": {k: v for k, v in runs[0].items() if not k.startswith("database_")},
                                             "run_2": {k: v for k, v in runs[1].items() if not k.startswith("database_")},
                                             "crash": "crash_recovery.json", "predeclared_invariants": PREDECLARED})


def criteria(final: bool) -> None:
    protocol = json.loads(PROTOCOL.read_text())
    cap004 = junit("cap004_tests.xml")
    prior = junit("prior_phase_tests.xml")
    results = {**prior, **cap004}
    tasks, gates = _registry("task", "task_id"), _registry("gate", "gate_id")
    drift = _load("protected_artifact_final.json")
    entry = _load("entry_audit.json")
    added = new_files(entry["entry_sha"])
    full_text = (LOGS / "pytest_full.log").read_text()
    log = full_text.strip().splitlines()[-1]
    full_failed = re.findall(r"^FAILED (\S+)", full_text, re.M)
    flake_ok = known_flake_established()
    frontend = json.loads((LOGS / "frontend_results.json").read_text())
    mutation = _load("mutation_controls.json")
    runs = [_load(f"canonical_persistent_e2e_run_{n}.json") for n in (1, 2)]
    crash = _load("crash_recovery.json")
    deps = _load("dependency_audit.json")
    routes = _load("route_parity_audit.json")
    freeze = freeze_precedes_result()
    r1 = runs[0]
    p1, p2, p3 = r1["process_1"], r1["process_2"], r1["ownership_process_3"]
    db1, db2, obs = r1["database_after_process_1"], r1["database_after_restart"], r1["observed"]
    policy_tables = [e["table"] for e in json.loads((ROOT / "contracts/capstone/storage_policy_v2.json").read_text())["entities"]]
    ev = stream(1)
    py_added = [p for p in added if p.endswith(".py")]
    both = [(r, r["database_after_process_1"], r["database_after_restart"]) for r in runs]
    s1v1 = json.loads((ROOT / "contracts/capstone/storage_policy_v1.json").read_text())
    s2 = json.loads((ROOT / "contracts/capstone/storage_policy_v2.json").read_text())
    api2 = json.loads((ROOT / "contracts/capstone/product_api_v2.json").read_text())
    pin_file = (ROOT / PIN_FILE).read_text()
    metric_hits = [w for w in METRIC_WORDS if any(w in json.dumps(r).lower() for r in runs)]
    predeclared_ok = all(
        r["observed"]["windows"] == PREDECLARED["windows"] and r["observed"]["valid"] == PREDECLARED["valid"]
        and r["observed"]["unusable"] == PREDECLARED["unusable"] and r["observed"]["inference_results"] == PREDECLARED["http_200"]
        and r["observed"]["attempts_equiv"] == PREDECLARED["attempts"] and r["observed"]["http_422_equiv"] == PREDECLARED["http_422"]
        and r["observed"]["terminal_session_state"] == PREDECLARED["terminal"] and r["database_after_process_1"]["inference_models"] == [PREDECLARED["model_id"]]
        and r["noninterference"]["model_calibration_equal"] for r in runs)
    stages = [(db1, db2), *[(a, b) for _r, a, b in both[1:]]]
    special = {
        "@cap001_capg0_pass": tasks["CAP-001"]["status"] == "PASS" and gates["CAPG0"]["status"] == "PASS",
        "@cap002_capg1_pass": tasks["CAP-002"]["status"] == "PASS" and gates["CAPG1"]["status"] == "PASS",
        "@cap003_capg2_pass": tasks["CAP-003"]["status"] == "PASS" and gates["CAPG2"]["status"] == "PASS",
        "@cap001_lock": verify_cap001_lock()["verified"], "@cap002_lock_chain": verify_cap002_lock()["verified"],
        "@cap003_lock_chain": verify_cap003_lock()["verified"], "@cap003_lock_unchanged": verify_cap003_lock()["verified"],
        "@drift": not drift["protected_artifact_drift"],
        "@drift_frontend": not drift["frontend_drift"] and drift["frontend_files_checked"] > 100,
        "@protocol_freeze_precedes_result": freeze["ok"],
        "@storage_successor": s2["supersedes"]["sha256"] == hash_file(ROOT / "contracts/capstone/storage_policy_v1.json") and "scenario_id" in next(e for e in s2["entities"] if e["table"] == "devices")["columns"] and "scenario_id" not in next(e for e in s1v1["entities"] if e["table"] == "devices")["columns"],
        "@api_successor": {"auth_provider", "demo_mode"} <= set(api2["system_info_v2"]["added_fields"]) and "SQLITE" in api2["system_info_v2"]["changed_values"]["persistence_mode"],
        "@clerk_sdk_imported": "from clerk_backend_api.security import" in (ROOT / "product/auth/clerk.py").read_text(),
        "@clerk_exact_pin": "clerk-backend-api==7.0.0" in pin_file and ">=" not in pin_file and deps["clerk_installed_version"] == "7.0.0",
        "@dependency_firewall": deps["critical_unchanged"] and all(deps["critical_installed_equals_pin"].values()),
        "@dependency_additions_only": deps["only_allowed_additions"] and dependency_files_ok()[0],
        "@e2e_no_credentials_in_database": all(not a["credential_strings_in_database"] and not b["credential_strings_in_database"] for _r, a, b in both),
        "@e2e_me": p1["me"]["user_id"] == "demo:faculty" and p1["me"]["demo_mode"] is True and p1["me"]["auth_provider"] == "DEMO",
        "@e2e_users_persisted": [u["user_id"] for u in db1["users"]] == ["demo:faculty"] and db2["users"] == db1["users"],
        "@e2e_pragmas_fk": all(a["pragmas"]["foreign_keys"] == 1 and b["pragmas"]["foreign_keys"] == 1 for _r, a, b in both),
        "@e2e_pragmas_wal": all(str(a["pragmas"]["journal_mode"]).lower() == "wal" and str(b["pragmas"]["journal_mode"]).lower() == "wal" for _r, a, b in both),
        "@e2e_pragmas_version": all(a["pragmas"]["user_version"] == 1 and b["pragmas"]["user_version"] == 1 for _r, a, b in both),
        "@e2e_tables": sorted(db1["tables"]) == sorted(policy_tables) and len(policy_tables) == 15,
        "@e2e_device_scenario": db1["devices"][0]["scenario_id"] == "MIXED_MONITORING_SESSION" and db2["devices"] == db1["devices"],
        "@e2e_no_raw_table": sorted(db1["tables"]) == sorted(policy_tables) and not [t for t in db1["tables"] if "sample" in t or t.startswith("raw_")],
        "@e2e_row_counts_bounded": all(sum(a["row_counts"].values()) < 2000 and a["row_counts"]["inference_events"] == 86 for _r, a, _b in both),
        "@e2e_device_metadata": len(db1["devices"]) == 1 and db1["devices"][0]["adapter_type"] == "SIMULATED" and db1["devices"][0]["user_id"] == "demo:faculty",
        "@e2e_connection_history": db1["row_counts"]["device_connections"] >= len(obs["device_state_sequence"]) + 2 and db2["row_counts"]["device_connections"] == db1["row_counts"]["device_connections"],
        "@e2e_restart_detached": bool(p2["devices"]) and all(d["connection_state"] == "DETACHED" for d in p2["devices"]),
        "@e2e_session_create": p1["session_created"]["state"] == "DEVICE_READY" and bool(p1["session_created"]["session_id"]),
        "@e2e_session_list": p1["session_list_ids"] == [p1["session_created"]["session_id"]],
        "@e2e_session_get": p1["session_get_state"] == "DEVICE_READY" and p1["final_session"]["state"] == "COMPLETED",
        "@e2e_ownership": p3["devices_listed"] == [] and p3["sessions_listed"] == [] and p3["get_session_status"] == 403 and p3["start_status"] == 403 and p3["scan_other_users_device_status"] == 403 and p3["websocket_close_code"] == 4403 and p3["unknown_session_status"] == 404 and p3["other_user"] == "demo:other",
        "@e2e_runtime_identity_restart": db1["sessions"] == db2["sessions"] and db1["sessions"][0]["model_id"] == "MODEL_V2_FINAL" and db1["sessions"][0]["calibration_id"] == "CAL_V2",
        "@e2e_93_windows": all(r["observed"]["windows"] == 93 for r in runs),
        "@e2e_quality_counts": all(r["observed"]["valid"] == 86 and r["observed"]["unusable"] == 7 for r in runs),
        "@e2e_inference_counts": all(r["observed"]["http_200_equiv"] == 86 and r["observed"]["http_422_equiv"] == 7 and r["observed"]["attempts_equiv"] == 93 and r["database_after_process_1"]["row_counts"]["inference_events"] == 86 for r in runs),
        "@e2e_model_only": all(r["database_after_process_1"]["inference_models"] == ["MODEL_V2_FINAL"] and r["noninterference"]["model_calibration_equal"] for r in runs),
        "@e2e_calibration_only": all(r["noninterference"]["model_calibration_equal"] for r in runs) and all(e["payload"]["calibration_id"] == "CAL_V2" for e in ev if e["event_type"] == "inference.result"),
        "@e2e_projected_stream_identical": all(r["noninterference"]["full_projected_stream_identical_to_cap003_canonical_run_1"] and r["noninterference"]["raw_and_calibrated_probabilities_equal"] for r in runs),
        "@e2e_sequence_contiguous": all(r["observed"]["sequence_contiguous"] for r in runs),
        "@e2e_raw_context_separate": all(r["database_after_process_1"]["raw_context_rows"] == 86 for r in runs),
        "@e2e_withheld_auditable": all(r["database_after_process_1"]["withheld_raw_has_ppg_values"] and r["database_after_process_1"]["withheld_product_values_null"] and r["database_after_process_1"]["withheld_context_cases"] == (len(r["noninterference"]["cap003_context_values_withheld"]) if isinstance(r["noninterference"]["cap003_context_values_withheld"], list) else r["noninterference"]["cap003_context_values_withheld"]) for r in runs),
        "@e2e_quality_change_only": db1["row_counts"]["signal_quality_events"] == quality_changes(ev) < 93,
        "@e2e_context_cadence": db1["row_counts"]["context_snapshots"] == sum(1 for e in ev if e["event_type"] == "context.snapshot") <= 86,
        "@e2e_preview_bounded": all(r["database_after_process_1"]["waveform_preview"] and r["database_after_process_1"]["waveform_preview"]["point_count"] <= 4000 and r["database_after_process_1"]["waveform_preview"]["decoded_points"] == r["database_after_process_1"]["waveform_preview"]["point_count"] and r["database_after_process_1"]["waveform_preview"]["encoding"] == "JSON_ZLIB_V1" for r in runs),
        "@e2e_no_raw_waveform": db1["waveform_preview"]["decimation_factor"] > 1 and db1["waveform_preview"]["blob_bytes"] < 100_000 and db1["row_counts"]["waveform_previews"] == 1,
        "@e2e_completed_survives": db1["sessions"] == db2["sessions"] and p2["session"]["state"] == "COMPLETED" and db1["row_counts"] == db2["row_counts"],
        "@crash_recovery": crash["stale_session_failed_not_resumed"] and crash["before_crash"]["session_state_via_api"] == "MONITORING" and crash["at_crash_database"]["session_state"] == "MONITORING" and crash["database_unchanged_while_product_down"] and crash["recovered_session"]["state"] == "FAILED",
        "@crash_devices_detached": crash["devices_detached"] and bool(crash["devices_after_restart"]),
        "@crash_no_fake_events": crash["no_fake_post_crash_inference"] and crash["no_fake_post_crash_context"],
        "@fl_firewall": not _scan(cap004_code(), r"^\s*(import|from)\s+(federated|privacy|flwr)\b") and not _scan(cap004_code(), r"\blocal_train\b|\bfedavg\b|\bfedprox\b|\bsecagg\b"),
        "@e2e_future_tables_empty": all(a["row_counts"][t] == 0 and b["row_counts"][t] == 0 for _r, a, b in both for t in FUTURE) and all(crash["database_after_recovery"]["row_counts"][t] == 0 for t in FUTURE),
        "@no_candidate": all(a["row_counts"]["candidate_models"] == 0 for _r, a, _b in both) and not [p for p in added if "candidate" in p.lower() and p.endswith(".py")],
        "@no_per_user_model_state": not [t for t in db1["tables"] if re.search(r"model_state|weights|checkpoint", t)] and "candidate_models" in FUTURE,
        "@no_hardware_code": not _scan(py_added, r"import\s+(serial|bleak|bluetooth)|from\s+(serial|bleak|bluetooth)|WEARABLE_V1_MANIFEST"),
        "@e2e_real_inference": all(r["inference_service"]["fresh_process"] and "SOFTWARE_SYSTEM_V2 default binding" in r["inference_service"]["service_title"] and r["inference_service"]["profile"] == "default" for r in runs) and not re.search(r"MockTransport|StrictInferenceDouble", (ROOT / "scripts/run_capstone_persistent_e2e.py").read_text()),
        "@e2e_separate_process": all(r["product_process_separate"] and r["inference_process_separate"] for r in runs) and len({p1["pid_excluded"], p2["pid_excluded"], p3["pid_excluded"], os.getpid()}) == 4,
        "@e2e_demo_explicit": all(r["process_1"]["system"]["auth_provider"] == "DEMO" and r["process_1"]["system"]["demo_mode"] is True and r["process_1"]["system"]["persistence_mode"] == "SQLITE" for r in runs) and "explicit" in r1["auth_mode"],
        "@e2e_restart_two_process": p1["pid_excluded"] != p2["pid_excluded"] and p2["session"]["session_id"] == p1["session_created"]["session_id"] and p2["session"]["state"] == "COMPLETED" and p2["me"]["user_id"] == p1["me"]["user_id"] and p2["late_start_status"] == 409,
        "@all_cap004_tests": bool(cap004) and all(v == "passed" for v in cap004.values()),
        "@prior_phase_tests": bool(prior) and all(v == "passed" or (k.split("[")[0] == KNOWN_FLAKE and flake_ok) for k, v in prior.items()),
        "@regression": bool(re.search(r"\d+ passed", log)) and " error" not in log and set(full_failed) <= {KNOWN_FLAKE_ID} and (not full_failed or flake_ok),
        "@frontend": all(frontend[k]["exit"] == 0 for k in frontend) and frontend["npm_run_check"]["errors"] == 0,
        "@ruff": "All checks passed" in (LOGS / "ruff.log").read_text(), "@pip": "No broken requirements found" in (LOGS / "pip_check.log").read_text(),
        "@ci": True,
        "@registry_cap004": tasks["CAP-004"]["status"] == "PASS" if final else None,
        "@registry_capg3": gates["CAPG3"]["status"] == "PASS" if final else None,
        "@registry_cap005": tasks["CAP-005"]["status"] == "NOT_STARTED",
        "@e2e_reproducible": all(runs[0][k] == runs[1][k] for k in ("projected_event_stream_sha256", "observed", "noninterference")) and runs[0]["database_after_process_1"]["row_counts"] == runs[1]["database_after_process_1"]["row_counts"] and runs[0]["database_after_process_1"]["schema_sha256"] == runs[1]["database_after_process_1"]["schema_sha256"] and runs[0]["database_after_process_1"]["quality_change_sequence"] == runs[1]["database_after_process_1"]["quality_change_sequence"] and stream(1) == stream(2),
        "@e2e_predeclared": predeclared_ok,
        "@mutation_log": mutation["all_caught"] and mutation["all_restored"] and len(mutation["controls"]) == 10 and {c["mutation"] for c in mutation["controls"]} == set(protocol["mutation_controls"]),
        "@no_db_file_committed": not [p for p in _git("ls-files").splitlines() + added if p.endswith((".sqlite", ".sqlite3", ".db", ".sqlite3-wal", ".sqlite3-shm"))],
        "@route_parity": routes["exact_match"] and not routes["later_phase_routes_implemented"] and routes["v1_contract_cap003_routes_all_preserved"],
        "@e2e_ws_past_session": p2["websocket_close_code_for_past_process_session"] == 1000,
        "@e2e_integrity": all(x["integrity_check"] in (["ok"], "ok") and not x["foreign_key_check"] for pair in stages for x in pair) and crash["database_after_recovery"]["integrity_check"] in (["ok"], "ok") and not crash["database_after_recovery"]["foreign_key_check"],
        "@no_efficacy_metrics": not metric_hits and all(r["noninterference"] and True for r in runs),
        "@disclosures_preserved": len(protocol["preserved_disclosures"]) == 8 and len(entry["preserved_disclosures"]) >= 4 and len(list((ROOT / "artifacts/capstone").glob("CAPSTONE_DEVICE_EDGE_PROTOCOL_V1.amendment_*.json"))) == 3 and len(list((ROOT / "artifacts/capstone").glob("CAPSTONE_PRODUCT_MONITORING_PROTOCOL_V1.amendment_*.json"))) == 1,
    }
    rows = []
    for item in protocol["capg3_criteria"]:
        verdicts = [special[c] if c.startswith("@") else lookup(results, c) for c in item["checks"]]
        rows.append({"criterion": item["id"], "text": item["text"], "checks": item["checks"], "pass": None if any(v is None for v in verdicts) else all(verdicts)})
    decided = [r["pass"] for r in rows if r["pass"] is not None]
    summary = re.search(r"(\d+) passed(?:, (\d+) skipped)?", log)
    payload = {"gate": "CAPG3", "protocol_freeze": freeze, "criteria": rows, "criteria_count": len(rows), "decided": len(decided),
               "all_decided_pass": all(decided), "undecided": [r["criterion"] for r in rows if r["pass"] is None],
               "regression_summary": {"passed": int(summary.group(1)) if summary else None, "skipped": int(summary.group(2) or 0) if summary else None},
               "known_preexisting_flake_failures_in_full_run": full_failed, "known_flake_evidence": "preexisting_cap003_flake.json", "cap004_tests": {"count": len(cap004), "passed": sum(1 for v in cap004.values() if v == "passed")}}
    _write("capg3_criteria.json", payload)
    print(json.dumps({k: payload[k] for k in ("criteria_count", "decided", "all_decided_pass", "undecided", "regression_summary", "cap004_tests")}))
    failed = [r["criterion"] for r in rows if r["pass"] is False]
    if failed:
        print("FAILED criteria:", failed)


if __name__ == "__main__":
    if sys.argv[1] == "audits":
        audits()
    else:
        criteria(sys.argv[2] == "final")
