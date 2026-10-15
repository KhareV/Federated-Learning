from __future__ import annotations

import datetime as dt
import math

from api.hardware_v2_experimental import (
    ADC_MIDPOINT, ASSUMPTIONS, LABEL, MAX_BRIDGE_US, SOURCE_HZ, build_windows, readings_to_records, window_key,
)

T0 = dt.datetime(2026, 10, 15, 12, 0, 0, tzinfo=dt.UTC)


def _readings(seconds: float, skip: tuple[float, float] | None = None, amp: float = 15.0, rate: int = 20):
    out = []
    for i in range(int(seconds * rate)):
        t = i / rate
        if skip and skip[0] <= t < skip[1]:
            continue
        phase = (t * 1.2) % 1
        ecg = int(ADC_MIDPOINT + (120 if phase < 0.06 else 0) + amp * math.sin(2 * math.pi * phase))
        out.append({"ordinal": len(out) + 1, "ingested_at": (T0 + dt.timedelta(seconds=t)).isoformat(),
                    "ecg": ecg, "bpm": 72, "spo2": 97})
    return out


def test_resampling_only_between_real_readings_and_never_across_gaps():
    records, _ = readings_to_records(_readings(10, skip=(4.0, 6.0)), "HW-X")
    indices = [r.sample_index for r in records]
    assert indices == sorted(set(indices))
    stamps = [r.timestamp_us for r in records]
    assert all(b - a > 0 for a, b in zip(stamps, stamps[1:], strict=False))
    biggest = max(b - a for a, b in zip(stamps, stamps[1:], strict=False))
    assert biggest > 1_900_000 and biggest >= MAX_BRIDGE_US, "the 2 s gap must remain a gap"
    assert not any(4_100_000 < s < 5_900_000 for s in stamps), "no invented samples inside the gap"


def test_adc_midpoint_is_zero_and_values_come_from_readings():
    flat = [{"ordinal": i, "ingested_at": (T0 + dt.timedelta(milliseconds=50 * i)).isoformat(), "ecg": ADC_MIDPOINT,
             "bpm": None, "spo2": None} for i in range(40)]
    records, _ = readings_to_records(flat, "HW-X")
    assert records and {r.ecg_raw for r in records} == {0}
    assert all(r.pr_ppg_bpm is None and r.spo2_valid is False for r in records)
    assert abs(records[1].timestamp_us - records[0].timestamp_us - 1e6 / SOURCE_HZ) < 2


def test_windows_follow_the_unchanged_runtime_contract_and_stay_labelled_experimental():
    windows, summary = build_windows(_readings(32), "HW-X", "MODEL_V2_FINAL")
    assert summary["windows"] == len(windows) >= 3
    first = windows[0]
    assert first["timestamp_us"] == 15_000_000 and len(first["ecg"]["samples"]) == 2500
    assert first["ecg"]["target_hz"] == 250 and first["ecg"]["window_seconds"] == 10
    assert first["ecg_quality"] == "VALID"
    assert first["ppg_context"]["pr_bpm"] == 72.0 and first["ppg_context"]["quality"] is None
    assert "NOT VALID" in LABEL and "NOT DIAGNOSTIC" in LABEL and "unverified" in ASSUMPTIONS["adc_scaling"]
    assert window_key(first) != window_key(windows[1])


def test_gap_makes_the_overlapping_windows_unusable_not_silently_clean():
    windows, _ = build_windows(_readings(40, skip=(20.0, 23.0)), "HW-X", "MODEL_V2_FINAL")
    flagged = [w for w in windows if w["diagnostics"]["long_gap_or_missing"]]
    assert flagged and all(w["ecg_quality"] == "UNUSABLE" for w in flagged)
