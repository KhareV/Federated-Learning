from __future__ import annotations

import csv
from pathlib import Path

from federated.non_iid_manifest import constrained_quantity_allocation

ROOT = Path(__file__).resolve().parents[1]


def read(name: str) -> list[dict[str, str]]:
    with (ROOT / "manifests/clients" / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_all_manifests_close_over_whole_train_patients() -> None:
    for name in (
        "NONIID_LABEL_V1.csv",
        "NONIID_QUANTITY_V1.csv",
        "NONIID_FEATURE_V1.csv",
        "NONIID_COMBINED_V1.csv",
    ):
        rows = read(name)
        groups = [row["participant_group_id"] for row in rows]
        assert len(groups) == len(set(groups)) == 27
        assert {row["partition"] for row in rows} == {"TRAIN"}
        assert sum(int(row["eligible_window_count"]) for row in rows) == 9660
        assert sum(int(row["positive_window_count"]) for row in rows) == 3557
        assert sum(int(row["negative_window_count"]) for row in rows) == 6103


def test_label_and_quantity_capacities() -> None:
    label = read("NONIID_LABEL_V1.csv")
    quantity = read("NONIID_QUANTITY_V1.csv")
    assert [sum(row["site_id"] == f"SITE_{i:02d}" for row in label) for i in range(8)] == [
        4,
        4,
        4,
        3,
        3,
        3,
        3,
        3,
    ]
    assert constrained_quantity_allocation() == (2, 2, 2, 3, 3, 4, 5, 6)
    assert [sum(row["site_id"] == f"SITE_{i:02d}" for row in quantity) for i in range(8)] == [
        2,
        2,
        2,
        3,
        3,
        4,
        5,
        6,
    ]


def test_feature_mapping_equals_iid() -> None:
    iid = read("CLIENTS_IID_V1.csv")
    feature = read("NONIID_FEATURE_V1.csv")

    def mapping(rows: list[dict[str, str]]) -> list[tuple[str, str]]:
        return sorted((row["site_id"], row["participant_group_id"]) for row in rows)

    assert mapping(feature) == mapping(iid)
