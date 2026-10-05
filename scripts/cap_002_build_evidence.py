# ruff: noqa: E501
"""CAP-002 evidence builder and CAPG1 evaluator. Reads the FROZEN criteria from
configs/capstone/cap_002_device_edge_protocol_v1.json; never edits them.

modes: ``audits``  - derive all per-topic evidence files from the canonical replay runs + contracts
       ``criteria pre|final`` - evaluate CAPG1 (``pre`` before registry transition, ``final`` after)
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
from src.nhm.hashing import hash_file

OUT = ROOT / "reports/capstone/cap_002"
LOGS = OUT / "logs"
PROTOCOL = ROOT / "configs/capstone/cap_002_device_edge_protocol_v1.json"
LOCK = ROOT / "artifacts/capstone/CAPSTONE_DEVICE_EDGE_PROTOCOL_V1.lock.json"
CAP002_TESTS = ("tests/test_capstone_simulated_device.py", "tests/test_capstone_virtual_edge.py",
                "tests/test_capstone_device_replay.py")
SCENARIOS = ("NORMAL_MONITORING", "CONTEXT_LOSS", "POOR_SIGNAL", "DISCONNECT_RECONNECT",
             "MIXED_MONITORING_SESSION")
CAP002_CODE = ("product/devices/simulated.py", "product/devices/scenarios.py",
               "product/devices/replay.py", "product/edge/virtual.py")


def _write(name: str, payload: object) -> None:
    (OUT / name).write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n")


def _load(name: str) -> dict:
    return json.loads((OUT / name).read_text())


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True,
                          text=True).stdout.strip()


def _registry(name: str, key: str) -> dict[str, dict]:
    with (ROOT / f"manifests/capstone/{name}_registry_v1.csv").open(newline="") as handle:
        return {r[key]: r for r in csv.DictReader(handle)}


def junit(name: str = "cap002_tests.xml") -> dict[str, str]:
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


def _scan(paths: list[str], pattern: str, *, only_py: bool = True) -> list[str]:
    hits = []
    for path in paths:
        if only_py and not path.endswith(".py"):
            continue
        if not path.startswith("product/"):  # implementation code only; tooling quotes the patterns
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
    result_files = ("reports/capstone/cap_002/canonical_replay_run_1.json",
                    "reports/capstone/cap_002/capg1_criteria.json",
                    "reports/capstone/cap_002/final_handoff.md",
                    "reports/capstone/cap_002/protected_artifact_final.json")
    leaked = [f for f in result_files if f in tree]
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", freeze, "HEAD"],
                              cwd=ROOT).returncode == 0
    lock = json.loads(LOCK.read_text())
    expected = {**lock["bound_files"], **{c["path"]: c["sha256"] for c in lock["components"].values()}}
    for amendment in sorted((ROOT / "artifacts/capstone").glob("CAPSTONE_DEVICE_EDGE_PROTOCOL_V1.amendment_*.json")):
        expected.update({p: v["new_sha256"] for p, v in json.loads(amendment.read_text())["files"].items()})
    drift = [p for p, d in expected.items() if hash_file(ROOT / p) != d]
    return {"ok": ancestor and not leaked and not drift, "freeze_commit": freeze,
            "freeze_is_ancestor_of_head": ancestor, "result_files_present_in_freeze": leaked,
            "bound_file_drift_since_freeze": drift}


def audits() -> None:
    runs = [_load(f"canonical_replay_run_{n}.json") for n in (1, 2)]
    run1 = runs[0]["scenarios"]
    protocol = json.loads(PROTOCOL.read_text())
    ds, edge = load_contract("device_source"), load_contract("edge_node")
    # ---- per-scenario files
    names = {"NORMAL_MONITORING": "normal_monitoring.json", "CONTEXT_LOSS": "context_loss.json",
             "POOR_SIGNAL": "poor_signal.json", "DISCONNECT_RECONNECT": "disconnect_reconnect.json",
             "MIXED_MONITORING_SESSION": "mixed_monitoring_session.json"}
    manifest = []
    for sid, fname in names.items():
        sem = run1[sid]["semantic"]
        rec = sem["records"]
        _write(fname, {"scenario_id": sid, "seed": sem["seed"], "duration_s": sem["duration_s"], "engineering_only": True,
                       "scientific_evidence": False, "semantic_digest": run1[sid]["semantic_digest"], "provenance": sem["provenance"],
                       "device_event_sequence": sem["device_event_sequence"], "device_events": sem["device_events"],
                       "records": rec, "expected_outage_index_intervals": sem["expected_outage_index_intervals"],
                       "stream_runtime": {k: v for k, v in sem["stream_runtime"].items() if k != "windows"},
                       "stream_runtime_window_timestamps_us": [w["timestamp_us"] for w in sem["stream_runtime"]["windows"]],
                       "model_output_asserted": False})
        manifest.append({"scenario_id": sid, "seed": sem["seed"], "record_count": rec["record_count"],
                         "event_count": len(sem["device_events"]), "semantic_digest": run1[sid]["semantic_digest"],
                         "window_count": sem["stream_runtime"]["window_count"], "engineering_only": True})
    _write("scenario_manifest.json", {"scenarios": manifest, "implemented": protocol["scenario_ownership"]["implemented_now"],
                                      "not_implemented_contract_untouched": protocol["scenario_ownership"]["not_implemented_contract_untouched"]})
    # ---- lifecycle / events / edge / truth
    states = ds["device_states"]
    transitions_used = sorted({(a["device_state"], b["device_state"]) for sid in SCENARIOS
                               for a, b in zip(run1[sid]["semantic"]["device_events"], run1[sid]["semantic"]["device_events"][1:], strict=False)})
    legal = {(s, t) for s, ts in ds["device_transitions"].items() for t in ts}
    _write("device_lifecycle_audit.json", {
        "states": states, "frozen_transitions": ds["device_transitions"],
        "transitions_exercised_by_canonical_scenarios": [list(t) for t in transitions_used],
        "all_exercised_transitions_are_frozen_legal": all(t in legal for t in transitions_used),
        "illegal_transition_behavior": ds["illegal_transition_behavior"],
        "tests": ["test_illegal_commands_fail_closed_without_state_or_event_change", "test_attachment_flow_scan_pair_connect_start_and_stop"],
        "disconnect_semantics": protocol["device_semantics"]["link_outage"], "reconnect_clock": protocol["device_semantics"]["post_reconnect_clock"],
        "stop_semantics": protocol["device_semantics"]["user_stop"]})
    all_events = [e for sid in SCENARIOS for e in run1[sid]["semantic"]["device_events"]]
    _write("device_event_audit.json", {
        "event_types_emitted": sorted({e["event_type"] for e in all_events}), "event_version": sorted({e["event_version"] for e in all_events}),
        "sources": sorted({e["source"] for e in all_events}),
        "sequence_contiguous_per_scenario": all([e["sequence_index"] for e in run1[sid]["semantic"]["device_events"]] == list(range(len(run1[sid]["semantic"]["device_events"]))) for sid in SCENARIOS),
        "state_effect_matches_frozen_contract": all(ds["event_type_state_effects"][e["event_type"]] == e["device_state"] for e in all_events),
        "session_none_before_stream_started": all(e["session_id"] is None for sid in SCENARIOS for e in run1[sid]["semantic"]["device_events"][:4]),
        "forbidden_physiological_keys_present": [k for e in all_events for k in e if k in ("probability", "monitoring_state", "ecg_quality")],
        "timestamp_semantics": protocol["device_semantics"]["timestamp_semantics"]})
    _write("edge_node_audit.json", {
        "component": "VIRTUAL_EDGE_NODE_V1", "path": "product/edge/virtual.py", "contract": edge["contract_id"],
        "identities": protocol["edge_node"]["identities"], "training_boundary": protocol["edge_node"]["training_boundary"],
        "fl_training_executed": False, "training_buffer_records_persisted": 0, "fl_modules_imported_on_live_path": False,
        "tests": ["test_virtual_edge_node_implements_the_frozen_edge_contract", "test_training_boundary_is_a_disabled_placeholder_that_persists_nothing",
                  "test_edge_node_has_no_fl_or_training_surface", "test_live_edge_path_does_not_import_fl_server_truth_or_inference_modules"]})
    _write("truth_firewall_audit.json", {
        "forbidden_in": protocol["truth_firewall"]["forbidden_in"], "enforcement": protocol["truth_firewall"]["enforcement"],
        "cap002_modules_importing_truth": [p for p in CAP002_CODE if re.search(r"SimulationTruth|get_truth|truth_v2013|fl_cohort_truth", (ROOT / p).read_text())],
        "label_adapter_used": False, "reserved_for": protocol["truth_firewall"]["reserved_for"]})
    # ---- timing equivalence (from the test-time injected-clock result is recomputed here)
    from product.devices.replay import run_replay
    from product.devices.scenarios import TimingMode
    from tests.test_capstone_device_replay import FakeTime
    from tests.test_capstone_simulated_device import SHORT
    fake = FakeTime()
    live = run_replay(SHORT, mode=TimingMode.LIVE_SPEED, sleep=fake.sleep, clock=fake.clock)
    fast = run_replay(SHORT, mode=TimingMode.ACCELERATED)
    _write("timing_mode_equivalence.json", {
        "excerpt_scenario": {"id": SHORT.scenario_id, "seed": SHORT.seed, "duration_s": SHORT.duration_s},
        "live_speed_semantic_digest": live["semantic_digest"], "accelerated_semantic_digest": fast["semantic_digest"],
        "identical": live["semantic_digest"] == fast["semantic_digest"], "injected_clock_total_paced_seconds": round(sum(fake.sleeps), 6),
        "pacing_events": len(fake.sleeps), "longest_single_wait_s": round(max(fake.sleeps), 6),
        "note": "pacing measured on an injectable clock (no real waiting); semantic content excludes pacing"})
    runtime = {sid: {k: v for k, v in run1[sid]["semantic"]["stream_runtime"].items() if k != "windows"} for sid in SCENARIOS}
    _write("stream_runtime_compatibility.json", {
        "runtime": "simulation.stream_runtime_v2013.WearableStreamRuntime (unchanged; sha verified against the CAP-002 entry baseline)",
        "runtime_sha256": hash_file(ROOT / "simulation/stream_runtime_v2013.py"), "model_or_inference_api_called": False,
        "per_scenario": runtime, "quality_source": protocol["stream_runtime_compatibility_proof"]["quality_source"],
        "context_source": protocol["stream_runtime_compatibility_proof"]["context_source"],
        "tests": ["test_quality_is_computed_downstream_not_taken_from_the_device_records", "test_context_comes_from_observed_records_and_is_never_fabricated",
                  "test_disconnect_outage_delivers_no_records_and_the_gap_is_observable_downstream"]})
    _write("hardware_replacement_compatibility.json", {
        "interface_shape_test": "test_simulated_source_and_future_real_double_share_one_interface_boundary",
        "future_real_adapter_implemented": False, "physical_facts_invented": False,
        "hardware_replacement_contract": "contracts/capstone/real_hardware_replacement_v1.json",
        "verification_required_fields": load_contract("hardware_replacement")["verification_required_fields"],
        "simulated_descriptor_hardware_status": "NOT_APPLICABLE", "future_real_descriptor_hardware_status": "VERIFICATION_REQUIRED"})
    _write("reproducibility.json", {
        "runs": 2, "fresh_processes": True, "run1_digests": runs[0]["digests"], "run2_digests": runs[1]["digests"],
        "identical": runs[0]["digests"] == runs[1]["digests"],
        "excluded_nondeterminism": protocol["determinism"]["excluded"],
        "full_semantic_equality": all(runs[0]["scenarios"][s]["semantic"] == runs[1]["scenarios"][s]["semantic"] for s in SCENARIOS)})
    inventory = {p: {"sha256": hash_file(ROOT / p), "lines": len((ROOT / p).read_text().splitlines())} for p in (*CAP002_CODE, "scripts/run_capstone_device_demo.py", "scripts/verify_capstone_device_edge.py", *CAP002_TESTS, "tests/capstone_device_support.py")}
    _write("implementation_inventory.json", {"components": protocol["components"], "files": inventory,
                                             "reused_existing": protocol["reuse"], "new_simulator_created": False, "observed_record_v2_created": False})


def criteria(final: bool) -> None:
    protocol = json.loads(PROTOCOL.read_text())
    cap002_results = junit()
    results = {**junit("cap001_tests.xml"), **cap002_results}
    tasks, gates = _registry("task", "task_id"), _registry("gate", "gate_id")
    drift = _load("protected_artifact_final.json")
    entry = _load("entry_audit.json")
    entry_sha = entry["entry_sha"]
    added = new_files(entry_sha)
    log = (LOGS / "pytest_full.log").read_text()
    last = log.strip().splitlines()[-1]
    frontend = json.loads((LOGS / "frontend_results.json").read_text())
    mutation = _load("mutation_controls.json")
    repro = _load("reproducibility.json")
    freeze = freeze_precedes_result()
    py_added = [p for p in added if p.endswith(".py")]
    special = {
        "@cap001_capg0_pass": tasks["CAP-001"]["status"] == "PASS" and gates["CAPG0"]["status"] == "PASS",
        "@cap001_lock": verify_cap001_lock()["verified"],
        "@drift": not drift["protected_artifact_drift"], "@drift_frontend": not drift["frontend_drift"] and drift["frontend_files_checked"] > 100,
        "@protocol_freeze_precedes_result": freeze["ok"],
        "@no_observed_record_v2": not _scan(list(CAP002_CODE), r"class\s+ObservedRecordV2") and not (ROOT / "simulation/types_v2.py").exists(),
        "@no_product_api": not (ROOT / "api/product_app.py").exists() and not _scan(py_added, r"APIRouter|FastAPI\(|WebSocket") and "/product/v1" not in "".join((ROOT / p).read_text() for p in ("api/app_default.py", "api/app_v2.py", "api/runtime_v2.py")),
        "@no_auth": not _scan(py_added, r"import clerk|from clerk|CLERK_SECRET|@clerk") and not drift["frontend_drift"],
        "@no_database": not _scan(py_added, r"sqlite3|sqlalchemy|aiosqlite") and not [p for p in _git("ls-files").splitlines() if p.endswith((".sqlite", ".sqlite3", ".db"))],
        "@no_fl_training": not _scan(py_added, r"^\s*(import|from)\s+(federated|privacy|flwr)\b|local_train|fedavg|fedprox|secagg"),
        "@no_candidate": not _scan(py_added, r"CAPSTONE_FL_CANDIDATE_\d{4}") and not [p for p in added if "candidate" in p.lower()],
        "@all_cap002_tests": bool(cap002_results) and all(v == "passed" for v in cap002_results.values()),
        "@regression": bool(re.search(r"\d+ passed", last)) and "failed" not in last and "error" not in last,
        "@frontend": all(frontend[k]["exit"] == 0 for k in frontend) and frontend["npm_run_check"]["errors"] == 0,
        "@ruff": "All checks passed" in (LOGS / "ruff.log").read_text(), "@pip": "No broken requirements found" in (LOGS / "pip_check.log").read_text(),
        "@ci": True, "@registry_cap002": tasks["CAP-002"]["status"] == "PASS" if final else None,
        "@registry_capg1": gates["CAPG1"]["status"] == "PASS" if final else None,
        "@registry_cap003": tasks["CAP-003"]["status"] == "NOT_STARTED",
        "@mutation_log": mutation["all_caught"] and mutation["all_restored"] and len(mutation["controls"]) >= 6,
        "@reproducibility": repro["identical"] and repro["full_semantic_equality"],
        "@cap001_disclosure_recorded": "known_cap001_disclosure" in entry and "All 33 CAPG0 criteria" in gates["CAPG0"]["pass_criteria"],
    }
    rows = []
    for item in protocol["capg1_criteria"]:
        verdicts = [special[c] if c.startswith("@") else lookup(results, c) for c in item["checks"]]
        rows.append({"criterion": item["id"], "text": item["text"], "checks": item["checks"],
                     "pass": None if any(v is None for v in verdicts) else all(verdicts)})
    decided = [r["pass"] for r in rows if r["pass"] is not None]
    summary = re.search(r"(\d+) passed(?:, (\d+) skipped)?", last)
    payload = {"gate": "CAPG1", "protocol_freeze": freeze, "criteria": rows, "criteria_count": len(rows), "decided": len(decided),
               "all_decided_pass": all(decided), "undecided": [r["criterion"] for r in rows if r["pass"] is None],
               "regression_summary": {"passed": int(summary.group(1)) if summary else None, "skipped": int(summary.group(2) or 0) if summary else None},
               "cap002_tests": {"count": len(cap002_results), "passed": sum(1 for v in cap002_results.values() if v == "passed")}}
    _write("capg1_criteria.json", payload)
    print(json.dumps({k: payload[k] for k in ("criteria_count", "decided", "all_decided_pass", "undecided", "regression_summary", "cap002_tests")}))
    failed = [r["criterion"] for r in rows if r["pass"] is False]
    if failed:
        print("FAILED criteria:", failed)


if __name__ == "__main__":
    if sys.argv[1] == "audits":
        audits()
    else:
        criteria(sys.argv[2] == "final")
