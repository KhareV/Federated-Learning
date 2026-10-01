"""T032 stateful HTTP-layer coverage: K2 episode-open debounce, M2 episode-close debounce +
cooldown, DEGRADED handling, context availability, session isolation, and same-session
concurrency safety. Exercises the real, frozen ALERT_POLICY_V1 state machine
(`fusion.episode_manager.AlertEpisodeManager`) through the real HTTP route, via the
deterministic fake runtime in tests/_t032_support.py (never MODEL_V1/torch).
"""

from __future__ import annotations

import threading

from fastapi.testclient import TestClient

from tests._t032_support import build_app, make_payload, real_policy

POLICY = real_policy()
CADENCE_US = 5_000_000  # configs/alert_policy_v1.yaml: window_cadence_seconds == 5


def _with_context(payload: dict) -> dict:
    payload["ppg_context"] = {
        "quality": "VALID",
        "pr_bpm": 70.0,
        "spo2_pct": 98.0,
        "spo2_valid": True,
    }
    return payload


def test_k2_requires_two_consecutive_above_threshold_windows_to_open() -> None:
    app, _, _ = build_app(probability=0.95)
    client = TestClient(app)
    sid = "STATE-K2"

    first = client.post(
        "/v1/infer-window", json=_with_context(make_payload(sid, 1_000_000))
    )
    assert first.status_code == 200
    assert first.json()["monitoring_state"] == "NORMAL_MONITORED_PATTERN"
    assert first.json()["context"]["possible_pattern"] is False

    second = client.post(
        "/v1/infer-window", json=_with_context(make_payload(sid, 1_000_000 + CADENCE_US))
    )
    assert second.status_code == 200
    assert second.json()["monitoring_state"] == "POTENTIAL_ECTOPY_ASSOCIATED_PATTERN"


def test_m2_requires_two_consecutive_below_threshold_windows_to_close_then_cooldown() -> None:
    app, runtime, _ = build_app(probability=0.95)
    client = TestClient(app)
    sid = "STATE-M2"
    ts = 1_000_000

    client.post("/v1/infer-window", json=_with_context(make_payload(sid, ts)))
    ts += CADENCE_US
    opened = client.post("/v1/infer-window", json=_with_context(make_payload(sid, ts)))
    assert opened.json()["monitoring_state"] == "POTENTIAL_ECTOPY_ASSOCIATED_PATTERN"

    runtime.probability = 0.05
    ts += CADENCE_US
    below_1 = client.post("/v1/infer-window", json=_with_context(make_payload(sid, ts)))
    assert below_1.json()["monitoring_state"] == "POTENTIAL_ECTOPY_ASSOCIATED_PATTERN"

    ts += CADENCE_US
    below_2 = client.post("/v1/infer-window", json=_with_context(make_payload(sid, ts)))
    assert below_2.json()["monitoring_state"] == "NORMAL_MONITORED_PATTERN"


def test_cooldown_prevents_reopen_until_elapsed() -> None:
    app, runtime, _ = build_app(probability=0.95)
    client = TestClient(app)
    sid = "STATE-COOLDOWN"
    ts = 1_000_000

    client.post("/v1/infer-window", json=_with_context(make_payload(sid, ts)))
    ts += CADENCE_US
    client.post("/v1/infer-window", json=_with_context(make_payload(sid, ts)))  # opened

    runtime.probability = 0.05
    ts += CADENCE_US
    client.post("/v1/infer-window", json=_with_context(make_payload(sid, ts)))
    ts += CADENCE_US
    closed = client.post("/v1/infer-window", json=_with_context(make_payload(sid, ts)))
    assert closed.json()["monitoring_state"] == "NORMAL_MONITORED_PATTERN"

    # Still within the cooldown window: back-to-back above-threshold windows must NOT reopen.
    runtime.probability = 0.95
    ts += 1_000
    still_cooling = client.post(
        "/v1/infer-window", json=_with_context(make_payload(sid, ts))
    )
    ts += 1_000
    still_cooling_2 = client.post(
        "/v1/infer-window", json=_with_context(make_payload(sid, ts))
    )
    assert still_cooling.json()["monitoring_state"] == "NORMAL_MONITORED_PATTERN"
    assert still_cooling_2.json()["monitoring_state"] == "NORMAL_MONITORED_PATTERN"

    # After the cooldown elapses, K2 can open a fresh episode again.
    ts += POLICY.cooldown_us
    reopen_1 = client.post("/v1/infer-window", json=_with_context(make_payload(sid, ts)))
    ts += CADENCE_US
    reopen_2 = client.post("/v1/infer-window", json=_with_context(make_payload(sid, ts)))
    assert reopen_1.json()["monitoring_state"] == "NORMAL_MONITORED_PATTERN"
    assert reopen_2.json()["monitoring_state"] == "POTENTIAL_ECTOPY_ASSOCIATED_PATTERN"


def test_degraded_ecg_quality_maps_to_recheck_sensor_and_warns() -> None:
    app, _, _ = build_app(probability=0.95)
    client = TestClient(app)
    response = client.post(
        "/v1/infer-window",
        json=_with_context(make_payload("STATE-DEGRADED", 1_000_000, ecg_quality="DEGRADED")),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["monitoring_state"] == "RECHECK_SENSOR"
    assert body["context"]["possible_pattern"] is True


def test_missing_context_reports_context_unavailable() -> None:
    app, _, _ = build_app(probability=0.05)
    client = TestClient(app)
    response = client.post(
        "/v1/infer-window", json=make_payload("STATE-NOCTX", 1_000_000)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["monitoring_state"] == "CONTEXT_UNAVAILABLE"
    assert body["context"]["context_available"] is False


def test_out_of_range_spo2_degrades_to_unavailable_instead_of_crashing() -> None:
    """validate_observation() would raise INVALID_VALID_SPO2 for spo2_valid=True with an
    out-of-range spo2_pct; the route must sanitize this to 'unavailable' before it ever
    reaches fusion.state_machine, never surfacing as a 500."""
    app, _, _ = build_app(probability=0.05)
    client = TestClient(app)
    payload = make_payload("STATE-BADCTX", 1_000_000)
    payload["ppg_context"] = {
        "quality": "VALID",
        "pr_bpm": 70.0,
        "spo2_pct": 150.0,
        "spo2_valid": True,
    }
    response = client.post("/v1/infer-window", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["context"]["spo2_valid"] is False
    assert body["monitoring_state"] == "CONTEXT_UNAVAILABLE"


def test_session_state_does_not_leak_between_session_ids() -> None:
    app, _, _ = build_app(probability=0.95)
    client = TestClient(app)
    sid_a, sid_b = "ISO-A", "ISO-B"

    client.post("/v1/infer-window", json=_with_context(make_payload(sid_a, 1_000_000)))
    client.post(
        "/v1/infer-window", json=_with_context(make_payload(sid_a, 1_000_000 + CADENCE_US))
    )
    opened_a = client.post(
        "/v1/infer-window", json=_with_context(make_payload(sid_a, 1_000_000 + 2 * CADENCE_US))
    )
    assert opened_a.json()["monitoring_state"] == "POTENTIAL_ECTOPY_ASSOCIATED_PATTERN"

    first_b = client.post(
        "/v1/infer-window", json=_with_context(make_payload(sid_b, 9_000_000))
    )
    assert first_b.json()["monitoring_state"] == "NORMAL_MONITORED_PATTERN"
    assert first_b.json()["context"]["possible_pattern"] is False


def test_session_timestamps_are_independent_per_session() -> None:
    app, _, _ = build_app(probability=0.05)
    client = TestClient(app)
    r_a = client.post("/v1/infer-window", json=make_payload("ISO-TS-A", 5_000_000))
    r_b = client.post("/v1/infer-window", json=make_payload("ISO-TS-B", 5_000_000))
    assert r_a.status_code == 200
    assert r_b.status_code == 200


def test_same_session_concurrent_requests_serialize_without_corruption() -> None:
    """Fires two requests with the SAME timestamp at the SAME session concurrently. The
    per-session lock must serialize them: exactly one succeeds and the other is rejected as
    non-monotonic -- never both succeeding, and never a crash/race condition."""
    app, _, _ = build_app(probability=0.05)
    client = TestClient(app)
    sid = "CONCURRENT-1"
    client.post("/v1/infer-window", json=make_payload(sid, 1_000_000))  # establishes baseline

    results: list[int] = []
    results_lock = threading.Lock()
    barrier = threading.Barrier(2)

    def fire() -> None:
        barrier.wait()
        response = client.post(
            "/v1/infer-window", json=make_payload(sid, 2_000_000)
        )
        with results_lock:
            results.append(response.status_code)

    threads = [threading.Thread(target=fire) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(results) == [200, 400]


def test_concurrent_requests_across_different_sessions_do_not_contend() -> None:
    app, _, _ = build_app(probability=0.05)
    client = TestClient(app)
    results: dict[str, int] = {}
    results_lock = threading.Lock()
    barrier = threading.Barrier(2)

    def fire(session_id: str) -> None:
        barrier.wait()
        response = client.post(
            "/v1/infer-window", json=make_payload(session_id, 1_000_000)
        )
        with results_lock:
            results[session_id] = response.status_code

    threads = [
        threading.Thread(target=fire, args=("PARALLEL-A",)),
        threading.Thread(target=fire, args=("PARALLEL-B",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results == {"PARALLEL-A": 200, "PARALLEL-B": 200}
