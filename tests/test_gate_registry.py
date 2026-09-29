from pathlib import Path

from nhm.coverage import GATE_STATUSES, read_csv

ROOT = Path(__file__).resolve().parents[1]


def test_gate_registry_is_exact_and_only_approved_gates_are_passed() -> None:
    """G1 (hardware/data contract) stays NOT_STARTED (BLOCKED_HARDWARE, see
    docs/HARDWARE_DEFERRED_EXECUTION_PLAN.md) while G2/G3 (public-dataset acquisition and
    validation, T006+T007), G4 (label freeze, T008), and G5 (split/leakage audit, T009+T010)
    legitimately close ahead of it -- gates do not close in strict numeric order once a
    hardware-independent track exists."""
    rows = read_csv(ROOT / "manifests/gate_registry_v1.csv")
    assert [row["gate_id"] for row in rows] == [f"G{number}" for number in range(23)]
    assert len({row["gate_id"] for row in rows}) == 23
    assert {row["status"] for row in rows} <= GATE_STATUSES
    passed = {row["gate_id"] for row in rows if row["status"] == "PASS"}
    assert passed == {"G0", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G10"}
    not_started = {row["gate_id"] for row in rows if row["gate_id"] not in passed}
    assert all(
        row["status"] == "NOT_STARTED" for row in rows if row["gate_id"] in not_started
    )
    assert all(row["pass_criteria"] and row["fail_criteria"] for row in rows)
