from __future__ import annotations

from pathlib import Path

import pytest

from evaluation.noise import (
    EXPECTED_RECORDS,
    NoiseRobustnessError,
    snr_mapping,
    verify_official_sources,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("record_id", "expected"),
    [
        ("118e24", 24), ("118e18", 18), ("118e12", 12),
        ("118e06", 6), ("118e00", 0), ("118e_6", -6),
        ("119e24", 24), ("119e18", 18), ("119e12", 12),
        ("119e06", 6), ("119e00", 0), ("119e_6", -6),
    ],
)
def test_exact_snr_mapping(record_id: str, expected: int) -> None:
    assert snr_mapping(record_id) == expected


def test_pure_noise_is_not_a_stress_condition() -> None:
    with pytest.raises(NoiseRobustnessError, match="NOT_A_STRESS_RECORD"):
        snr_mapping("bw")


def test_official_source_allowlist_hashes_and_mlii() -> None:
    result = verify_official_sources(ROOT)
    assert result["stress_ecg_count"] == 12
    assert result["pure_noise_count"] == 3
    assert result["exact_MLII_all_stress_records"] is True
    assert result["fallback_used"] is False
    assert len(EXPECTED_RECORDS) == 12
