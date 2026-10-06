# ruff: noqa: E501
"""UFL-LITE-003 pure analyzers over the sanitized REAL-Clerk browser observations (used by the E2E orchestrator, the frozen UFLG2 evaluator,
the tests and the mutation controls). Each analyzer returns {check_name: bool}; nothing here performs I/O, training or network access."""

from __future__ import annotations

import copy
import re
from typing import Any

from scripts import ufl_lite_lib as lib

OWNER = "SIM_FL_SITE_00"
CLIENT_IDS = lib.CLIENT_IDS
CANDIDATE = lib.CANONICAL_CANDIDATE_DIGEST
FORBIDDEN = re.compile(r"contribution|influence score|personali[sz]ed|personal model|my ECG|my monitoring|opt[- ]in|consent|join federation", re.I)


def step(run: dict[str, Any], name: str) -> dict[str, Any]:
    return next(s for s in run["steps"] if s["step"] == name)


def _num(text: str) -> int | None:
    m = re.search(r"\d+", text or "")
    return int(m.group()) if m else None


def _updates_ok(auth: dict[str, Any]) -> dict[str, bool]:
    ud = auth["update_digests"]
    per_round = [len(ud.get(str(r), ud.get(r, {}))) for r in (1, 2, 3)]
    sites = [set(ud.get(str(r), ud.get(r, {}))) for r in (1, 2, 3)]
    return {"rounds_3": sorted(map(str, ud)) == ["1", "2", "3"], "updates_24": auth["update_ready_events"] == 24, "updates_8_8_8": per_round == [8, 8, 8], "every_round_has_all_8": all(s == set(CLIENT_IDS) for s in sites),
            "site00_93_examples_each_update": all(ud.get(str(r), ud.get(r, {})).get(OWNER, {}).get("examples_seen") == 93 for r in (1, 2, 3)), "sequence_contiguous": auth["sequence_contiguous"] is True,
            "update_digests_64hex": all(re.fullmatch(r"[0-9a-f]{64}", v["update_sha256"]) for rd in ud.values() for v in rd.values())}


def _completed(f: dict[str, Any]) -> dict[str, bool]:
    return {"status_completed": "COMPLETED" in f["runStatus"], "no_stream_error": f["streamError"] is False}


def analyze_live(f: dict[str, Any], auth: dict[str, Any], clients_rest: dict[str, Any], baseline: dict[str, Any]) -> dict[str, bool]:
    """Owner journey on the REAL Clerk LIVE_RUN page after completion (``f`` = DOM facts, ``auth`` = authoritative events/REST)."""
    ids = f["clientIds"]
    site00_rest = clients_rest.get("site00") or {}
    return {
        **_completed(f), **_updates_ok(auth),
        "client_ids_exact_8": ids == list(CLIENT_IDS), "no_ninth_client": len(ids) == 8 and len(set(ids)) == 8,
        "one_owner_card": f["ownerCards"] == 1, "owner_is_site00": f["ownerClient"] == OWNER and f["ownerRole"] == "AUTHENTICATED_OWNER", "seven_peer_cards": f["peerCards"] == 7,
        "one_my_edge_label": f["myEdgeMentions"] == 1, "technical_id_unchanged": OWNER in ids,
        "owner_card_synthetic_wording": "SYNTHETIC ENGINEERING" in f["ownerText"] and "NOT YOUR PHYSIOLOGY" in f["ownerText"],
        "owner_participants_title": f["federatedParticipantsTitle"] is True and f["eightLogicalTitle"] is False,
        "owner_state_submitted": f["ownerState"] == "SUBMITTED",
        "examples_93_ui": _num(f["myExamples"]) == 93, "examples_93_rest": site00_rest.get("local_example_count") == 93 == baseline["datasets"][OWNER]["local_example_count"],
        "examples_event_derived": _num(f["myExamples"]) == auth["update_digests"]["1"][OWNER]["examples_seen"],
        "rounds_3_ui": _num(f["myRounds"]) == 3 and "3 / 3" in f["myRounds"], "updates_3_ui": _num(f["myUpdates"]) == 3 and "3 / 3" in f["myUpdates"],
        "raw_examples_sent_zero": f["rawSent"] == "0", "locality_wording": "logical local buffer" in f["myParticipation"] or "Raw training examples sent" in f["myParticipation"],
        "synthetic_summary_wording": "SYNTHETIC ENGINEERING FIXTURE" in f["myParticipation"] and "not the authenticated user's physiology" in f["myParticipation"],
        "no_contribution_or_personalization_wording": not f["forbiddenWords"], "no_consent_ui": f["interactiveConsentControls"] == 0,
        "summary_not_updates_submitted_label": f["updatesSubmittedLabelForOwner"] is False,
    }


def analyze_candidate(models: dict[str, Any], auth: dict[str, Any]) -> dict[str, bool]:
    cands = models.get("candidates") or []
    c = cands[0] if cands else {}
    return {"one_candidate": len(cands) == 1, "candidate_digest_canonical": c.get("state_digest") == CANDIDATE, "candidate_event_digest_canonical": auth["candidate_state_digest_event"] == CANDIDATE, "candidate_accepted_to_sandbox": c.get("governance_status") == "ACCEPTED_TO_SANDBOX",
            "candidate_in_sandbox": c.get("sandbox_status") == "IN_SANDBOX", "candidate_not_deployed": c.get("production_deployed") is False, "released_default_v2_final": models.get("released_default") == "MODEL_V2_FINAL"}


def analyze_identity(signin: dict[str, Any]) -> dict[str, bool]:
    return {"auth_provider_clerk": signin["system"]["auth_provider"] == "CLERK" and signin["me"]["auth_provider"] == "CLERK", "not_demo_mode": signin["system"]["demo_mode"] is False and signin["me"]["demo_mode"] is False,
            "me_200_clerk_user": signin["me"]["status"] == 200 and signin["me"]["user_id_is_clerk_shaped"] is True and signin["me"]["user_id_is_demo"] is False, "model_v2_final": signin["system"]["model_id"] == "MODEL_V2_FINAL"}


def analyze_refresh(r: dict[str, Any]) -> dict[str, bool]:
    return {"refresh_keeps_one_owner": r["after_ownerCards"] == 1 and r["after_ownerClient"] == OWNER, "refresh_keeps_seven_peers": r["after_peerCards"] == 7, "refresh_keeps_8_ids": r["after_clientIds"] == list(CLIENT_IDS), "refresh_no_stream_error": r["after_streamError"] is False}


def analyze_ws(sockets: list[dict[str, Any]]) -> dict[str, bool]:
    fed = [s for s in sockets if re.search(r"/federation/runs/[^/]+/live$", s["pathname"])]
    live = [s for s in fed if s["handshakeStatus"] is not None]       # a socket aborted by a navigation never completes a handshake
    return {"ws_present": bool(live), "ws_handshake_101": bool(live) and all(s["handshakeStatus"] == 101 for s in live), "ws_no_token_in_url": bool(fed) and not any(s["urlHasToken"] for s in fed), "ws_cookie_transport": bool(live) and all(s["cookieSessionSent"] for s in live),
            "ws_events_received": bool(live) and all(s["framesReceived"] > 0 for s in live), "ws_reconnected_after_refresh": len(live) >= 2}


def analyze_rounds_page(r: dict[str, Any]) -> dict[str, bool]:
    return {"rounds_note_owner": OWNER in r["ownerNote"] and "synthetic engineering data" in r["ownerNote"], "rounds_one_my_edge": r["myEdgeMentions"] == 1}


def analyze_global(g: dict[str, Any]) -> dict[str, bool]:
    return {"global_view_8_ids": g["clientIdsShown"] == 8, "global_view_unbound": g["myEdgeMentions"] == 0 and g["authenticatedOwnerMentions"] == 0}


def analyze_replay(rp: dict[str, Any], live_auth: dict[str, Any], models_after: dict[str, Any], models_before: dict[str, Any]) -> dict[str, bool]:
    f = rp["facts"]
    return {"replay_distinct_run": rp["runId_differs_from_live"] is True, "replay_completed": "COMPLETED" in f["runStatus"], "replay_type": (rp["authoritative"]["run"] or {}).get("run_type") == "REPLAY",
            "replay_no_owner_card": f["ownerCards"] == 0 and f["myEdgeMentions"] == 0 and f["ownerClient"] is None, "replay_no_participation_summary": f["myParticipation"] == "", "replay_8_ids": f["clientIds"] == list(CLIENT_IDS),
            "replay_title_unbound": f["eightLogicalTitle"] is True and f["federatedParticipantsTitle"] is False, "replay_candidate_unchanged": models_after.get("candidates") == models_before.get("candidates")}


def analyze_isolation(b: dict[str, Any], a_run: str) -> dict[str, bool]:
    probes = step(b, "b-rest-probes")["results"]
    deny = [p for p in probes if "CONTROL" not in p["label"]]
    nonexist = next(p for p in probes if "nonexistent" in p["label"])
    glob = next(p for p in probes if "global" in p["label"])
    ws = step(b, "b-websocket")["federation"]
    view = step(b, "b-views-a-live-page")
    own = step(b, "b-own-runs")
    gl = step(b, "global-clients-view")
    return {"b_rest_a_run_403": all(p["rewritten"] and p["status"] == 403 and p["app_bearer_kept"] for p in deny) and len(deny) == 3, "b_control_nonexistent_404": nonexist["rewritten"] and nonexist["status"] == 404, "b_control_global_200": glob["rewritten"] and glob["status"] == 200,
            "b_ws_4403": ws["closeCode"] == 4403 and ws["frames"] == 0, "b_no_owner_card_on_a_run": view["ownerCards"] == 0 and view["myEdgeMentions"] == 0 and "SIM_FL" not in view["myParticipation"],
            "b_own_runs_exclude_a": own["status"] == 200 and own["contains_a_run"] is False, "b_global_clients_unbound": gl["clientIdsShown"] == 8 and gl["myEdgeMentions"] == 0 and gl["authenticatedOwnerMentions"] == 0,
            "b_distinct_run_id": bool(a_run)}


def analyze_restart(a2: dict[str, Any], a_live_auth: dict[str, Any], a_models: dict[str, Any]) -> dict[str, bool]:
    f, auth = step(a2, "live-reconstructed"), step(a2, "live-authoritative")
    f_ok = analyze_live(f, auth, {"site00": {"local_example_count": 93}}, {"datasets": {OWNER: {"local_example_count": 93}}})
    mod = step(a2, "models-after-restart")
    return {"restart_signin_clerk": analyze_identity(step(a2, "signin"))["auth_provider_clerk"], "restart_one_owner": f_ok["one_owner_card"] and f_ok["owner_is_site00"], "restart_seven_peers": f_ok["seven_peer_cards"], "restart_8_ids": f_ok["client_ids_exact_8"],
            "restart_examples_93": f_ok["examples_93_ui"], "restart_rounds_3_updates_3": f_ok["rounds_3_ui"] and f_ok["updates_3_ui"], "restart_24_updates_8_8_8": f_ok["updates_24"] and f_ok["updates_8_8_8"],
            "restart_same_update_digests": auth["update_digests"] == a_live_auth["update_digests"], "restart_same_state_digests": auth["round_state_digests"] == a_live_auth["round_state_digests"], "restart_candidate_unchanged": mod["candidates"] == a_models["candidates"],
            "restart_candidate_canonical": mod["candidates"][0]["state_digest"] == CANDIDATE, "restart_ws_ok": analyze_ws(a2["websockets"])["ws_handshake_101"]}


def analyze_all(a: dict[str, Any], b: dict[str, Any], a2: dict[str, Any], baseline: dict[str, Any]) -> dict[str, dict[str, bool]]:
    live_f, live_auth = step(a, "live-completed"), step(a, "live-authoritative")
    models = step(a, "models-after-live")
    rp = step(a, "replay")
    return {"identity": analyze_identity(step(a, "signin")), "live": analyze_live(live_f, live_auth, step(a, "clients-rest"), baseline), "candidate": analyze_candidate(models, live_auth), "refresh": analyze_refresh(step(a, "refresh-mid-run")),
            "websocket": analyze_ws(a["websockets"]), "rounds_page": analyze_rounds_page(step(a, "rounds-page")), "global": analyze_global(step(a, "global-clients-view")), "replay": analyze_replay(rp, live_auth, step(a, "models-after-replay"), models),
            "isolation": analyze_isolation(b, a["liveRunId"]), "restart": analyze_restart(a2, live_auth, models), "clerk_network": {"clerk_hosts_contacted": bool(a["network"]["clerkOwnedHosts"]), "no_console_errors": a["console_errors"] == []}}


def mutate(name: str, a: dict[str, Any], b: dict[str, Any], a2: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str]:
    """Return mutated deep copies of the observations and the analyzer group that MUST report a failure."""
    a, b, a2 = copy.deepcopy(a), copy.deepcopy(b), copy.deepcopy(a2)
    lf, la, rp = step(a, "live-completed"), step(a, "live-authoritative"), step(a, "replay")
    m = {
        "REPLAY_SHOWS_OWNER_CARD": lambda: rp["facts"].update(ownerCards=1, myEdgeMentions=1, ownerClient=OWNER),
        "REPLAY_SHOWS_PARTICIPATION_SUMMARY": lambda: rp["facts"].update(myParticipation="MY FEDERATED PARTICIPATION"),
        "GLOBAL_CLIENTS_VIEW_SHOWS_OWNER": lambda: step(a, "global-clients-view").update(myEdgeMentions=1),
        "SECOND_OWNER_CARD": lambda: lf.update(ownerCards=2, myEdgeMentions=2),
        "OWNER_ON_SITE_01": lambda: lf.update(ownerClient="SIM_FL_SITE_01"),
        "NINTH_CLIENT_CARD": lambda: lf.update(clientIds=[*lf["clientIds"], "SIM_FL_SITE_08"]),
        "PEER_COUNT_NOT_7": lambda: lf.update(peerCards=6),
        "OWNER_EXAMPLES_NOT_93": lambda: lf.update(myExamples="92"),
        "OWNER_EXAMPLES_NOT_EVENT_DERIVED": lambda: la["update_digests"]["1"][OWNER].update(examples_seen=7),
        "UPDATE_COUNT_NOT_24": lambda: la.update(update_ready_events=23),
        "ROUNDS_NOT_3": lambda: la["update_digests"].pop("3"),
        "UPDATES_PER_ROUND_NOT_8": lambda: la["update_digests"]["2"].pop("SIM_FL_SITE_07"),
        "OWNER_UPDATES_UI_NOT_3": lambda: lf.update(myUpdates="2 / 3"),
        "RAW_EXAMPLES_SENT_NONZERO": lambda: lf.update(rawSent="93"),
        "CONTRIBUTION_WORDING_PRESENT": lambda: lf.update(forbiddenWords=["contribution"]),
        "PERSONALIZED_WORDING_PRESENT": lambda: lf.update(forbiddenWords=["personalized"]),
        "CONSENT_CONTROL_PRESENT": lambda: lf.update(interactiveConsentControls=1),
        "SYNTHETIC_WORDING_MISSING": lambda: lf.update(ownerText="MY EDGE CLIENT"),
        "CANDIDATE_DIGEST_CHANGED": lambda: step(a, "models-after-live")["candidates"][0].update(state_digest="0" * 64),
        "CANDIDATE_PRODUCTION_DEPLOYED": lambda: step(a, "models-after-live")["candidates"][0].update(production_deployed=True),
        "REFRESH_LOSES_OWNER_CARD": lambda: step(a, "refresh-mid-run").update(after_ownerCards=0),
        "RESTART_LOSES_OWNER_CARD": lambda: step(a2, "live-reconstructed").update(ownerCards=0),
        "RESTART_CHANGES_CANDIDATE": lambda: step(a2, "models-after-restart")["candidates"][0].update(state_digest="1" * 64),
        "USER_B_READS_A_RUN": lambda: step(b, "b-rest-probes")["results"][0].update(status=200),
        "USER_B_WS_ACCEPTED": lambda: step(b, "b-websocket")["federation"].update(closeCode=1000, opened=True, frames=5),
        "USER_B_SEES_OWNER_ON_A_RUN": lambda: step(b, "b-views-a-live-page").update(ownerCards=1),
        "TOKEN_IN_WS_URL": lambda: a["websockets"][0].update(urlHasToken=True),
        "DEMO_FALLBACK_IN_CLERK_MODE": lambda: step(a, "signin")["system"].update(auth_provider="DEMO"),
    }
    m[name]()
    group = {"REPLAY_SHOWS_OWNER_CARD": "replay", "REPLAY_SHOWS_PARTICIPATION_SUMMARY": "replay", "GLOBAL_CLIENTS_VIEW_SHOWS_OWNER": "global", "REFRESH_LOSES_OWNER_CARD": "refresh", "RESTART_LOSES_OWNER_CARD": "restart", "RESTART_CHANGES_CANDIDATE": "restart",
             "USER_B_READS_A_RUN": "isolation", "USER_B_WS_ACCEPTED": "isolation", "USER_B_SEES_OWNER_ON_A_RUN": "isolation", "TOKEN_IN_WS_URL": "websocket", "DEMO_FALLBACK_IN_CLERK_MODE": "identity", "CANDIDATE_DIGEST_CHANGED": "candidate", "CANDIDATE_PRODUCTION_DEPLOYED": "candidate"}.get(name, "live")
    return a, b, a2, group


OBSERVATION_MUTATIONS = ("REPLAY_SHOWS_OWNER_CARD", "REPLAY_SHOWS_PARTICIPATION_SUMMARY", "GLOBAL_CLIENTS_VIEW_SHOWS_OWNER", "SECOND_OWNER_CARD", "OWNER_ON_SITE_01", "NINTH_CLIENT_CARD", "PEER_COUNT_NOT_7", "OWNER_EXAMPLES_NOT_93", "OWNER_EXAMPLES_NOT_EVENT_DERIVED",
                         "UPDATE_COUNT_NOT_24", "ROUNDS_NOT_3", "UPDATES_PER_ROUND_NOT_8", "OWNER_UPDATES_UI_NOT_3", "RAW_EXAMPLES_SENT_NONZERO", "CONTRIBUTION_WORDING_PRESENT", "PERSONALIZED_WORDING_PRESENT", "CONSENT_CONTROL_PRESENT", "SYNTHETIC_WORDING_MISSING",
                         "CANDIDATE_DIGEST_CHANGED", "CANDIDATE_PRODUCTION_DEPLOYED", "REFRESH_LOSES_OWNER_CARD", "RESTART_LOSES_OWNER_CARD", "RESTART_CHANGES_CANDIDATE", "USER_B_READS_A_RUN", "USER_B_WS_ACCEPTED", "USER_B_SEES_OWNER_ON_A_RUN", "TOKEN_IN_WS_URL",
                         "DEMO_FALLBACK_IN_CLERK_MODE")
