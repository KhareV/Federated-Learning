from pathlib import Path

from nhm.coverage import GATE_STATUSES, read_csv

ROOT = Path(__file__).resolve().parents[1]


def test_gate_registry_is_exact_and_only_g0_is_passed() -> None:
    rows = read_csv(ROOT / "manifests/gate_registry_v1.csv")
    assert [row["gate_id"] for row in rows] == [f"G{number}" for number in range(23)]
    assert len({row["gate_id"] for row in rows}) == 23
    assert {row["status"] for row in rows} <= GATE_STATUSES
    assert rows[0]["status"] == "PASS"
    assert all(row["status"] == "NOT_STARTED" for row in rows[1:])
    assert all(row["pass_criteria"] and row["fail_criteria"] for row in rows)
