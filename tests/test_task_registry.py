from pathlib import Path

from nhm.coverage import TASK_STATUSES, read_csv, split_refs

ROOT = Path(__file__).resolve().parents[1]


def test_task_registry_is_complete_and_future_work_is_not_started() -> None:
    rows = read_csv(ROOT / "manifests/task_registry_v1.csv")
    expected = [f"T{number:03d}" for number in range(1, 37)]
    assert [row["task_id"] for row in rows] == expected
    assert len({row["task_id"] for row in rows}) == 36
    assert {row["status"] for row in rows} <= TASK_STATUSES
    assert rows[0]["status"] == "PASS"
    assert rows[1]["status"] == "PASS"
    assert all(row["status"] == "NOT_STARTED" for row in rows[2:])


def test_task_prerequisites_reference_known_tasks_or_gates() -> None:
    rows = read_csv(ROOT / "manifests/task_registry_v1.csv")
    allowed = {row["task_id"] for row in rows} | {f"G{number}" for number in range(23)}
    assert all(
        reference in allowed
        for row in rows
        for reference in split_refs(row["prerequisites"])
    )
