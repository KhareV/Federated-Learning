from __future__ import annotations

import numpy as np
import pytest

from evaluation.noise import (
    NoiseRobustnessError,
    StressWindow,
    fixed_paired_population,
    pair_id,
    validate_pair_rows,
)


def rows(labels: tuple[int, int] = (0, 1)) -> list[dict[str, int | str]]:
    return [
        {"pair_id": f"P{pair}", "snr_db": snr, "label": label}
        for pair, label in enumerate(labels)
        for snr in (24, 18, 12, 6, 0, -6)
    ]


def test_six_condition_pair_closure() -> None:
    result = validate_pair_rows(rows())
    assert result["pair_ids"] == 2
    assert result["complete_six_snr_pair_ids"] == 2


def test_missing_duplicate_and_label_mismatch_fail() -> None:
    fixture = rows()
    with pytest.raises(NoiseRobustnessError, match="NSTDB_PAIRING_FAILURE"):
        validate_pair_rows(fixture[:-1])
    duplicate = [*fixture, fixture[0]]
    with pytest.raises(NoiseRobustnessError, match="NSTDB_PAIRING_FAILURE"):
        validate_pair_rows(duplicate)
    mismatched = [dict(row) for row in fixture]
    mismatched[0]["label"] = 1
    with pytest.raises(NoiseRobustnessError, match="NSTDB_PAIRING_FAILURE"):
        validate_pair_rows(mismatched)


def test_quality_does_not_remove_offline_stress_pair() -> None:
    windows = []
    for snr, quality in zip((24, 18, 12, 6, 0, -6), ("VALID",) * 5 + ("UNUSABLE",), strict=True):
        windows.append(
            StressWindow(
                base_record_id="118",
                nstdb_record_id=f"118_{snr}",
                snr_db=snr,
                source_right_edge_index=3600,
                pair_id=pair_id("118", 3600),
                label=1,
                quality=quality,
                waveform=np.ones(2500),
            )
        )
    paired = fixed_paired_population(windows)
    assert len(paired) == 6
    assert {window.quality for window in paired} == {"VALID", "UNUSABLE"}


def test_label_invariance_is_required() -> None:
    fixture = rows(labels=(0,))
    fixture[-1]["label"] = 1
    with pytest.raises(NoiseRobustnessError, match="NSTDB_PAIRING_FAILURE"):
        validate_pair_rows(fixture)

