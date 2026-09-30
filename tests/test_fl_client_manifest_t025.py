from __future__ import annotations

import csv
from pathlib import Path

from federated.client_manifest import (
    SITE_IDS,
    PatientSummary,
    balanced_capacities,
    build_assignment,
    manifest_rows,
)

ROOT = Path(__file__).resolve().parents[1]


def _patients() -> list[PatientSummary]:
    return [
        PatientSummary(f"P{index:02d}", (str(index),), 100 + index, 10 + index, 90)
        for index in range(27)
    ]


def test_whole_patient_assignment_is_complete_balanced_and_deterministic() -> None:
    first, first_audit = build_assignment(_patients())
    second, second_audit = build_assignment(_patients())
    assert manifest_rows(first) == manifest_rows(second)
    assert first_audit == second_audit
    assigned = [patient.participant_group_id for site in SITE_IDS for patient in first[site]]
    assert len(assigned) == len(set(assigned)) == 27
    assert sorted(len(first[site]) for site in SITE_IDS) == [3, 3, 3, 3, 3, 4, 4, 4]
    assert balanced_capacities(27) == {
        "SITE_00": 4,
        "SITE_01": 4,
        "SITE_02": 4,
        "SITE_03": 3,
        "SITE_04": 3,
        "SITE_05": 3,
        "SITE_06": 3,
        "SITE_07": 3,
    }
    assert all(row["partition"] == "TRAIN" for row in manifest_rows(first))


def test_pairwise_swaps_never_worsen_objective() -> None:
    _, audit = build_assignment(_patients())
    assert audit["final_objective"] <= audit["initial_objective"]


def test_real_manifest_has_all_and_only_whole_train_patients() -> None:
    with (ROOT / "manifests/clients/CLIENTS_IID_V1.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    with (ROOT / "manifests/splits/MITDB_SPLIT_V1.csv").open(newline="") as handle:
        split = list(csv.DictReader(handle))
    train = {row["participant_group_id"] for row in split if row["partition"] == "TRAIN"}
    assigned = [row["participant_group_id"] for row in rows]
    assert len(rows) == len(train) == len(set(assigned)) == 27
    assert set(assigned) == train
    assert {row["site_id"] for row in rows} == set(SITE_IDS)
    assert all(row["partition"] == "TRAIN" for row in rows)
    assert sum(int(row["eligible_window_count"]) for row in rows) == 9660
    assert sum(int(row["positive_window_count"]) for row in rows) == 3557
    assert sum(int(row["negative_window_count"]) for row in rows) == 6103
