"""Offline tests for the locked exact-Lead-II selection policy (INCART_EXACT_II_V1)."""

import pytest

from datasets.incart import ExclusionReason, inspect_record, select_exact_lead_ii


def test_ii_in_middle_of_twelve_lead_set() -> None:
    assert select_exact_lead_ii(["I", "II", "III"]) == 1


def test_ii_first_position() -> None:
    assert select_exact_lead_ii(["II", "I", "III"]) == 0


def test_no_exact_ii_returns_none() -> None:
    assert select_exact_lead_ii(["I", "III", "V1"]) is None


def test_duplicate_ii_raises_ambiguous() -> None:
    with pytest.raises(ValueError, match="AMBIGUOUS"):
        select_exact_lead_ii(["II", "II"])


def test_exact_case_sensitive_match_only() -> None:
    assert select_exact_lead_ii(["ii", "I"]) is None
    assert select_exact_lead_ii([" II ", "I"]) is None
    assert select_exact_lead_ii(["MLII"]) is None


def test_empty_signal_list_returns_none() -> None:
    assert select_exact_lead_ii([]) is None


def test_no_index_based_fallback_in_source() -> None:
    import inspect

    source = inspect.getsource(select_exact_lead_ii)
    forbidden = ("sig_name[0]", "sig_name[1]", "channel = 1", "index = 1")
    for pattern in forbidden:
        assert pattern not in source


def test_inspect_record_reports_malformed_header_without_raising(tmp_path, monkeypatch) -> None:
    def _broken_read_header(record_id, raw_root):
        raise OSError("no such record")

    monkeypatch.setattr("datasets.incart.read_header", _broken_read_header)
    selection = inspect_record("I999", tmp_path)
    assert selection.eligible is False
    assert selection.exclusion_reason == ExclusionReason.MALFORMED_HEADER


def test_inspect_record_ambiguous_ii_is_excluded_not_arbitrary(tmp_path, monkeypatch) -> None:
    from datasets.incart import HeaderInfo

    def _fake_header(record_id, raw_root):
        return HeaderInfo(
            record_id=record_id,
            fs=257.0,
            sig_len=1000,
            n_sig=2,
            sig_name=("II", "II"),
            comments=(),
            duration_seconds=1000 / 257.0,
        )

    monkeypatch.setattr("datasets.incart.read_header", _fake_header)
    selection = inspect_record("I998", tmp_path)
    assert selection.eligible is False
    assert selection.exclusion_reason == ExclusionReason.AMBIGUOUS_MULTIPLE_II


def test_inspect_record_eligible_with_exact_ii(tmp_path, monkeypatch) -> None:
    from datasets.incart import HeaderInfo

    def _fake_header(record_id, raw_root):
        return HeaderInfo(
            record_id=record_id,
            fs=257.0,
            sig_len=1000,
            n_sig=12,
            sig_name=("I", "II", "III"),
            comments=("patient 5",),
            duration_seconds=1000 / 257.0,
        )

    monkeypatch.setattr("datasets.incart.read_header", _fake_header)
    selection = inspect_record("I997", tmp_path)
    assert selection.eligible is True
    assert selection.ii_channel_index == 1
    assert selection.exclusion_reason == ExclusionReason.NONE
