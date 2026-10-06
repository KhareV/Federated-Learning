# ruff: noqa: E501
"""Build the CAP-010 derived audit evidence from the canonical runs, the recorded test report and the repository.
Reads reports/capstone/cap_010/*.json written by run_capstone_full_demo_e2e / cap_010_test_report; writes the audits."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.cap_010_runbook_audit import RUNBOOK, audit_runbook

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/capstone/cap_010"
BINDING = ROOT / "configs/capstone/cap_010_full_demo_binding_v1.json"
PROTOCOL = ROOT / "configs/capstone/cap_010_faculty_demo_protocol_v1.json"


def rd(name: str) -> dict:
    return json.loads((OUT / name).read_text())


def wr(name: str, payload: dict) -> None:
    (OUT / name).write_text(json.dumps(payload, indent=1, sort_keys=True, default=str) + "\n")


def tests_matching(report: dict, needles: list[str]) -> dict[str, str]:
    return {k: v for k, v in report["targeted"]["tests"].items() if any(n in k for n in needles)}


def group(name: str, report: dict, needles: list[str], extra: dict | None = None) -> None:
    found = tests_matching(report, needles)
    wr(name, {"status": "PASS" if found and all(v == "passed" for v in found.values()) else "FAIL", "tests": found, **(extra or {})})


def external(run: dict) -> list[str]:
    return list(run["browser"]["network"]["external"]) + list((run.get("restart") or {}).get("network", {}).get("external", []))


def main() -> int:
    report = rd("test_report.json")
    run1, run2 = rd("full_browser_demo_run_1.json"), rd("full_browser_demo_run_2.json")
    protocol = json.loads(PROTOCOL.read_text())
    # ---- demo governance audits (from the recorded unit/integration tests) ----
    group("full_demo_binding_audit.json", report, ["test_full_demo_binding_matches_the_frozen_contract"], {"binding": BINDING.name})
    group("workspace_safety_audit.json", report, ["test_capstone_demo_workspace"])
    group("process_supervision_audit.json", report, ["test_an_unexpected_child_death", "test_ctrl_c_style_stop", "test_grandchildren_of_a_service", "test_a_child_that_exits_before_ready", "test_a_service_that_never_becomes_ready", "test_ready_only_after"])
    group("launcher_audit.json", report, ["test_the_faculty_stack_is_exactly_three_services", "test_the_launcher_has_no_profile_or_timing_option", "test_the_launcher_never_issues_a_write_request"],
          {"services": ["inference", "product", "frontend"], "default_ports": run1["ports"], "command": run1["launcher_command"]})
    group("launcher_negative_tests.json", report, ["test_missing_demo_auth_acknowledgement", "test_the_cli_subprocess_refuses", "test_an_occupied_port", "test_unsafe_reset_is_refused_by_the_cli"])
    group("prewarm_audit.json", report, ["test_prewarm_is_a_read_only_preparation"], {"canonical_prewarm": run1["prewarm"]})
    # ---- preflight (the real environment, via the real CLI; no workspace is created) ----
    # the stack's own build step (writes the frontend build stamp that preflight verifies), then the real preflight
    built = subprocess.run([sys.executable, "-c", "from scripts.run_capstone_faculty_demo import build_frontend; build_frontend()"], cwd=ROOT, capture_output=True, text=True,
                           env={**__import__("os").environ, "PYTHONPATH": "src:."}, timeout=1800)
    pf = subprocess.run([sys.executable, "-m", "scripts.run_capstone_faculty_demo", "--preflight-only", "--acknowledge-demo-auth"], cwd=ROOT, capture_output=True, text=True,
                        env={**__import__("os").environ, "PYTHONPATH": "src:."}, timeout=600)
    group("preflight_audit.json", report, ["test_capstone_demo_preflight"], {"launcher_build_returncode": built.returncode, "real_preflight_returncode": pf.returncode, "real_preflight_output_tail": pf.stdout.strip().splitlines()[-12:]})
    pa = rd("preflight_audit.json")
    pa["status"] = "PASS" if pa["status"] == "PASS" and pf.returncode == 0 else "FAIL"
    wr("preflight_audit.json", pa)
    # ---- runbook ----
    text = RUNBOOK.read_text()
    audit = audit_runbook(text)
    wr("faculty_runbook_audit.json", {"status": "PASS" if not audit["missing_required"] and not audit["unnegated_watched_claims"] else "FAIL", **audit, "runbook": "docs/capstone/FACULTY_DEMO_RUNBOOK_V1.md",
                                     "runbook_lines": len(text.splitlines())})
    wr("claim_audit.json", {"status": "PASS" if not audit["unnegated_watched_claims"] and not audit["missing_required"] else "FAIL", "runbook_violations": audit["unnegated_watched_claims"], "runbook_missing_required": audit["missing_required"],
                           "claim_allowed": protocol["claim_boundary"]["allowed"], "not_claimed": protocol["claim_boundary"]["not_claimed"],
                           "hardware_status": "VERIFICATION_REQUIRED", "personalization_answer": "NO", "mutation_tests": tests_matching(report, ["test_runbook_claim_audit_rejects_every_overclaim_mutation"])})
    # ---- reproducibility ----
    same = run1["semantic_sha256"] == run2["semantic_sha256"] and run1["semantic_projection"] == run2["semantic_projection"]
    wr("full_demo_reproducibility.json", {"status": "PASS" if same else "FAIL", "run_1_semantic_sha256": run1["semantic_sha256"], "run_2_semantic_sha256": run2["semantic_sha256"],
                                          "projections_equal": run1["semantic_projection"] == run2["semantic_projection"], "fresh_workspaces": True,
                                          "excluded_from_digest": ["session ids", "federation run ids", "timestamps", "latency/elapsed seconds", "ports are fixed defaults", "process ids", "log text", "workspace path",
                                                                  "screenshots", "machine-specific wall-clock telemetry", "device connection state after restart (runtime-only by the CAP-004 restart policy)"],
                                          "included_in_digest": ["runtime identity", "session/summary/timeline projections", "federation config and rounds", "update digests", "candidate digests", "research payload hashes", "research catalog file sha256"]})
    # ---- offline ----
    ext = external(run1) + external(run2)
    wr("offline_network_audit.json", {"status": "PASS" if not ext and not run1["browser"]["network"]["blockedExternal"] and not run2["browser"]["network"]["blockedExternal"] else "FAIL",
                                     "external_network_policy": "ACTIVE_CDP_REQUEST_INTERCEPTION_LOOPBACK_ONLY", "external_requests": ext,
                                     "blocked_external_attempts": run1["browser"]["network"]["blockedExternal"] + run2["browser"]["network"]["blockedExternal"],
                                     "origins": run1["browser"]["network"]["origins"], "request_count_run_1": run1["browser"]["network"]["requestCount"], "request_count_run_2": run2["browser"]["network"]["requestCount"],
                                     "clerk_global_initialised": [s.get("clerkGlobal") for s in run1["browser"]["steps"] if s["step"] == "sign-in"] + [s.get("clerkGlobal") for s in run2["browser"]["steps"] if s["step"] == "sign-in"],
                                     "claim_limit": "NHM demo processes and the demo browser journey only"})
    wr("resource_telemetry.json", {"status": "PASS", "note": "machine-specific engineering telemetry; not a requirement or a performance claim",
                                  "run_1": {"startup_s_including_build_and_prewarm": run1["startup_s_including_build_and_prewarm"], "wall_s": run1["wall_clock_total_s_machine_specific"], "driver_wall_s": run1["browser"]["driver_wall_s"]},
                                  "run_2": {"startup_s_including_build_and_prewarm": run2["startup_s_including_build_and_prewarm"], "wall_s": run2["wall_clock_total_s_machine_specific"], "driver_wall_s": run2["browser"]["driver_wall_s"]},
                                  "prewarm_s": run1["prewarm"]["elapsed_s_engineering_telemetry_only"], "tests": {"full_regression_s": report["full_regression"]["seconds_machine_specific"]}})
    print(json.dumps({"built": True}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
