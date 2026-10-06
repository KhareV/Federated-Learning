# ruff: noqa: E501
"""UFL-LITE-003 machinery tests: frozen protocol shape, analyzer behaviour on a synthetic good observation set, every mutation breaks its named group, evaluator wiring."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts import ufl_lite_003_evaluate_gate as ev
from scripts import ufl_lite_003_lib as an
from scripts import ufl_lite_lib as lib

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT / "configs/ufl_lite/uflg2_protocol_v1.json").read_text())
IDS = list(lib.CLIENT_IDS)


def facts(**kw):
    base = {"clientIds": IDS, "ownerCards": 1, "peerCards": 7, "ownerClient": an.OWNER, "ownerRole": "AUTHENTICATED_OWNER", "ownerState": "SUBMITTED", "ownerText": "MY EDGE CLIENT SYNTHETIC ENGINEERING NOT YOUR PHYSIOLOGY", "myParticipation": "MY FEDERATED PARTICIPATION SYNTHETIC ENGINEERING FIXTURE (not the authenticated user's physiology) logical local buffer",
            "myExamples": "93", "myRounds": "3 / 3", "myUpdates": "3 / 3", "rawSent": "0", "runStatus": "COMPLETED · LIVE_RUN", "updateReady": "24", "streamError": False, "federatedParticipantsTitle": True, "eightLogicalTitle": False, "myEdgeMentions": 1,
            "forbiddenWords": [], "interactiveConsentControls": 0, "updatesSubmittedLabelForOwner": False}
    base.update(kw)
    return base


def auth():
    ud = {str(r): {c: {"update_sha256": f"{r}{i}".ljust(64, "a"), "examples_seen": 93 if c == an.OWNER else 90} for i, c in enumerate(IDS)} for r in (1, 2, 3)}
    return {"event_count": 202, "sequence_contiguous": True, "update_ready_events": 24, "update_digests": ud, "round_state_digests": {"1": "a" * 64, "2": "b" * 64, "3": "c" * 64}, "candidate_state_digest_event": an.CANDIDATE,
            "run": {"status": "COMPLETED", "run_type": "LIVE_RUN"}}


CAND = {"status": 200, "released_default": "MODEL_V2_FINAL", "candidates": [{"candidate_id": "C1", "state_digest": an.CANDIDATE, "governance_status": "ACCEPTED_TO_SANDBOX", "sandbox_status": "IN_SANDBOX", "production_deployed": False, "parent_model_id": "FL_INIT_V2"}]}
SOCK = [{"pathname": "/product/v1/federation/runs/R/live", "handshakeStatus": 101, "urlHasToken": False, "cookieSessionSent": True, "framesReceived": 202}] * 2


def signin():
    return {"step": "signin", "system": {"auth_provider": "CLERK", "demo_mode": False, "model_id": "MODEL_V2_FINAL"}, "me": {"status": 200, "auth_provider": "CLERK", "demo_mode": False, "user_id_is_clerk_shaped": True, "user_id_is_demo": False}}


def observations():
    a = {"liveRunId": "R", "websockets": SOCK, "network": {"clerkOwnedHosts": ["clerk.accounts.dev"]}, "console_errors": [], "steps": [
        signin(), {"step": "clients-rest", "site00": {"local_example_count": 93}}, {"step": "refresh-mid-run", "after_ownerCards": 1, "after_peerCards": 7, "after_ownerClient": an.OWNER, "after_clientIds": IDS, "after_streamError": False},
        {"step": "live-completed", **facts()}, {"step": "live-authoritative", **auth()}, {"step": "rounds-page", "ownerNote": "MY EDGE CLIENT: SIM_FL_SITE_00 synthetic engineering data", "myEdgeMentions": 1}, {"step": "models-after-live", **CAND},
        {"step": "global-clients-view", "clientIdsShown": 8, "myEdgeMentions": 0, "authenticatedOwnerMentions": 0},
        {"step": "replay", "runId_differs_from_live": True, "authoritative": {"run": {"run_type": "REPLAY"}}, "facts": facts(ownerCards=0, peerCards=0, ownerClient=None, ownerRole=None, ownerState=None, ownerText="", myParticipation="", myEdgeMentions=0, federatedParticipantsTitle=False, eightLogicalTitle=True)},
        {"step": "models-after-replay", **CAND}]}
    probes = [{"label": "read A run", "rewritten": True, "status": 403, "app_bearer_kept": True}, {"label": "read A rounds", "rewritten": True, "status": 403, "app_bearer_kept": True}, {"label": "start A run (control)", "rewritten": True, "status": 403, "app_bearer_kept": True},
              {"label": "CONTROL: nonexistent run", "rewritten": True, "status": 404, "app_bearer_kept": True}, {"label": "CONTROL: global research view", "rewritten": True, "status": 200, "app_bearer_kept": True}]
    b = {"steps": [{"step": "global-clients-view", "clientIdsShown": 8, "myEdgeMentions": 0, "authenticatedOwnerMentions": 0}, {"step": "b-rest-probes", "results": probes}, {"step": "b-websocket", "federation": {"closeCode": 4403, "opened": False, "frames": 0}},
                  {"step": "b-views-a-live-page", "ownerCards": 0, "myEdgeMentions": 0, "myParticipation": ""}, {"step": "b-own-runs", "status": 200, "contains_a_run": False}]}
    a2 = {"websockets": SOCK, "steps": [signin(), {"step": "live-reconstructed", **facts()}, {"step": "live-authoritative", **auth()}, {"step": "models-after-restart", **CAND}]}
    return a, b, a2


BASE = lib.load_baseline(ROOT)


def test_protocol_shape_is_frozen() -> None:
    assert CFG["criteria_count"] == len(CFG["uflg2_criteria"]) and CFG["mutation_control_count"] == 35 == len(CFG["mutation_controls"]) == len(set(CFG["mutation_controls"]))
    assert [c["id"] for c in CFG["uflg2_criteria"]] == [f"U{i:02d}" for i in range(1, len(CFG["uflg2_criteria"]) + 1)]


def test_every_criterion_check_is_wired() -> None:
    checks = ev.build_checks()
    a, b, a2 = observations()
    groups = an.analyze_all(a, b, a2, BASE)
    for row in CFG["uflg2_criteria"]:
        for c in row["checks"]:
            if c.startswith("G:"):
                group, name = c[2:].split(".")
                assert name in groups[group], c
            else:
                assert c in checks, c


def test_synthetic_good_observations_pass_every_analyzer() -> None:
    a, b, a2 = observations()
    groups = an.analyze_all(a, b, a2, BASE)
    bad = {g: [k for k, v in c.items() if not v] for g, c in groups.items() if g != "clerk_network" and not all(c.values())}
    assert bad == {}


@pytest.mark.parametrize("name", an.OBSERVATION_MUTATIONS)
def test_each_observation_mutation_breaks_its_group(name: str) -> None:
    a, b, a2 = observations()
    ma, mb, m2, group = an.mutate(name, a, b, a2)
    assert not all(an.analyze_all(ma, mb, m2, BASE)[group].values()), name
    assert all(an.analyze_all(a, b, a2, BASE)[group].values())


def test_mutation_leaves_inputs_untouched() -> None:
    a, b, a2 = observations()
    snap = copy.deepcopy((a, b, a2))
    an.mutate("SECOND_OWNER_CARD", a, b, a2)
    assert (a, b, a2) == snap


def test_names_cover_protocol() -> None:
    assert list(an.OBSERVATION_MUTATIONS) == CFG["mutation_controls"][: len(an.OBSERVATION_MUTATIONS)]
    assert len(an.OBSERVATION_MUTATIONS) == 28
