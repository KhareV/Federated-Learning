# ruff: noqa: E501
"""FINAL-EVAL-REPAIR-001 anti-regression tests: permanent guards for the defect classes found by FINAL_EVALUATOR_AUDIT_V1 (stale feature status, legacy routes, runbook, font, owner-binding scope)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from scripts import final_eval_repair_lib as lib
from scripts import final_eval_repair_presentation as pres

ROOT = Path(__file__).resolve().parents[1]
POLICY = json.loads((ROOT / "configs/final_eval_repair/legacy_route_policy_v1.json").read_text())
PROTOCOL = json.loads((ROOT / "configs/final_eval_repair/fer_001_protocol_v1.json").read_text())


def test_about_does_not_claim_federation_disabled() -> None:
    assert not pres.about_ok()["stale"]
    assert not re.search(r"not yet enabled", (ROOT / "frontend/src/routes/app/about/+page.svelte").read_text(), re.I)


def test_about_matches_current_federation_truth() -> None:
    r = pres.about_ok()
    assert r["ok"], r


def test_landing_does_not_claim_federation_disabled() -> None:
    t = (ROOT / "frontend/src/routes/+page.svelte").read_text()
    assert not re.search(r"not yet enabled", t, re.I) and not pres.landing_ok()["stale"]


def test_landing_reports_engineering_federation_with_qualifications() -> None:
    r = pres.landing_ok()
    assert r["ok"] and not r["missing"], r


def test_landing_does_not_expose_owner_binding_to_every_visitor() -> None:
    assert pres.landing_ok()["owner_binding_overreach"] == []


def test_connected_runbook_documents_owner_bound_difference() -> None:
    t = (ROOT / "docs/capstone/CLERK_CONNECTED_RUNBOOK_V1_1.md").read_text()
    assert pres.runbook_ok()["ok"] and "MY EDGE CLIENT" in t and "SYNTHETIC PEER" in t and "OFFLINE DEMO" in t and "REPLAY" in t


def test_connected_runbook_denies_user_physiology_training() -> None:
    t = (ROOT / "docs/capstone/CLERK_CONNECTED_RUNBOOK_V1_1.md").read_text()
    assert "not** the authenticated user's physiology" in t and "never feed federation" in t


def test_connected_runbook_denies_personal_model() -> None:
    t = (ROOT / "docs/capstone/CLERK_CONNECTED_RUNBOOK_V1_1.md").read_text()
    assert "no personal model" in t and "not personalized federated learning" in t


def test_historical_runbook_v1_is_byte_frozen() -> None:
    from scripts.verify_clerk_connected import verify

    assert verify()["status"] == "PASS"
    assert "exactly as in the offline mode" in (ROOT / "docs/capstone/CLERK_CONNECTED_RUNBOOK_V1.md").read_text()      # historical bytes preserved; V1_1 supersedes it


def test_every_route_is_classified() -> None:
    r = pres.routes_ok()
    assert r["unclassified"] == [] and r["stale_entries"] == [] and r["bad_class"] == []
    assert r["counts"]["routes"] == len(lib.discover_routes()) == POLICY["route_file_count"]


def test_every_legacy_route_has_policy() -> None:
    assert pres.ts_redirects() == {r["pattern"]: r["redirect_to"] for r in POLICY["routes"] if r["class"] == "LEGACY_REDIRECT"}
    assert POLICY["legacy_redirect_count"] == 33 and POLICY["retained_legacy_tool_count"] == 1


@pytest.mark.parametrize(("legacy", "target"), [("/fl/overview", "/app/federation"), ("/fl/personal-models", "/app/federation"), ("/ai/insights", "/app/research/ml"), ("/overview", "/app")])
def test_known_bad_legacy_routes_redirect(legacy: str, target: str) -> None:
    assert pres.ts_redirects()[legacy] == target
    assert "legacyRedirect" in (ROOT / "frontend/src/routes/+layout.ts").read_text()


def test_redirect_policy_is_safe() -> None:
    r = pres.routes_ok()
    assert r["loops"] == [] and r["external"] == [] and r["dangling"] == [] and r["retired_current"] == [] and r["layout_wired"]


def test_monitoring_research_tool_decision_is_documented() -> None:
    assert pres.routes_ok()["monitoring_decision_ok"] and "monitoring_decision" in POLICY


def test_no_legacy_route_renders_fabricated_metrics() -> None:
    legacy = {r["pattern"] for r in POLICY["routes"] if r["class"] == "LEGACY_REDIRECT"}
    reachable = set(pres.current_files())
    assert not [r["file"] for r in POLICY["routes"] if r["pattern"] in legacy and r["file"] in reachable]


def test_no_current_route_contains_stale_feature_status() -> None:
    r = pres.stale_feature_status()
    assert r["ok"], r["hits"]


def test_no_current_route_makes_an_unqualified_overclaim() -> None:
    r = pres.claims_ok()
    assert r["ok"], r["hits"]


def test_truth_contract_matches_backend_and_frozen_constants() -> None:
    r = pres.truth_contract_ok()
    assert r["ok"], r


def test_global_clients_demo_and_replay_remain_unbound() -> None:
    r = pres.unbound_ok()
    assert r["ok"] and r["global_page_unbound"], r


def test_research_and_model_pages_keep_their_distinctions() -> None:
    r = pres.pages_ok()
    assert r["ok"], r


def test_no_missing_lastoria_request_source() -> None:
    r = pres.lastoria_unreferenced()
    assert r["ok"] and not r["signature_reachable"], r


def test_capstone_ui_v1_5_verifies() -> None:
    from scripts.verify_capstone_ui_v1_5 import verify

    assert verify()["status"] == "PASS"


def test_protocol_shape_is_frozen() -> None:
    assert PROTOCOL["criteria_count"] == len(PROTOCOL["ferg0_criteria"]) == 51 and PROTOCOL["mutation_control_count"] == 35 == len(PROTOCOL["mutation_controls"]) == len(set(PROTOCOL["mutation_controls"]))


def test_presentation_verifier_passes_on_the_repaired_tree() -> None:
    assert pres.verify_all()["ok"]


def test_every_criterion_check_is_wired_in_the_evaluator() -> None:
    from scripts import final_eval_repair_evaluate_gate as ev

    checks = ev.build_checks()
    for row in PROTOCOL["ferg0_criteria"]:
        for c in row["checks"]:
            assert c in checks, c


def test_mutation_names_match_the_control_table() -> None:
    from scripts import final_eval_repair_mutation_controls as mc

    assert list(mc.CONTROLS) == PROTOCOL["mutation_controls"]
