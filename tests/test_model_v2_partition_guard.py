"""V2-001 partition-access firewall tests (Section 9/13).

Proves the MODEL_V2 partition guard fails closed: a forbidden partition raises
PartitionAccessViolation BEFORE any file is opened (even a nonexistent path raises the
firewall error, never a FileNotFoundError), while an allowed partition genuinely loads the
array and appends an access-ledger row."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nhm.model_v2_partition_guard import (
    PartitionAccessViolation,
    check_partition_allowed,
    load_model_v2_partition,
)

ROOT = Path(__file__).resolve().parents[1]
TRAIN_WAVEFORM_PATH = (
    ROOT
    / "data/processed/mitdb/1.0.0/PREPROC_V1/MITDB_SPLIT_V1/AAMI_SVF_WINDOW_V1/TRAIN/"
    "101_filtered_windows.npy"
)
STAGE_V2_001_ALLOWED = frozenset({"TRAIN"})


def test_train_waveform_access_succeeds(tmp_path: Path) -> None:
    array = load_model_v2_partition(
        "TRAIN",
        "V2-001",
        STAGE_V2_001_ALLOWED,
        source_path=TRAIN_WAVEFORM_PATH,
        root=tmp_path,
        access_type="waveform_read",
    )
    assert array.shape[0] > 0

    ledger = (tmp_path / "reports/model_v2/access_ledger.jsonl").read_text(encoding="utf-8")
    rows = [json.loads(line) for line in ledger.splitlines()]
    assert len(rows) == 1
    assert rows[0]["partition"] == "TRAIN"
    assert rows[0]["stage_id"] == "V2-001"
    assert rows[0]["access_type"] == "waveform_read"
    assert rows[0]["rows"] == array.shape[0]


@pytest.mark.parametrize(
    "partition",
    ["VALIDATION", "CALIBRATION", "INTERNAL_TEST", "INCART", "NSTDB", "BIDMC"],
)
def test_forbidden_partition_access_raises_before_opening_file(
    partition: str, tmp_path: Path
) -> None:
    nonexistent = tmp_path / "this_file_does_not_exist.npy"
    with pytest.raises(PartitionAccessViolation, match="MODEL_V2_PARTITION_FIREWALL_DENIED"):
        load_model_v2_partition(
            partition,
            "V2-001",
            STAGE_V2_001_ALLOWED,
            source_path=nonexistent,
            root=tmp_path,
        )
    assert not nonexistent.exists()
    ledger_path = tmp_path / "reports/model_v2/access_ledger.jsonl"
    assert not ledger_path.exists()


def test_unknown_partition_name_raises() -> None:
    with pytest.raises(PartitionAccessViolation, match="UNKNOWN_PARTITION"):
        check_partition_allowed("NOT_A_REAL_PARTITION", "V2-001", STAGE_V2_001_ALLOWED)


def test_allowed_partitions_must_themselves_be_known() -> None:
    with pytest.raises(PartitionAccessViolation, match="UNKNOWN_ALLOWED_PARTITION"):
        check_partition_allowed("TRAIN", "V2-001", frozenset({"NOT_A_REAL_PARTITION"}))


def test_check_partition_allowed_passes_silently_for_train() -> None:
    check_partition_allowed("TRAIN", "V2-001", STAGE_V2_001_ALLOWED)


def test_ledger_is_append_only_across_multiple_accesses(tmp_path: Path) -> None:
    for _ in range(3):
        load_model_v2_partition(
            "TRAIN",
            "V2-001",
            STAGE_V2_001_ALLOWED,
            source_path=TRAIN_WAVEFORM_PATH,
            root=tmp_path,
        )
    ledger = (tmp_path / "reports/model_v2/access_ledger.jsonl").read_text(encoding="utf-8")
    rows = [json.loads(line) for line in ledger.splitlines()]
    assert len(rows) == 3
