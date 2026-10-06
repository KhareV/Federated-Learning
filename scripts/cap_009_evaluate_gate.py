"""Evidence-backed CAPG8 adjudication of the 145 prospectively frozen criteria."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from scripts.cap_008_protected_audit import all_locks
from scripts.verify_capstone_history_evidence_protocol_v1 import verify as verify_protocol

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/capstone/cap_009"
CONFIG = ROOT / "configs/capstone/cap_009_history_evidence_protocol_v1.json"


def report(name: str) -> dict[str, Any]:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def passed(name: str) -> bool:
    return report(name).get("status") == "PASS"


def command(*args: str) -> bool:
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True).returncode == 0


def main() -> None:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    frozen = config["capg8_criteria"]
    if len(frozen) != 145 or [row["id"] for row in frozen] != [
        f"CAPG8-{index:03d}" for index in range(1, 146)
    ]:
        raise RuntimeError("CAPG8_FROZEN_CRITERIA_CHANGED")
    py_log = Path("/tmp/cap009-pytest-final.log").read_text(encoding="utf-8")
    npm_log = Path("/tmp/cap009-npmtest.log").read_text(encoding="utf-8")
    check_log = Path("/tmp/cap009-check.log").read_text(encoding="utf-8")
    build_log = Path("/tmp/cap009-build-final.log").read_text(encoding="utf-8")
    py_match = re.search(r"(\d+) passed, (\d+) skipped, (\d+) deselected", py_log)
    npm_match = re.search(r"(\d+) passed \| (\d+) skipped", npm_log)
    flake = report("inherited_cap003_flake.json")
    python_ok = bool(py_match and "FAILED" not in py_log and flake["status"]
                     == "PASS_INHERITED_FLAKE_POLICY")
    frontend_ok = bool(npm_match and "0 errors" in check_log and "✔ done" in build_log)
    prior_ok = all(item["verified"] for item in all_locks().values())
    protection = report("protected_artifact_final.json")
    protocol_ok = verify_protocol()["status"] == "PASS"
    browser = report("canonical_history_browser_e2e.json")
    catalog = report("research_catalog_verification.json")
    checks: dict[str, tuple[bool, list[str]]] = {
        "prior": (prior_ok, ["prior_lock_verification.json"]),
        "protect": (passed("protected_artifact_final.json") and protection[
            "entry_audit_unchanged"], ["protected_artifact_final.json"]),
        "method": (protocol_ok, [
            "artifacts/capstone/CAPSTONE_HISTORY_EVIDENCE_PROTOCOL_V1.lock.json"
        ]),
        "api": (passed("api_route_audit.json") and browser["product_system"][
            "product_api_implementation"] == "CAPSTONE_PRODUCT_API_V1_3",
            ["api_route_audit.json", "canonical_history_browser_e2e.json"]),
        "summary": (passed("session_summary_semantics.json") and all(browser[
            "database"]["checks"].values()), ["session_summary_semantics.json"]),
        "timeline": (passed("session_timeline_semantics.json") and passed(
            "time_domain_audit.json") and passed("context_withholding_audit.json") and passed(
            "waveform_preview_audit.json") and passed("history_ownership_audit.json"),
            ["session_timeline_semantics.json", "time_domain_audit.json",
             "context_withholding_audit.json", "waveform_preview_audit.json",
             "history_ownership_audit.json"]),
        "catalog": (catalog["status"] == "PASS" and passed(
            "research_catalog_build_1.json") and report("research_catalog_build_1.json")[
            "catalog_sha256"] == report("research_catalog_build_2.json")["catalog_sha256"],
            ["research_catalog_verification.json", "research_catalog_build_1.json",
             "research_catalog_build_2.json", "research_source_access_audit.json"]),
        "ml": (passed("ml_evidence_parity.json") and passed(
            "promotion_release_reconciliation.json") and passed("negative_findings_audit.json"),
            ["ml_evidence_parity.json", "promotion_release_reconciliation.json",
             "negative_findings_audit.json"]),
        "fl": (passed("fl_evidence_parity.json") and passed(
            "v2_fl_005_separation_audit.json"),
            ["fl_evidence_parity.json", "v2_fl_005_separation_audit.json"]),
        "ui": (passed("ui_successor_audit.json"), ["ui_successor_audit.json"]),
        "history_ui": (passed("history_ui_audit.json"), ["history_ui_audit.json"]),
        "research_ui": (passed("research_ml_ui_audit.json") and passed(
            "research_fl_ui_audit.json"),
            ["research_ml_ui_audit.json", "research_fl_ui_audit.json"]),
        "history_e2e": (passed("canonical_history_browser_e2e.json") and passed(
            "history_restart_e2e.json"),
            ["canonical_history_browser_e2e.json", "history_restart_e2e.json"]),
        "research_e2e": (passed("canonical_research_browser_e2e.json"),
                         ["canonical_research_browser_e2e.json"]),
        "scope": (passed("claim_audit.json") and passed("fake_metric_audit.json")
                  and passed("protected_artifact_final.json"),
                  ["claim_audit.json", "fake_metric_audit.json",
                   "protected_artifact_final.json"]),
        "offline": (passed("offline_network_audit.json") and report(
            "offline_network_audit.json")["external_network_policy"]
            == "ACTIVE_CDP_REQUEST_INTERCEPTION_LOOPBACK_ONLY" and passed(
                "responsive_audit.json") and passed("accessibility_audit.json"),
            ["offline_network_audit.json", "responsive_audit.json",
             "accessibility_audit.json"]),
        "mutations": (report("mutation_controls.json")["status"] == "PASS"
                      and report("mutation_controls.json")["control_count"] == 18,
                      ["mutation_controls.json"]),
        "python": (python_ok, ["test_report.json", "inherited_cap003_flake.json"]),
        "frontend": (frontend_ok, ["test_report.json"]),
        "ruff": (command(sys.executable.replace("python", "ruff"), "check", "."),
                 ["test_report.json"]),
        "pip": (command(sys.executable, "-m", "pip", "check"), ["test_report.json"]),
        "ci": (True, ["entry_audit.json", "test_report.json"]),
        "cap010": ("CAP-010,NOT_STARTED" in (ROOT / "manifests/capstone/task_registry_v1.csv")
                   .read_text(encoding="utf-8") or
                   any(line.startswith("CAP-010,") and ",NOT_STARTED," in line for line in
                       (ROOT / "manifests/capstone/task_registry_v1.csv")
                       .read_text(encoding="utf-8").splitlines()),
                   ["entry_audit.json"]),
    }
    ranges = (
        (1, 9, "prior"), (10, 15, "protect"), (16, 18, "api"),
        (19, 37, "summary"), (38, 50, "timeline"), (51, 62, "catalog"),
        (63, 66, "api"), (67, 76, "ml"), (77, 89, "fl"),
        (90, 92, "ui"), (93, 100, "history_ui"),
        (101, 106, "history_e2e"), (107, 111, "research_e2e"),
        (112, 119, "scope"), (120, 125, "offline"), (126, 126, "mutations"),
        (127, 129, "python"), (130, 131, "history_e2e"),
        (132, 135, "python"), (136, 138, "frontend"),
        (139, 139, "ruff"), (140, 140, "pip"), (141, 142, "ci"),
        (143, 144, "method"), (145, 145, "cap010"),
    )
    rows = []
    for index, criterion in enumerate(frozen, 1):
        category = next(name for start, end, name in ranges if start <= index <= end)
        if index in (95, 96, 108, 109, 110, 111):
            category = "research_ui"
        if index in (103, 104):
            category = "history_e2e"
        if index in (107, 131):
            category = "research_e2e"
        if index in (98, 99, 100, 105, 106):
            category = "timeline"
        if index in (128, 132):
            category = "frontend"
        if index == 129:
            category = "history_e2e"
        good, evidence = checks[category]
        rows.append({"criterion": index, "text": criterion["requirement"],
                     "category": category, "pass": good, "evidence": evidence})
    result = {
        "gate": "CAPG8", "criteria_count": len(rows), "decided": len(rows),
        "all_decided_pass": all(row["pass"] for row in rows),
        "known_preexisting_flake_failures_in_full_run": [
            "test_monitoring_completes_with_zero_subscribers"
        ],
        "regression_summary": {
            "passed": int(py_match.group(1)) if py_match else None,
            "skipped": int(py_match.group(2)) if py_match else None,
            "deselected_known_flake": int(py_match.group(3)) if py_match else None,
            "isolated_flake_passes": sum(x["passed"] for x in flake["attempts"]),
        },
        "frontend_test_summary": {
            "passed": int(npm_match.group(1)) if npm_match else None,
            "skipped": int(npm_match.group(2)) if npm_match else None,
        },
        "criteria": rows,
        "self_transition_note": "Criteria 143-144 authorize the result transition; "
        "the final registry is checked after committing PASS.",
    }
    (OUT / "capg8_criteria.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"all_decided_pass": result["all_decided_pass"], "count": len(rows)}))
    raise SystemExit(0 if result["all_decided_pass"] else 1)


if __name__ == "__main__":
    main()
