from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_committed_real_reproducibility_evidence() -> None:
    report = json.loads((ROOT / "reports/t014/reproducibility.json").read_text())
    assert report["overall_status"] == "PASS"
    assert all(report["checks"].values())


def test_real_feature_population_is_one_to_one_and_permitted_only() -> None:
    import csv

    with (ROOT / "manifests/features/MITDB_BASELINE_FEATURES_V1.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 9660 + 2880
    assert len({row["example_id"] for row in rows}) == len(rows)
    assert {row["partition"] for row in rows} == {"TRAIN", "VALIDATION"}
    assert len({row["participant_group_id"] for row in rows if row["partition"] == "TRAIN"}) == 27
    assert (
        len(
            {
                row["participant_group_id"]
                for row in rows
                if row["partition"] == "VALIDATION"
            }
        )
        == 7
    )
