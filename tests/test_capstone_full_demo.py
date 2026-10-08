# ruff: noqa: E501
"""CAP-010: FULL_CAPSTONE_DEMO binding, runbook claim audit, zero-drift and no-fakery guards."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from scripts.cap_010_runbook_audit import RUNBOOK, audit_runbook

ROOT = Path(__file__).resolve().parents[1]
ENTRY = "be778d4ced186639155064e94516ff096751a81f"
DRIVER = ROOT / "scripts/cap_010_cdp_driver.mjs"
RUNNER = ROOT / "scripts/run_capstone_full_demo_e2e.py"


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout


def test_product_api_frontend_and_backend_are_byte_identical_to_entry() -> None:
    trees = ["api", "product", "capstone_persistence", "frontend", "federated", "privacy", "simulation", "src", "checkpoints", "contracts", "reports/model_v2",
             "artifacts/DEFAULT_RUNTIME_BINDING_V2.lock.json", "artifacts/SOFTWARE_SYSTEM_V2.lock.json", "artifacts/capstone/CAPSTONE_UI_V1_2.lock.json", "artifacts/capstone/CAPSTONE_RESEARCH_EVIDENCE_CATALOG_V1.json"]
    drift = _git("diff", "--name-only", "--diff-filter=AMD", ENTRY, "--", *trees).split()
    # NHM_RESEARCH_OBSERVATORY_V1 adds read-only observability files; they are verified by scripts.verify_observatory_v1, not treated as drift.
    drift = [p for p in drift if p != "api/product_app_observatory_v1.py" and not p.startswith("product/observatory/")]
    # CLERK-LIVE-001 successor awareness (CAP-010 amendment 2): frontend drift is legal ONLY if it is completely accounted for by the
    # registered, verifying CAPSTONE_UI_V1_3 lock; any other drift (and any unaccounted frontend change) still fails.
    successor = ROOT / "artifacts/capstone/CAPSTONE_UI_V1_3.lock.json"
    if successor.exists():
        from scripts.verify_capstone_ui_v1_3 import verify as verify_ui13

        assert verify_ui13()["status"] == "PASS"
        accounted = set(json.loads(successor.read_text())["changed_from_predecessor"])
        successor14 = ROOT / "artifacts/capstone/CAPSTONE_UI_V1_4.lock.json"       # UFL-LITE-002 (CAP-010 amendment 3): V1_4 accounts for its own delta
        if successor14.exists():
            from scripts.verify_capstone_ui_v1_4 import verify as verify_ui14

            assert verify_ui14()["status"] == "PASS"
            accounted |= set(json.loads(successor14.read_text())["changed_from_predecessor"])
        successor15 = ROOT / "artifacts/capstone/CAPSTONE_UI_V1_5.lock.json"       # FINAL-EVAL-REPAIR-001 (CAP-010 amendment 4): V1_5 accounts for its own delta
        if successor15.exists():
            from scripts.verify_capstone_ui_v1_5 import verify as verify_ui15

            assert verify_ui15()["status"] == "PASS"
            accounted |= set(json.loads(successor15.read_text())["changed_from_predecessor"])
        successor16 = ROOT / "artifacts/capstone/CAPSTONE_UI_V1_6.lock.json"       # FINAL-EVAL-REPAIR-002 (CAP-010 amendment 5): V1_6 accounts for its own delta
        if successor16.exists():
            from scripts.verify_capstone_ui_v1_6 import verify as verify_ui16

            assert verify_ui16()["status"] == "PASS"
            accounted |= set(json.loads(successor16.read_text())["changed_from_predecessor"])
        successor17 = ROOT / "artifacts/capstone/CAPSTONE_UI_V1_7.lock.json"       # UI-ENH-001: V1_7 accounts for its own delta
        if successor17.exists():
            from scripts.verify_capstone_ui_v1_7 import verify as verify_ui17

            assert verify_ui17()["status"] == "PASS"
            accounted |= set(json.loads(successor17.read_text())["changed_from_predecessor"])
        successor18 = ROOT / "artifacts/capstone/CAPSTONE_UI_V1_8.lock.json"
        if successor18.exists():
            from scripts.verify_capstone_ui_v1_8 import verify as verify_ui18

            assert verify_ui18()["status"] == "PASS"
            accounted |= set(json.loads(successor18.read_text())["changed_from_predecessor"])
        successor19 = ROOT / "artifacts/capstone/CAPSTONE_UI_V1_9.lock.json"
        if successor19.exists():
            from scripts.verify_capstone_ui_v1_9 import verify as verify_ui19

            assert verify_ui19()["status"] == "PASS"
            accounted |= set(json.loads(successor19.read_text())["changed_from_predecessor"])
        observatory = ROOT / "artifacts/observatory/NHM_RESEARCH_OBSERVATORY_V1.lock.json"       # additive Observatory successor tip
        if observatory.exists():
            from scripts.verify_observatory_v1 import verify as verify_observatory

            assert verify_observatory()["status"] == "PASS"
            accounted |= set(json.loads(observatory.read_text())["changed_from_predecessor"])
        drift = [p for p in drift if not (p.startswith("frontend/") and p in accounted)]
    assert drift == []


def test_no_new_python_or_npm_dependency() -> None:
    for rel in ("pyproject.toml", "requirements-dev.lock", "frontend/package.json", "frontend/package-lock.json", "frontend/clerk-sdk/package.json", "frontend/clerk-sdk/package-lock.json"):
        if (ROOT / rel).exists():
            assert _git("diff", "--name-only", ENTRY, "--", rel).strip() == "", rel
    imports = set()
    for rel in ("scripts/run_capstone_faculty_demo.py", "scripts/capstone_demo_preflight.py", "scripts/capstone_demo_workspace.py", "scripts/run_capstone_full_demo_e2e.py"):
        imports |= set(re.findall(r"^(?:from|import) ([A-Za-z_][\w]*)", (ROOT / rel).read_text(), re.M))
    assert imports <= {"__future__", "argparse", "contextlib", "csv", "dataclasses", "datetime", "hashlib", "importlib", "json", "os", "pathlib", "re", "shutil", "signal", "socket", "sqlite3", "subprocess", "sys", "tempfile",
                       "threading", "time", "typing", "webbrowser", "collections", "httpx", "websockets", "scripts", "product"}, imports


def test_full_demo_binding_matches_the_frozen_contract() -> None:
    binding = json.loads((ROOT / "configs/capstone/cap_010_full_demo_binding_v1.json").read_text())
    contract = next(s for s in json.loads((ROOT / "contracts/capstone/demo_scenarios_v1.json").read_text())["scenarios"] if s["scenario_id"] == "FULL_CAPSTONE_DEMO")
    assert binding["A_contract_coverage"]["composes"] == contract["composes"]
    assert binding["classification"] == contract["classification"] == "ENGINEERING_DEMO" and binding["scientific_evidence"] is False and binding["production_deployed"] is False
    assert binding["offline_one_laptop"] is True and binding["outcome_tuning_forbidden"] is True
    hero = binding["B_faculty_hero_journey"]
    assert hero["monitoring_scenario"] == "MIXED_MONITORING_SESSION" and hero["federation"] == {"run_type": "LIVE_RUN", "scenario": "FL_SINGLE_RUN", "algorithm": "FEDAVG", "secagg_mode": "SECAGG_SHADOW", "rounds": 3, "clients": 8, "updates": 24, "authoritative_aggregation": "PLAIN"}
    assert [binding["services"][k]["default_port"] for k in ("inference", "product", "frontend")] == [8001, 8002, 4173]
    protocol = json.loads((ROOT / "configs/capstone/cap_010_faculty_demo_protocol_v1.json").read_text())
    assert protocol["scenario_coverage"] == contract["composes"] and len(protocol["mutation_controls"]) == 16


def test_runbook_has_required_statements_and_both_paths() -> None:
    text = RUNBOOK.read_text()
    result = audit_runbook(text)
    assert result["missing_required"] == [], result
    assert "SHORT PATH" in text and "FULL PATH" in text and "5-7 minutes" in text and "10-15 minutes" in text and "planning range only" in text
    for statement in ("There is no personal model", "Does it train a personal model for the user?", "MODEL_V2_NOT_PROMOTED_RELEASE_CI", "SYSTEM_V2_RESEARCH_DEFAULT_ACCEPTED", "does not retroactively pass", "VERIFICATION_REQUIRED",
                      "DeviceSource boundary", "never automatically deployed", "round-1 protected-aggregation shadow", "authoritative aggregation remains plain", "inference.log", "product.log", "frontend.log", "PORT_IN_USE", "Never kill arbitrary processes"):
        assert statement in text, statement


def test_runbook_claim_audit_finds_no_overclaim() -> None:
    result = audit_runbook(RUNBOOK.read_text())
    assert result["unnegated_watched_claims"] == [] and result["ok"]


def test_runbook_claim_audit_rejects_every_overclaim_mutation() -> None:
    base = RUNBOOK.read_text()
    for claim in ("The physical wearable is connected.", "The system uses real hardware.", "Eight hospitals participate in the federation.", "The SecAgg shadow provides differential privacy.", "The candidate is deployed automatically.",
                  "The user session trains a personal model.", "REPLAY is active training in progress.", "The product gives a clinical diagnosis.", "The federation is secure and private.", "On-device ML personalizes the model."):
        assert audit_runbook(base + "\n" + claim)["unnegated_watched_claims"], claim
    assert audit_runbook(base.replace("There is no personal model", "There is a personal model"))["missing_required"]


def test_no_outcome_tuning_or_hardcoded_model_output() -> None:
    for path in (DRIVER, RUNNER, ROOT / "scripts/run_capstone_faculty_demo.py"):
        text = path.read_text()
        assert "POTENTIAL_ECTOPY_ASSOCIATED_PATTERN" not in text, path.name
        assert not re.search(r"seed\s*=\s*\d{6,}|search_seed|for seed in", text), path.name
        assert "model_outcome_asserted" not in text or '"model_outcome_asserted": False' in text
    assert "positive_state_required" not in RUNNER.read_text()


def test_hero_path_uses_the_real_stack_without_mocks() -> None:
    driver, runner = DRIVER.read_text(), RUNNER.read_text()
    for forbidden in ("Fetch.fulfillRequest", "route.fulfill", "respondWith", "MockTransport", "TestClient", "monkeypatch", "unittest.mock", "page.route"):
        assert forbidden not in driver and forbidden not in runner, forbidden
    assert "Fetch.continueRequest" in driver and "Fetch.failRequest" in driver
    for step in ("ENTER DEMO WORKSPACE", "ATTACH NHM VIRTUAL WEARABLE", "'SCAN'", "PAIR / CONNECT", "create-session", "start-session", "session-complete", "cfg-submit", "MIXED_MONITORING_SESSION"):
        assert step in driver, step
    assert "scripts.run_capstone_faculty_demo" in runner and "chrome(" in runner and "run_nhm_default" not in runner
    assert "createFederationRun" not in driver and "POST" not in driver.replace("POSTED", "")
