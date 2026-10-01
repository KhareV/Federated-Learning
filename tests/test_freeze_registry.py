from pathlib import Path

from nhm.coverage import read_csv

ROOT = Path(__file__).resolve().parents[1]


def test_freeze_registry_covers_required_decisions_without_premature_freezes() -> None:
    rows = read_csv(ROOT / "manifests/freeze_registry_v1.csv")
    names = " ".join(row["artifact_or_decision"].casefold() for row in rows)
    for expected in (
        "source authority",
        "hardware/data contract",
        "dataset versions",
        "label mapping",
        "patient split",
        "preprocessing",
        "model_v1",
        "calibration",
        "privacy",
        "deployment",
        "release",
    ):
        assert expected in names
    assert len(rows) == 15
    assert rows[0]["freeze_id"] == "F01"
    frozen = {row["freeze_id"] for row in rows if row["current_status"] == "FROZEN"}
    assert frozen == {
        "F01",
        "F04",
        "F05",
        "F06",
        "F07",
        "F08",
        "F09",
        "F10",
        "F11",
        "F12",
        "F13",
    }
    assert all(
        row["current_status"] == "NOT_FROZEN" for row in rows if row["freeze_id"] not in frozen
    )
