from __future__ import annotations

from evaluation.episode_metrics import metrics_from_trace


def _row(state: str, *, opened: bool = False, quality: str = "VALID", warning: bool = False):
    return {
        "monitoring_state": state,
        "episode_opened": opened,
        "ecg_quality": quality,
        "context_available": state != "CONTEXT_UNAVAILABLE",
        "quality_warning": warning,
    }


def test_metrics_trace_exact_events_and_denominators() -> None:
    rows = [
        _row("NORMAL_MONITORED_PATTERN"),
        _row("POTENTIAL_ECTOPY_ASSOCIATED_PATTERN", opened=True),
        _row("RECHECK_SENSOR", quality="UNUSABLE", warning=True),
        _row("RECHECK_SENSOR", quality="UNUSABLE", warning=True),
    ]
    result = metrics_from_trace(rows)
    assert result["candidate_slots"] == 4
    assert result["usable_slots"] == 2
    assert result["alert_episode_opens"] == 1
    assert result["state_transitions"] == 2
    assert result["recheck_sensor_slots"] == 2
    assert result["recheck_sensor_entries"] == 1
    assert result["prediction_suppression_rate"] == 0.5
    assert result["quality_warning_runs"] == 1
    assert result["quality_warning_duration_seconds"] == 10


def test_zero_usable_hours_produces_null_rate() -> None:
    rows = [_row("RECHECK_SENSOR", quality="UNUSABLE")]
    assert metrics_from_trace(rows)["alert_episodes_per_usable_hour"] is None
