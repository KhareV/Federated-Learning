# ruff: noqa: E501
"""CAP-007: SecAgg SHADOW (round 1, PROTECTED_AGGREGATION_INTERFACE_ONLY; aggregation stays PLAIN)."""

from __future__ import annotations

import json

import yaml
from fastapi.testclient import TestClient

from federated.wearable_fl_secagg_shadow_v1 import load_compat
from product.contracts import ROOT
from product.federation import secagg_shadow
from product.federation import service as service_module
from product.federation.secagg_shadow import CLAIM_SCOPE, EXPECTED, SecAggShadowFailure
from tests.capstone_federation_support import (
    BASE,
    SINGLE_RUN,
    USER_A,
    completed_run,
    make_fed_app,
    poll_run,
)


def _secagg_events(done):
    return [e["payload"] for e in done.events if e["event_type"] == "secagg.status"]


def test_plain_runs_report_not_used_each_round_and_aggregation_is_plain() -> None:
    plain = completed_run()
    assert [(p["round_id"], p["mode"], p["status"]) for p in _secagg_events(plain)] == [
        (1, "PLAIN", "NOT_USED"), (2, "PLAIN", "NOT_USED"), (3, "PLAIN", "NOT_USED")]
    assert {e["payload"]["aggregation_mode"] for e in plain.events if e["event_type"] == "aggregation.status"} == {"PLAIN"}


def test_shadow_run_verifies_round_one_only_and_the_authoritative_result_stays_plain() -> None:
    shadow, plain = completed_run("FEDAVG", "SECAGG_SHADOW"), completed_run()
    assert shadow.run["status"] == "COMPLETED" and shadow.run["secagg_mode"] == "SECAGG_SHADOW"
    payloads = _secagg_events(shadow)
    assert [(p["round_id"], p["mode"], p["status"], p["claim_scope"]) for p in payloads] == [
        (1, "SECAGG_SHADOW", "SHADOW_RUNNING", CLAIM_SCOPE), (1, "SECAGG_SHADOW", "SHADOW_VERIFIED", CLAIM_SCOPE)]
    assert {e["payload"]["aggregation_mode"] for e in shadow.events if e["event_type"] == "aggregation.status"} == {"PLAIN"}
    assert shadow.meta["final_global_state_sha256"] == plain.meta["final_global_state_sha256"]
    assert shadow.meta["committed_digests"] == plain.meta["committed_digests"]
    assert len(shadow.run["candidate_ids"]) == 1 and shadow.run["status"] == "COMPLETED"


def test_the_frozen_tolerances_and_expectations_are_untouched() -> None:
    compat = load_compat()
    assert compat["max_weight"] == 256.0 and EXPECTED == {
        "clients": 8, "max_weight": 256.0, "plain_clear_update_count": 8, "protected_clear_update_count": 0}
    raw = yaml.safe_load((ROOT / "configs/model_v2/wearable_sim_fl_secagg_compat_v1.yaml").read_text())
    assert compat["correctness"] == raw["correctness"]
    lock = json.loads((ROOT / "artifacts/V2_FL_WEARABLE_SYSTEM_PROTOCOL_V1.lock.json").read_text())
    assert lock["secagg_compat_max_weight"] == 256.0
    text = (ROOT / "product/federation/secagg_shadow.py").read_text()
    assert "tolerance" not in text.split("def run_round1_shadow")[1].replace("tolerances are never widened", "")


def test_a_failed_shadow_fails_the_run_loudly_without_a_candidate(tmp_path, monkeypatch) -> None:
    def fail(*args, **kwargs):
        raise SecAggShadowFailure("SECAGG_SHADOW_NOT_VERIFIED")

    monkeypatch.setattr(service_module, "run_round1_shadow", fail)
    app, _ = make_fed_app(tmp_path)
    with TestClient(app) as client:
        body = {**SINGLE_RUN, "secagg_mode": "SECAGG_SHADOW"}
        rid = client.post(f"{BASE}/federation/runs", json=body, headers=USER_A).json()["run_id"]
        client.post(f"{BASE}/federation/runs/{rid}/start", headers=USER_A)
        run = poll_run(client, rid, USER_A)
    assert run["status"] == "FAILED" and run["candidate_ids"] == []
    events = [e.model_dump(mode="json") for e in app.state.federation_service.journal_for(rid).events]
    assert [p["status"] for p in [e["payload"] for e in events if e["event_type"] == "secagg.status"]] == [
        "SHADOW_RUNNING", "SHADOW_FAILED"]
    errors = [e["payload"] for e in events if e["event_type"] == "federation.error"]
    assert errors and errors[0]["error_code"] == "SECAGG_SHADOW_FAILED" and errors[0]["recoverable"] is False
    assert events[-1]["payload"]["run_status"] == "FAILED"
    assert app.state.federation_store.counts()["candidate_models"] == 0
    assert secagg_shadow.CLAIM_SCOPE == "PROTECTED_AGGREGATION_INTERFACE_ONLY"
