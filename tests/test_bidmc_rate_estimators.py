from __future__ import annotations

import numpy as np
import pytest

from preprocessing.context_quality import estimate_ecg_rate, estimate_ppg_rate


def _impulses(rate_bpm: int, sample_rate: int, amplitude: float = 5.0) -> np.ndarray:
    values = np.linspace(-0.01, 0.01, sample_rate * 10)
    period = round(sample_rate * 60 / rate_bpm)
    for position in range(period // 2, len(values), period):
        values[position] = amplitude
    return values


@pytest.mark.parametrize("rate", [60, 90, 120])
def test_ppg_known_rates(rate: int) -> None:
    estimate = estimate_ppg_rate(_impulses(rate, 100))
    assert estimate.rate_bpm == pytest.approx(rate, abs=1.0)


@pytest.mark.parametrize("rate", [60, 90, 120])
def test_ecg_known_rates(rate: int) -> None:
    estimate = estimate_ecg_rate(_impulses(rate, 250))
    assert estimate.rate_bpm == pytest.approx(rate, abs=1.0)
