"""CAP-003: real-inference integration. Every test here crosses real localhost HTTP into a FRESH
released SOFTWARE_SYSTEM_V2 process (`python -m scripts.run_nhm_default`): no mock, no scripted
probabilities. Model outputs are never asserted - only structure, identity, contract behaviour."""

from __future__ import annotations

import pytest

from product.events import parse_monitoring_event
from scripts.run_capstone_monitoring_e2e import (
    PREDECLARED,
    launch_released_inference,
    run_session,
    summarize,
)
from tests.capstone_device_support import replay


@pytest.fixture(scope="module")
def released():
    with launch_released_inference() as (base, info):
        yield base, info


def _go(released, scenario_id: str):
    base, _ = released
    result = run_session(scenario_id, base, f"E2E-TEST-{scenario_id}")
    return result, summarize(result)


def test_the_service_under_test_is_the_released_software_system_v2_default(released) -> None:
    _, info = released
    assert info["fresh_process"] is True and info["profile"] == "default"
    assert "SOFTWARE_SYSTEM_V2 default binding" in info["service_title"]
    assert info["paths"] == ["/v1/infer-window"]  # the frozen API only; no selector surface


def test_mixed_scenario_matches_the_predeclared_real_inference_invariants(released) -> None:
    result, summary = _go(released, "MIXED_MONITORING_SESSION")
    assert summary["terminal_session_state"] == PREDECLARED["terminal_session_state"]
    assert len(summary["windows"]) == PREDECLARED["windows"]
    assert len(result["inference_attempts"]) == PREDECLARED["attempts"]
    counts = summary["http_status_counts"]
    assert counts == {"200": PREDECLARED["http_200"], "422": PREDECLARED["http_422"]}
    assert summary["successful_model_ids"] == PREDECLARED["successful_model_ids"]
    assert summary["successful_calibration_ids"] == PREDECLARED["successful_calibration_ids"]
    quality = [w["ecg_quality"] for w in summary["windows"]]
    assert quality.count("VALID") == PREDECLARED["valid"]
    assert quality.count("UNUSABLE") == PREDECLARED["unusable"]
    assert summary["sequence_contiguous"] and summary["session_state_sequence"] == [
        "MONITORING", "STOPPING", "COMPLETED"]
    assert result["late_stop_status"] == 409
    for event in result["events"]:
        parse_monitoring_event(event)
    assert summary["claims"] == {
        "physical_hardware_used": False, "simulation_truth_used": False,
        "fl_training_used": False, "mock_model_used": False, "model_efficacy_claimed": False,
        "note": "systems/product integration evidence; not clinical evidence"}


def test_422_windows_have_quality_but_no_inference_result_against_the_real_api(released) -> None:
    result, summary = _go(released, "POOR_SIGNAL")
    events = result["events"]
    unusable = [w for w in summary["windows"] if w["http_status"] == 422]
    assert unusable and all(w["ecg_quality"] == "UNUSABLE" for w in unusable)
    inferred = {e["payload"]["timestamp_us"] for e in events
                if e["event_type"] == "inference.result"}
    assert not inferred & {w["timestamp_us"] for w in unusable}
    assert len(inferred) == sum(1 for w in summary["windows"] if w["http_status"] == 200)
    assert not [e for e in events if e["event_type"] == "system.error"]


def test_context_loss_keeps_ecg_inference_running_with_unavailable_context(released) -> None:
    _, summary = _go(released, "CONTEXT_LOSS")
    assert set(summary["http_status_counts"]) == {"200"}
    availability = summary["context_availability_sequence"]
    assert True in availability and False in availability  # response semantics, not the adapter's
    assert summary["terminal_session_state"] == "COMPLETED"


def test_disconnect_reconnect_keeps_the_session_monitoring_with_a_ui_gap(released) -> None:
    result, summary = _go(released, "DISCONNECT_RECONNECT")
    assert summary["device_state_sequence"] == [
        "STREAMING", "DISCONNECTED", "RECONNECTING", "CONNECTED", "STREAMING", "STOPPED"]
    assert summary["session_state_sequence"] == ["MONITORING", "STOPPING", "COMPLETED"]
    assert summary["waveform"]["null_intervals"] == [[25200, 30599]]
    cap002 = replay("DISCONNECT_RECONNECT")["semantic"]["records"]
    assert result["scientific_trace"]["records_sha256"] == cap002["records_sha256"]


def test_normal_monitoring_is_accepted_end_to_end_by_the_released_system(released) -> None:
    result, summary = _go(released, "NORMAL_MONITORING")
    assert set(summary["http_status_counts"]) == {"200"} and len(summary["windows"]) == 21
    assert {w["model_id"] for w in summary["windows"]} == {"MODEL_V2_FINAL"}
    assert summary["waveform"]["null_intervals"] == []
    assert result["session"]["runtime"]["software_system_id"] == "SOFTWARE_SYSTEM_V2"
