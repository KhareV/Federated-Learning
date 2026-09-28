"""Offline tests for the locked exact-MLII lead-selection policy. No network, no real data."""

import pytest

from datasets.mitdb import ExclusionReason, inspect_record, select_mlii_channel


def test_mlii_first_position() -> None:
    assert select_mlii_channel(["MLII", "V1"]) == 0


def test_mlii_second_position_not_index_zero() -> None:
    """Record 114's documented lead swap: the selector must not assume MLII is channel 0."""
    assert select_mlii_channel(["V5", "MLII"]) == 1


def test_no_exact_mlii_returns_none() -> None:
    assert select_mlii_channel(["V5", "V1"]) is None


def test_duplicate_mlii_raises_ambiguous() -> None:
    with pytest.raises(ValueError, match="AMBIGUOUS"):
        select_mlii_channel(["MLII", "MLII"])


def test_exact_case_sensitive_match_only() -> None:
    assert select_mlii_channel(["Mlii", "V1"]) is None
    assert select_mlii_channel(["mlii"]) is None


def test_near_miss_names_are_not_matched() -> None:
    assert select_mlii_channel(["II", "V1"]) is None
    assert select_mlii_channel([" MLII ", "V1"]) is None
    assert select_mlii_channel(["MLIII"]) is None
    assert select_mlii_channel(["MLI"]) is None


def test_empty_signal_list_returns_none() -> None:
    assert select_mlii_channel([]) is None


def test_no_index_based_fallback_in_source() -> None:
    """The selector's source must never fall back to a fixed channel index."""
    import inspect

    source = inspect.getsource(select_mlii_channel)
    forbidden = ("sig_name[0]", "channel = 0", "index = 0")
    for pattern in forbidden:
        assert pattern not in source


def test_inspect_record_reports_malformed_header_without_raising(tmp_path, monkeypatch) -> None:
    def _broken_read_header(record_id, raw_root):
        raise OSError("no such record")

    monkeypatch.setattr("datasets.mitdb.read_header", _broken_read_header)
    selection = inspect_record("999", tmp_path)
    assert selection.eligible is False
    assert selection.exclusion_reason == ExclusionReason.MALFORMED_HEADER


def test_inspect_record_ambiguous_mlii_is_excluded_not_arbitrary(tmp_path, monkeypatch) -> None:
    from datasets.mitdb import HeaderInfo

    def _fake_header(record_id, raw_root):
        return HeaderInfo(
            record_id=record_id,
            fs=360.0,
            sig_len=1000,
            n_sig=2,
            sig_name=("MLII", "MLII"),
            units=("mV", "mV"),
            duration_seconds=1000 / 360.0,
        )

    monkeypatch.setattr("datasets.mitdb.read_header", _fake_header)
    selection = inspect_record("998", tmp_path)
    assert selection.eligible is False
    assert selection.exclusion_reason == ExclusionReason.AMBIGUOUS_MULTIPLE_MLII


def test_inspect_record_eligible_with_exact_mlii(tmp_path, monkeypatch) -> None:
    from datasets.mitdb import HeaderInfo

    def _fake_header(record_id, raw_root):
        return HeaderInfo(
            record_id=record_id,
            fs=360.0,
            sig_len=1000,
            n_sig=2,
            sig_name=("V5", "MLII"),
            units=("mV", "mV"),
            duration_seconds=1000 / 360.0,
        )

    monkeypatch.setattr("datasets.mitdb.read_header", _fake_header)
    selection = inspect_record("997", tmp_path)
    assert selection.eligible is True
    assert selection.mlii_channel_index == 1
    assert selection.exclusion_reason == ExclusionReason.NONE
