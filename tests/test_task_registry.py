import json
import os
import subprocess
import sys
from pathlib import Path

from nhm.coverage import TASK_STATUSES, read_csv, split_refs
from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]


def test_task_registry_is_complete_and_future_work_is_not_started() -> None:
    rows = read_csv(ROOT / "manifests/task_registry_v1.csv")
    expected = [f"T{number:03d}" for number in range(1, 37)]
    assert [row["task_id"] for row in rows] == expected
    assert len({row["task_id"] for row in rows}) == 36
    assert {row["status"] for row in rows} <= TASK_STATUSES
    assert rows[0]["status"] == "PASS"
    assert rows[1]["status"] == "PASS"
    assert rows[2]["status"] == "PASS"
    assert rows[3]["status"] == "BLOCKED"
    assert rows[4]["status"] == "PASS"
    assert rows[5]["status"] == "PASS"
    assert rows[6]["status"] == "PASS"
    assert rows[7]["status"] == "PASS"
    assert rows[8]["status"] == "PASS"
    assert rows[9]["status"] == "PASS"
    assert rows[10]["status"] == "PASS"
    assert rows[11]["status"] == "PASS"
    assert rows[12]["status"] == "PASS"
    assert rows[13]["status"] == "PASS"
    assert rows[14]["status"] == "PASS"
    assert rows[15]["status"] == "PASS"
    assert rows[16]["status"] == "PASS"
    assert rows[17]["status"] == "PASS"
    assert rows[18]["status"] == "PASS"
    assert rows[19]["status"] == "PASS"
    assert rows[20]["status"] == "PASS"
    assert rows[21]["status"] == "PASS"
    assert rows[22]["status"] == "PASS"
    assert rows[23]["status"] == "PASS"
    assert rows[24]["status"] == "PASS"
    assert rows[25]["status"] == "PASS"
    assert rows[26]["status"] == "PASS"
    assert rows[27]["status"] == "PASS"
    assert rows[28]["status"] == "PASS"
    assert rows[29]["status"] == "NOT_STARTED"
    assert rows[30]["status"] == "PASS"
    assert rows[31]["status"] == "PASS"
    assert rows[32]["status"] == "PASS"
    assert rows[33]["status"] == "PASS"
    assert rows[34]["status"] == "PASS"
    assert all(row["status"] == "NOT_STARTED" for row in rows[35:])


def test_blocked_hardware_task_does_not_prevent_later_task_pass() -> None:
    """T004 is BLOCKED_HARDWARE; T005 (a hardware-independent task numerically after it)
    must still be able to reach PASS. This is the guard required by the T005 execution
    instructions Section 37: the future-task check rejects tasks *above* the latest
    approved task, not merely tasks *after* any earlier non-PASS task."""
    rows = {row["task_id"]: row for row in read_csv(ROOT / "manifests/task_registry_v1.csv")}
    assert rows["T004"]["status"] == "BLOCKED"
    assert rows["T005"]["status"] == "PASS"


def test_task_prerequisites_reference_known_tasks_or_gates() -> None:
    rows = read_csv(ROOT / "manifests/task_registry_v1.csv")
    allowed = {row["task_id"] for row in rows} | {f"G{number}" for number in range(23)}
    assert all(
        reference in allowed for row in rows for reference in split_refs(row["prerequisites"])
    )


def test_all_task_meanings_match_authoritative_execution_plan_snapshot() -> None:
    rows = read_csv(ROOT / "manifests/task_registry_v1.csv")
    snapshot = json.loads((ROOT / "manifests/task_packets_v1.json").read_text())
    assert snapshot["packet_count"] == 36
    assert snapshot["source_document"] == "NHM_Solo_Implementation_Execution_Plan_v1.0.docx"
    assert snapshot["source_role"] == "implementation_sequencing_authority"
    assert snapshot["source_sha256"] == hash_file(ROOT / snapshot["source_document"])
    source = {row["task_id"]: row for row in snapshot["packets"]}
    for row in rows:
        packet = source[row["task_id"]]
        assert row["task_name"] == packet["task_name"]
        assert row["phase_family"] == packet["phase"]
        assert row["source_prerequisites"] == packet["prerequisites"]
        assert row["source_gate_impact"] == packet["gate_freeze_impact"]
        assert row["source_document"] == snapshot["source_document"]
        assert row["source_sha256"] == snapshot["source_sha256"]
        assert "derived" not in " ".join(row.values()).casefold()


def test_anchor_task_names_are_canonical() -> None:
    tasks = {
        row["task_id"]: row["task_name"]
        for row in read_csv(ROOT / "manifests/task_registry_v1.csv")
    }
    expected = {
        "T004": "Bench hardware verification and firmware packet contract",
        "T005": "Fixture vertical slice 0",
        "T006": "MIT-BIH exact-version acquisition/manifest/MLII selection",
        "T007": "INCART/NSTDB/BIDMC acquisition and role-specific loaders",
        "T030": "Wearable ingest and domain-validation sessions",
        "T031": "Integrated Gradients and error analysis",
        "T032": "Typed API and versioned runtime contract",
        "T033": "Dashboard and state mapping",
        "T034": "Replay/live end-to-end integration",
    }
    assert {task_id: tasks[task_id] for task_id in expected} == expected


def test_checked_in_packet_snapshot_reextracts_from_authoritative_docx(tmp_path: Path) -> None:
    output = tmp_path / "task_packets.json"
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "src")
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/extract_execution_plan_tasks.py"),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    checked_in = json.loads((ROOT / "manifests/task_packets_v1.json").read_text())
    assert json.loads(output.read_text()) == checked_in
