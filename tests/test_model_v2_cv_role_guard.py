"""V2-002 CV-role firewall tests (Section 4/26).

Proves: OPTIMISE/INNER_VALIDATION access succeeds during V2-002_TRAIN_SELECT; OUTER_TEST
access during TRAIN_SELECT fails; wrong-fold access fails; OUTER_TEST access during
V2-002_OUTER_EVAL fails until checkpoint_finalized=True; and the existing V2-001 partition
firewall (VALIDATION/CALIBRATION/INTERNAL_TEST/INCART/NSTDB/BIDMC) is unweakened.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nhm.model_v2_cv_role_guard import (
    CVRoleAccessViolation,
    check_cv_role_allowed,
    record_cv_role_access,
)
from nhm.model_v2_partition_guard import (
    PartitionAccessViolation,
    check_partition_allowed,
)


def test_optimise_access_allowed_during_train_select() -> None:
    check_cv_role_allowed(
        "OPTIMISE", "V2-002_TRAIN_SELECT", requested_outer_fold=0, experiment_outer_fold=0
    )


def test_inner_validation_access_allowed_during_train_select() -> None:
    check_cv_role_allowed(
        "INNER_VALIDATION",
        "V2-002_TRAIN_SELECT",
        requested_outer_fold=2,
        experiment_outer_fold=2,
    )


def test_outer_test_access_during_train_select_fails() -> None:
    with pytest.raises(CVRoleAccessViolation, match="CV_ROLE_FIREWALL_DENIED"):
        check_cv_role_allowed(
            "OUTER_TEST",
            "V2-002_TRAIN_SELECT",
            requested_outer_fold=0,
            experiment_outer_fold=0,
        )


def test_optimise_access_during_outer_eval_fails() -> None:
    with pytest.raises(CVRoleAccessViolation, match="CV_ROLE_FIREWALL_DENIED"):
        check_cv_role_allowed(
            "OPTIMISE",
            "V2-002_OUTER_EVAL",
            requested_outer_fold=0,
            experiment_outer_fold=0,
            checkpoint_finalized=True,
        )


def test_outer_test_access_before_checkpoint_finalized_fails() -> None:
    with pytest.raises(
        CVRoleAccessViolation, match="CV_ROLE_FIREWALL_OUTER_TEST_BEFORE_CHECKPOINT_FINALIZED"
    ):
        check_cv_role_allowed(
            "OUTER_TEST",
            "V2-002_OUTER_EVAL",
            requested_outer_fold=0,
            experiment_outer_fold=0,
            checkpoint_finalized=False,
        )


def test_outer_test_access_after_checkpoint_finalized_succeeds() -> None:
    check_cv_role_allowed(
        "OUTER_TEST",
        "V2-002_OUTER_EVAL",
        requested_outer_fold=3,
        experiment_outer_fold=3,
        checkpoint_finalized=True,
    )


def test_wrong_fold_outer_test_access_fails_even_with_checkpoint_finalized() -> None:
    with pytest.raises(CVRoleAccessViolation, match="CV_ROLE_FIREWALL_WRONG_FOLD"):
        check_cv_role_allowed(
            "OUTER_TEST",
            "V2-002_OUTER_EVAL",
            requested_outer_fold=1,
            experiment_outer_fold=2,
            checkpoint_finalized=True,
        )


def test_wrong_fold_optimise_access_fails() -> None:
    with pytest.raises(CVRoleAccessViolation, match="CV_ROLE_FIREWALL_WRONG_FOLD"):
        check_cv_role_allowed(
            "OPTIMISE",
            "V2-002_TRAIN_SELECT",
            requested_outer_fold=4,
            experiment_outer_fold=1,
        )


def test_unknown_role_rejected() -> None:
    with pytest.raises(CVRoleAccessViolation, match="UNKNOWN_CV_ROLE"):
        check_cv_role_allowed(
            "NOT_A_ROLE",
            "V2-002_TRAIN_SELECT",
            requested_outer_fold=0,
            experiment_outer_fold=0,
        )


def test_unknown_stage_rejected() -> None:
    with pytest.raises(CVRoleAccessViolation, match="UNKNOWN_CV_STAGE"):
        check_cv_role_allowed(
            "OPTIMISE",
            "NOT_A_STAGE",
            requested_outer_fold=0,
            experiment_outer_fold=0,
        )


def test_ledger_append_only(tmp_path: Path) -> None:
    for i in range(3):
        record_cv_role_access(
            tmp_path,
            task_id="V2-002",
            experiment_id=f"V2-002-F00-S2026092{7 + i}",
            outer_fold=0,
            seed=20260927 + i,
            role="OPTIMISE",
            stage_id="V2-002_TRAIN_SELECT",
            participant_group_ids=["MITDB_P101", "MITDB_P103"],
            example_id_count=720,
            access_purpose="training",
        )
    ledger = (tmp_path / "reports/model_v2/v2_002/cv_role_access_ledger.jsonl").read_text(
        encoding="utf-8"
    )
    rows = [json.loads(line) for line in ledger.splitlines()]
    assert len(rows) == 3
    assert rows[0]["role"] == "OPTIMISE"
    assert rows[0]["participant_group_ids"] == ["MITDB_P101", "MITDB_P103"]


def test_existing_partition_firewall_still_blocks_official_validation() -> None:
    with pytest.raises(PartitionAccessViolation, match="MODEL_V2_PARTITION_FIREWALL_DENIED"):
        check_partition_allowed("VALIDATION", "V2-002", {"TRAIN"})


def test_existing_partition_firewall_still_blocks_calibration() -> None:
    with pytest.raises(PartitionAccessViolation, match="MODEL_V2_PARTITION_FIREWALL_DENIED"):
        check_partition_allowed("CALIBRATION", "V2-002", {"TRAIN"})


def test_existing_partition_firewall_still_blocks_internal_test() -> None:
    with pytest.raises(PartitionAccessViolation, match="MODEL_V2_PARTITION_FIREWALL_DENIED"):
        check_partition_allowed("INTERNAL_TEST", "V2-002", {"TRAIN"})


@pytest.mark.parametrize("partition", ["INCART", "NSTDB", "BIDMC"])
def test_existing_partition_firewall_still_blocks_external_domains(partition: str) -> None:
    with pytest.raises(PartitionAccessViolation, match="MODEL_V2_PARTITION_FIREWALL_DENIED"):
        check_partition_allowed(partition, "V2-002", {"TRAIN"})


def test_existing_partition_firewall_still_allows_train() -> None:
    check_partition_allowed("TRAIN", "V2-002", {"TRAIN"})
