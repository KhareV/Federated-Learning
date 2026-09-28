"""AAMI_SVF_WINDOW_V1 window-target decision rule (datasets.labels.classify_window_target):
boundary fixtures for positive, negative, every exclusion reason, and the mappable-count edge
-- R01.1's validation method. This is a pure decision rule over already-mapped beat classes; no
real signal window is built anywhere in these tests."""

import pytest

from datasets.labels import (
    MIN_MAPPABLE_BEATS,
    UNMAPPABLE,
    classify_window_target,
)


def test_positive_window_requires_at_least_one_svf_beat_and_no_exclusion() -> None:
    beats = ["N", "N", "N", "N", "V"]
    result = classify_window_target(beats)
    assert result.target == 1
    assert result.label == "SVF_CONTAINING_WINDOW"
    assert result.exclusion_reason is None
    assert result.mappable_beat_count == 5


@pytest.mark.parametrize("svf_class", ["S", "V", "F"])
def test_positive_window_accepts_any_of_s_v_f(svf_class: str) -> None:
    beats = ["N", "N", "N", "N", svf_class]
    result = classify_window_target(beats)
    assert result.target == 1


def test_negative_window_requires_only_mapped_n_beats() -> None:
    beats = ["N", "N", "N", "N", "N"]
    result = classify_window_target(beats)
    assert result.target == 0
    assert result.label == "N_ONLY_WINDOW"
    assert result.exclusion_reason is None


def test_window_with_q_beat_is_excluded_even_with_svf_present() -> None:
    beats = ["N", "N", "N", "V", "Q"]
    result = classify_window_target(beats)
    assert result.target is None
    assert result.label == "EXCLUDED"
    assert result.exclusion_reason == "EXCLUDE_Q_OR_UNMAPPABLE_BEAT_PRESENT"


def test_window_with_unmappable_beat_is_excluded() -> None:
    beats = ["N", "N", "N", "N", UNMAPPABLE]
    result = classify_window_target(beats)
    assert result.target is None
    assert result.exclusion_reason == "EXCLUDE_Q_OR_UNMAPPABLE_BEAT_PRESENT"


def test_window_below_minimum_mappable_beats_is_excluded() -> None:
    beats = ["N"] * (MIN_MAPPABLE_BEATS - 1)
    result = classify_window_target(beats)
    assert result.target is None
    assert result.exclusion_reason == "EXCLUDE_FEWER_THAN_MIN_MAPPABLE_BEATS"
    assert result.mappable_beat_count == MIN_MAPPABLE_BEATS - 1


def test_window_at_exactly_minimum_mappable_beats_is_eligible() -> None:
    beats = ["N"] * MIN_MAPPABLE_BEATS
    result = classify_window_target(beats)
    assert result.target == 0
    assert result.exclusion_reason is None


def test_empty_window_is_excluded_for_too_few_beats() -> None:
    result = classify_window_target([])
    assert result.target is None
    assert result.exclusion_reason == "EXCLUDE_FEWER_THAN_MIN_MAPPABLE_BEATS"
    assert result.mappable_beat_count == 0
