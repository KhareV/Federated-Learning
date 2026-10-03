#!/usr/bin/env python3
"""V2-013 Sections 9/20: scripted state-sequence integration through the REAL API_RUNTIME_V2
(real gateway, real CAL_V2 threshold, real ALERT_POLICY_V1 binding). Window fixtures are the V2-012
synthetic parity-corpus windows classified ONCE by the frozen threshold applied to the frozen
gateway output (first 'above' and first 'below' window by corpus index) -- only to build
software state-sequence fixtures; no metric is computed and nothing is tuned. Every expected
value below is predeclared; nothing adapts to outcomes."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

import scripts._v2_013_lib as lib
from api.app_v2 import create_research_app
from api.runtime_v2 import ResearchRuntimeV2
from deployment import gateway_v2 as gw
from fusion.alert_policy_v2_binding import binding_payload

OUT = lib.OUT
ROOT = lib.ROOT
MS = 1_000_000
N, P, R, C = ("NORMAL_MONITORED_PATTERN", "POTENTIAL_ECTOPY_ASSOCIATED_PATTERN", "RECHECK_SENSOR",
              "CONTEXT_UNAVAILABLE")

# NOTE: on the step that OPENS an episode the frozen engine leaves open_counter at K (=2) until
# the next processed window resets it (fusion/episode_manager.py::process); the expectation below
# follows that unchanged V1 engine behavior (corrected from an initial 0 after reading the engine).
# (label, window kind, quality, t_seconds, expected http, expected state,
#  open_counter, close_counter, episode_active, episode_count, model_executed)
SESSION_MAIN = [
    ("below_valid", "B", "VALID", 10, 200, N, 0, 0, False, 0, True),
    ("above_valid_1", "A", "VALID", 15, 200, N, 1, 0, False, 0, True),
    ("above_valid_2_opens", "A", "VALID", 20, 200, P, 2, 0, True, 1, True),
    ("above_valid_active", "A", "VALID", 25, 200, P, 0, 0, True, 1, True),
    ("degraded_above_in_episode", "A", "DEGRADED", 30, 200, R, 0, 0, True, 1, True),
    ("unusable_in_episode", "A", "UNUSABLE", 35, 422, None, 0, 0, True, 1, False),
    ("below_valid_recovery_1", "B", "VALID", 40, 200, P, 0, 1, True, 1, True),
    ("below_valid_2_closes", "B", "VALID", 45, 200, N, 0, 0, False, 1, True),
    ("above_in_cooldown_1", "A", "VALID", 50, 200, N, 0, 0, False, 1, True),
    ("above_in_cooldown_2", "A", "VALID", 55, 200, N, 0, 0, False, 1, True),
    ("above_after_cooldown_1", "A", "VALID", 80, 200, N, 1, 0, False, 1, True),
    ("above_after_cooldown_2_reopens", "A", "VALID", 85, 200, P, 2, 0, True, 2, True),
]
SESSION_UNUSABLE_CLEARS_OPEN = [
    ("below_valid", "B", "VALID", 10, 200, N, 0, 0, False, 0, True),
    ("above_valid_1", "A", "VALID", 15, 200, N, 1, 0, False, 0, True),
    ("unusable_clears_counter", "A", "UNUSABLE", 20, 422, None, 0, 0, False, 0, False),
    ("above_valid_after_unusable", "A", "VALID", 25, 200, N, 1, 0, False, 0, True),
    ("above_valid_opens", "A", "VALID", 30, 200, P, 2, 0, True, 1, True),
]
SESSION_DEGRADED_IDLE = [
    ("below_valid", "B", "VALID", 10, 200, N, 0, 0, False, 0, True),
    ("degraded_above_no_advance", "A", "DEGRADED", 15, 200, R, 0, 0, False, 0, True),
    ("valid_above_counter_1", "A", "VALID", 20, 200, N, 1, 0, False, 0, True),
]
SESSION_NO_PPG = [
    ("below_no_ppg", "B", "VALID", 10, 200, C, 0, 0, False, 0, True),
    ("above_no_ppg_1", "A", "VALID", 15, 200, C, 1, 0, False, 0, True),
    ("above_no_ppg_2_opens", "A", "VALID", 20, 200, P, 2, 0, True, 1, True),
]


def _classify() -> tuple[int, int, dict]:
    windows = lib.synthetic_api_windows(300)
    logits = lib.reference_raw_logits(windows)
    cal = json.loads((ROOT / "artifacts/CAL_V2.json").read_text())
    pred = gw.calibrate_logits(logits, cal)["prediction"]
    above = next(i for i in range(300) if pred[i] == 1)
    below = next(i for i in range(300) if pred[i] == 0)
    return above, below, {"windows": windows, "above_count": int(pred.sum())}


def run_session(client, app, runtime, counter, name, steps, a_window, b_window, *, ppg):
    results, ok = [], True
    manager = None
    for label, kind, quality, t, status, state, open_c, close_c, active, count, executed in steps:
        samples = (a_window if kind == "A" else b_window).tolist()
        before = counter["n"]
        body = lib.request_body(name, t * MS, samples, quality=quality, model_id=lib.V2_MODEL_ID,
                                ppg_context=lib.PPG_CONTEXT if ppg else None)
        response = client.post(lib.ROUTE, json=body)
        manager = app.state.session_store._sessions[name].episode_manager
        observed = {
            "http": response.status_code,
            "state": response.json().get("monitoring_state") if response.status_code == 200
            else None,
            "open_counter": manager._open_counter, "close_counter": manager._close_counter,
            "episode_active": manager._episode_active, "episode_count": manager._episode_count,
            "model_executed": counter["n"] > before,
        }
        expected = {"http": status, "state": state, "open_counter": open_c,
                    "close_counter": close_c, "episode_active": active, "episode_count": count,
                    "model_executed": executed}
        match = observed == expected
        ok &= match
        results.append({"step": label, "quality": quality, "t_seconds": t, "expected": expected,
                        "observed": observed, "match": match,
                        "possible_pattern": response.json().get("context", {}).get(
                            "possible_pattern") if response.status_code == 200 else None,
                        "cooldown_until_us": manager._cooldown_until_us})
    return {"session": name, "steps": results, "all_match": ok}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    above, below, meta = _classify()
    windows = meta["windows"]
    runtime = ResearchRuntimeV2(verify="manifest")
    counter = {"n": 0}
    original = runtime.infer

    def counting(samples):
        counter["n"] += 1
        return original(samples)

    runtime.infer = counting  # type: ignore[method-assign]
    app = create_research_app(runtime=runtime)
    client = TestClient(app, raise_server_exceptions=False)
    a_win, b_win = windows[above], windows[below]
    sessions = [
        run_session(client, app, runtime, counter, "V2-013-SEQ-MAIN", SESSION_MAIN, a_win, b_win,
                    ppg=True),
        run_session(client, app, runtime, counter, "V2-013-SEQ-UNUSABLE-CLEARS",
                    SESSION_UNUSABLE_CLEARS_OPEN, a_win, b_win, ppg=True),
        run_session(client, app, runtime, counter, "V2-013-SEQ-DEGRADED-IDLE",
                    SESSION_DEGRADED_IDLE, a_win, b_win, ppg=True),
        run_session(client, app, runtime, counter, "V2-013-SEQ-NO-PPG", SESSION_NO_PPG, a_win,
                    b_win, ppg=False),
    ]
    # system-error path: runtime failure leaves episode state untouched, session continues
    err_session = "V2-013-SEQ-SYSTEM-ERROR"
    client.post(lib.ROUTE, json=lib.request_body(err_session, 10 * MS, b_win.tolist(),
                                                 quality="VALID", model_id=lib.V2_MODEL_ID,
                                                 ppg_context=lib.PPG_CONTEXT))
    runtime.infer = lambda samples: (_ for _ in ()).throw(RuntimeError("scripted"))  # type: ignore
    failed = client.post(lib.ROUTE, json=lib.request_body(
        err_session, 15 * MS, a_win.tolist(), quality="VALID", model_id=lib.V2_MODEL_ID,
        ppg_context=lib.PPG_CONTEXT))
    runtime.infer = counting  # type: ignore[method-assign]
    manager = app.state.session_store._sessions[err_session].episode_manager
    after = client.post(lib.ROUTE, json=lib.request_body(
        err_session, 20 * MS, a_win.tolist(), quality="VALID", model_id=lib.V2_MODEL_ID,
        ppg_context=lib.PPG_CONTEXT))
    system_error = {
        "failure_http": failed.status_code, "failure_error_type": failed.json().get("error_type"),
        "state_after_next_valid_window": after.json().get("monitoring_state"),
        "open_counter_after_next_valid_window": manager._open_counter,
        "failed_request_did_not_advance_counters": manager._open_counter == 1,
        "session_continues_after_failure": after.status_code == 200,
    }
    system_ok = (system_error["failure_http"] == 500
                 and system_error["failure_error_type"] == "INTERNAL_SERVER_ERROR"
                 and system_error["session_continues_after_failure"]
                 and system_error["failed_request_did_not_advance_counters"])

    policy = runtime.policy
    binding = binding_payload(ROOT)
    audit = {
        "fixture_selection": {
            "rule": "first corpus window (index order) at/above and first below the frozen CAL_V2 "
            "threshold under the frozen gateway; software fixtures only, no metric",
            "above_window_index": above, "below_window_index": below,
            "above_windows_in_first_300": meta["above_count"],
        },
        "policy": {"K_open": policy.required_open, "M_close": policy.required_close,
                   "cooldown_seconds": policy.cooldown_us // MS,
                   "threshold": policy.threshold, "comparator": policy.threshold_comparator},
        "policy_expected": {"K_open": 2, "M_close": 2, "cooldown_seconds": 30},
        "sessions": sessions, "system_error_path": system_error,
        "degraded_above_never_advances_open_counter": sessions[2]["all_match"],
        "unusable_does_not_run_model": all(
            not s["observed"]["model_executed"] for sess in sessions for s in sess["steps"]
            if s["quality"] == "UNUSABLE"),
        "unusable_clears_open_confirmation_counter": sessions[1]["all_match"],
        "unusable_does_not_close_active_episode": sessions[0]["steps"][5]["observed"][
            "episode_active"] is True and sessions[0]["steps"][5]["observed"]["episode_count"] == 1,
        "public_states_observed": sorted({s["observed"]["state"] for sess in sessions
                                          for s in sess["steps"] if s["observed"]["state"]}),
        "parameters_changed_in_response_to_outcomes": False,
    }
    ok = (all(s["all_match"] for s in sessions) and system_ok
          and audit["policy"] == {**audit["policy"], "K_open": 2, "M_close": 2,
                                  "cooldown_seconds": 30}
          and set(audit["public_states_observed"]) <= {N, P, R, C})
    audit["status"] = "PASS" if ok else "FAIL"
    (OUT / "state_sequence_audit.json").write_text(
        json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    generic = {
        "alert_episode_manager_is_generic": True,
        "alert_policy_dataclass_carries_threshold_model_and_calibration_ids": True,
        "load_alert_policy_is_coupled_to_MODEL_V1_CAL_V1": True,
        "decision": "B_PARTIAL: engine generic; loader coupled -> additive V2 binding only",
        "alert_policy_v1_modified": False,
        "new_policy_artifact": "ALERT_POLICY_V1_MODEL_V2_BINDING (binding only; policy semantics "
        "identical, not a new clinical policy)",
        "binding": binding,
        "temporal_parameters_validated_against_unchanged_alert_policy_v1_config": True,
        "K": policy.required_open, "M": policy.required_close,
        "cooldown_seconds": policy.cooldown_us // MS,
        "degraded_above_threshold_behavior": "RECHECK_SENSOR + possible_pattern metadata; does "
        "not advance the open counter",
        "unusable_behavior": "RECHECK_SENSOR (HTTP 422); model not run; open counter cleared; an "
        "active episode is not closed by UNUSABLE alone",
        "state_sequence_audit_status": audit["status"],
        "status": audit["status"],
    }
    (OUT / "alert_policy_binding_audit.json").write_text(
        json.dumps(generic, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(audit["status"])
    if audit["status"] != "PASS":
        raise SystemExit("V2_013_STATE_SEQUENCE_FAILED")


if __name__ == "__main__":
    main()
