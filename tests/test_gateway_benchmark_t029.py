from __future__ import annotations

import math

import pytest

from deployment.benchmark import latency_summary


def test_latency_statistics_and_throughput_formula() -> None:
    samples = list(range(1_000_000, 2_000_000, 1000))
    report = latency_summary(samples)
    assert report["N"] == 1000
    assert report["p50_ms"] > 0
    assert report["p95_ms"] >= report["p50_ms"]
    assert report["throughput_windows_per_second"] == pytest.approx(
        1000 / report["total_timed_seconds"]
    )
    assert all(math.isfinite(float(value)) for value in report.values())


def test_latency_rejects_wrong_count() -> None:
    with pytest.raises(ValueError, match="1000"):
        latency_summary([1] * 999)
