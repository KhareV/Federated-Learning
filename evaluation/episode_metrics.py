"""Traceable deterministic operational metrics for T023."""

from __future__ import annotations

from itertools import pairwise
from typing import Any


def metrics_from_trace(rows: list[dict[str, Any]]) -> dict[str, float | int | None]:
    slots = len(rows)
    usable = sum(row["ecg_quality"] != "UNUSABLE" for row in rows)
    opens = sum(bool(row["episode_opened"]) for row in rows)
    state_changes = sum(
        left["monitoring_state"] != right["monitoring_state"]
        for left, right in pairwise(rows)
    )
    recheck = sum(row["monitoring_state"] == "RECHECK_SENSOR" for row in rows)
    recheck_entries = sum(
        right["monitoring_state"] == "RECHECK_SENSOR"
        and left["monitoring_state"] != "RECHECK_SENSOR"
        for left, right in pairwise(rows)
    )
    context_unavailable = sum(not bool(row["context_available"]) for row in rows)
    warning = sum(bool(row["quality_warning"]) for row in rows)
    warning_runs = sum(
        bool(row["quality_warning"]) and (index == 0 or not rows[index - 1]["quality_warning"])
        for index, row in enumerate(rows)
    )
    candidate_hours = slots * 5 / 3600
    usable_hours = usable * 5 / 3600
    return {
        "candidate_slots": slots,
        "usable_slots": usable,
        "candidate_monitoring_hours": candidate_hours,
        "usable_monitoring_hours": usable_hours,
        "alert_episode_opens": opens,
        "alert_episodes_per_usable_hour": opens / usable_hours if usable_hours else None,
        "state_transitions": state_changes,
        "state_chattering_per_hour": state_changes / candidate_hours if candidate_hours else None,
        "recheck_sensor_slots": recheck,
        "recheck_sensor_fraction": recheck / slots if slots else 0.0,
        "recheck_sensor_entries": recheck_entries,
        "recheck_sensor_entries_per_hour": (
            recheck_entries / candidate_hours if candidate_hours else None
        ),
        "prediction_suppression_rate": (slots - usable) / slots if slots else 0.0,
        "context_unavailable_fraction": context_unavailable / slots if slots else 0.0,
        "quality_warning_fraction": warning / slots if slots else 0.0,
        "quality_warning_runs": warning_runs,
        "quality_warning_duration_seconds": warning * 5,
    }
