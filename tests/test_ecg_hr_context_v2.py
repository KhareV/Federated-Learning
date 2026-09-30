from __future__ import annotations

import numpy as np
import pytest

from preprocessing.ecg_hr_context import GQRS_ID, XQRS_ID, estimate_hr_at


def synthetic_ecg(rate_bpm: int, seconds: int = 20, fs: int = 250) -> np.ndarray:
    time = np.arange(seconds * fs) / fs
    signal = 0.03 * np.sin(2 * np.pi * 1.1 * time)
    for beat_time in np.arange(0.8, seconds, 60 / rate_bpm):
        signal += 1.2 * np.exp(-0.5 * ((time - beat_time) / 0.018) ** 2)
        signal -= 0.25 * np.exp(-0.5 * ((time - (beat_time - 0.035)) / 0.012) ** 2)
        signal -= 0.35 * np.exp(-0.5 * ((time - (beat_time + 0.040)) / 0.014) ** 2)
    return signal


@pytest.mark.parametrize("candidate", [XQRS_ID, GQRS_ID])
@pytest.mark.parametrize("rate", [50, 60, 75, 90, 120, 150])
def test_known_synthetic_rates(candidate: str, rate: int) -> None:
    signal = synthetic_ecg(rate)
    result = estimate_hr_at(signal, timestamp_seconds=19, candidate_id=candidate)
    assert result.valid is True
    assert result.hr_ecg_bpm == pytest.approx(rate, abs=1.5)


@pytest.mark.parametrize("candidate", [XQRS_ID, GQRS_ID])
def test_future_append_does_not_change_estimate(candidate: str) -> None:
    prefix = synthetic_ecg(75, seconds=20)
    first = estimate_hr_at(prefix, timestamp_seconds=19, candidate_id=candidate)
    future = np.random.default_rng(20260927).normal(size=2500)
    second = estimate_hr_at(
        np.concatenate([prefix, future]),
        timestamp_seconds=19,
        candidate_id=candidate,
    )
    assert first == second


def test_incomplete_history_is_invalid() -> None:
    result = estimate_hr_at(np.zeros(2000), timestamp_seconds=7, candidate_id=XQRS_ID)
    assert result.valid is False
    assert result.hr_ecg_bpm is None


def test_chunk_reassembly_uses_same_production_estimator() -> None:
    signal = synthetic_ecg(90)
    chunks = [signal[:613], signal[613:2017], signal[2017:]]
    chunked = estimate_hr_at(np.concatenate(chunks), timestamp_seconds=19, candidate_id=XQRS_ID)
    continuous = estimate_hr_at(signal, timestamp_seconds=19, candidate_id=XQRS_ID)
    assert chunked == continuous
