"""Unit tests for the pure functions in datasets/grouping.py, using small synthetic fixtures
-- never real MITDB data (that belongs to tests/test_mitdb_split_v1.py)."""

import pytest

from datasets.grouping import (
    PARTITIONS,
    PatientEventPresence,
    apportion_partition_capacities,
    apportion_stratum_capacities,
    assign_partitions,
    build_mitdb_patient_groups,
    compute_patient_event_presence,
    participant_group_id_for_record,
    stable_group_order,
    validate_split,
)


def test_participant_group_id_groups_201_and_202() -> None:
    assert participant_group_id_for_record("201") == "MITDB_P201_202"
    assert participant_group_id_for_record("202") == "MITDB_P201_202"
    assert participant_group_id_for_record("100") == "MITDB_P100"


def test_build_mitdb_patient_groups_retains_excluded_records() -> None:
    rows = build_mitdb_patient_groups(
        all_record_ids=["100", "102", "201", "202"],
        eligible_record_ids=["100", "201", "202"],
        exclusion_reasons={"102": "EXCLUDE_NO_EXACT_MLII"},
    )
    by_record = {row.record_id: row for row in rows}
    assert by_record["100"].core_channel_eligible is True
    assert by_record["100"].participant_group_id == "MITDB_P100"
    assert by_record["100"].records_in_group == 1
    assert by_record["102"].core_channel_eligible is False
    assert by_record["102"].eligibility_reason == "EXCLUDE_NO_EXACT_MLII"
    assert by_record["201"].participant_group_id == "MITDB_P201_202"
    assert by_record["202"].participant_group_id == "MITDB_P201_202"
    assert by_record["201"].records_in_group == 2
    assert by_record["202"].records_in_group == 2


def test_compute_patient_event_presence_positive_requires_s_v_or_f() -> None:
    presence = compute_patient_event_presence(
        "MITDB_P100", {"100": [("N", 10, 1000), ("V", 20, 1000)]}
    )
    assert presence.has_svf_event is True
    assert presence.mapped_n == 1
    assert presence.mapped_v == 1


def test_compute_patient_event_presence_negative_when_only_n_q_unmapped() -> None:
    presence = compute_patient_event_presence(
        "MITDB_P100", {"100": [("N", 10, 1000), ("Q", 20, 1000), ("~", 30, 1000)]}
    )
    assert presence.has_svf_event is False
    assert presence.mapped_n == 1
    assert presence.mapped_q == 1
    assert presence.nonbeat == 1


def test_compute_patient_event_presence_ignores_pre_and_post_signal_annotations() -> None:
    """A V beat placed outside [0, sig_len) must not create a false positive -- structural
    enforcement of the in-signal invariant even though MITDB has no known anomaly (T007's
    INCART pre-signal finding is the reason this must be enforced, not assumed)."""
    presence = compute_patient_event_presence(
        "MITDB_P100",
        {"100": [("N", 10, 1000), ("V", -5, 1000), ("V", 1000, 1000), ("V", 1000, 999)]},
    )
    assert presence.has_svf_event is False
    assert presence.mapped_v == 0


def test_compute_patient_event_presence_is_logical_or_across_group_records() -> None:
    """201/202 must be evaluated as one unit: a positive in either record makes the whole
    group positive, decided before allocation, not corrected after."""
    presence = compute_patient_event_presence(
        "MITDB_P201_202",
        {
            "201": [("N", 10, 1000), ("N", 20, 1000)],
            "202": [("N", 10, 1000), ("S", 20, 1000)],
        },
    )
    assert presence.has_svf_event is True
    assert presence.mapped_n == 3
    assert presence.mapped_s == 1


def test_apportion_partition_capacities_matches_hand_computed_45_patient_case() -> None:
    result = apportion_partition_capacities(45)
    assert result.quotas == {"TRAIN": 27, "VALIDATION": 7, "CALIBRATION": 4, "INTERNAL_TEST": 7}
    assert sum(result.quotas.values()) == 45
    assert result.method == "LARGEST_REMAINDER_HAMILTON"


def test_apportion_partition_capacities_tie_break_uses_fixed_partition_order() -> None:
    """4 patients, proportions .60/.15/.10/.15 -> raw 2.4/0.6/0.4/0.6: floors 2/0/0/0=2,
    2 slots remain; remainders .4/.6/.4/.6 tie VALIDATION/INTERNAL_TEST at .6 (both win) and
    TRAIN/CALIBRATION tie at .4 (neither needed) -- exercises the fixed tie-break order."""
    result = apportion_partition_capacities(4)
    assert result.quotas == {"TRAIN": 2, "VALIDATION": 1, "CALIBRATION": 0, "INTERNAL_TEST": 1}
    assert sum(result.quotas.values()) == 4


def test_apportion_stratum_capacities_matches_hand_computed_42_of_45_case() -> None:
    quotas = {"TRAIN": 27, "VALIDATION": 7, "CALIBRATION": 4, "INTERNAL_TEST": 7}
    positive = apportion_stratum_capacities(quotas, 42)
    assert positive == {"TRAIN": 25, "VALIDATION": 7, "CALIBRATION": 4, "INTERNAL_TEST": 6}
    assert sum(positive.values()) == 42
    for partition in PARTITIONS:
        assert 0 <= positive[partition] <= quotas[partition]


def test_apportion_stratum_capacities_zero_and_full_positive() -> None:
    quotas = {"TRAIN": 3, "VALIDATION": 1, "CALIBRATION": 1, "INTERNAL_TEST": 1}
    assert apportion_stratum_capacities(quotas, 0) == {
        "TRAIN": 0, "VALIDATION": 0, "CALIBRATION": 0, "INTERNAL_TEST": 0,
    }
    assert apportion_stratum_capacities(quotas, 6) == quotas


def test_apportion_stratum_capacities_rejects_out_of_range_total() -> None:
    quotas = {"TRAIN": 3, "VALIDATION": 1, "CALIBRATION": 1, "INTERNAL_TEST": 1}
    with pytest.raises(ValueError, match="out of range"):
        apportion_stratum_capacities(quotas, 7)


def test_stable_group_order_is_deterministic_across_calls() -> None:
    ids = ["MITDB_P100", "MITDB_P101", "MITDB_P103", "MITDB_P201_202"]
    first = stable_group_order("MITDB_SPLIT_V1", 20260927, "POSITIVE", ids)
    second = stable_group_order("MITDB_SPLIT_V1", 20260927, "POSITIVE", ids)
    assert first == second
    assert sorted(first) == sorted(ids)


def test_stable_group_order_changes_with_seed() -> None:
    ids = [f"MITDB_P{n}" for n in range(20)]
    first = stable_group_order("MITDB_SPLIT_V1", 1, "POSITIVE", ids)
    second = stable_group_order("MITDB_SPLIT_V1", 2, "POSITIVE", ids)
    assert first != second


def test_assign_partitions_respects_quotas_and_is_deterministic() -> None:
    positive_ids = [f"P{n}" for n in range(6)]
    negative_ids = [f"N{n}" for n in range(2)]
    positive_quotas = {"TRAIN": 4, "VALIDATION": 1, "CALIBRATION": 0, "INTERNAL_TEST": 1}
    negative_quotas = {"TRAIN": 1, "VALIDATION": 0, "CALIBRATION": 1, "INTERNAL_TEST": 0}
    args = (positive_ids, negative_ids, positive_quotas, negative_quotas)
    first = assign_partitions("SID", 1, *args)
    second = assign_partitions("SID", 1, *args)
    assert [(a.participant_group_id, a.partition) for a in first] == [
        (a.participant_group_id, a.partition) for a in second
    ]
    counts: dict[str, int] = {}
    for row in first:
        counts[row.partition] = counts.get(row.partition, 0) + 1
    assert counts == {"TRAIN": 5, "VALIDATION": 1, "CALIBRATION": 1, "INTERNAL_TEST": 1}


def test_validate_split_detects_overlap_and_unassigned() -> None:
    from datasets.grouping import PartitionAssignment

    assignments = [
        PartitionAssignment("A", "TRAIN", True),
        PartitionAssignment("A", "VALIDATION", True),
        PartitionAssignment("B", "TRAIN", False),
    ]
    result = validate_split(assignments, eligible_group_ids=["A", "B", "C"])
    assert result["status"] == "FAIL"
    assert result["pairwise_overlap_count"] == 1
    assert result["unassigned_count"] == 1


def test_validate_split_passes_for_clean_partition() -> None:
    from datasets.grouping import PartitionAssignment

    assignments = [
        PartitionAssignment("A", "TRAIN", True),
        PartitionAssignment("B", "VALIDATION", False),
    ]
    result = validate_split(assignments, eligible_group_ids=["A", "B"])
    assert result == {
        "status": "PASS",
        "errors": [],
        "unassigned_count": 0,
        "duplicate_assignment_count": 0,
        "pairwise_overlap_count": 0,
    }


def test_patient_event_presence_is_frozen_dataclass() -> None:
    presence = PatientEventPresence("A", True, 1, 1, 1, 1, 0, 0, 0)
    with pytest.raises(AttributeError):
        presence.has_svf_event = False  # type: ignore[misc]
