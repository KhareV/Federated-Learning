"""V2-001 control-plane governance tests (Section 13).

Proves: the V2 task/gate namespace is fully separate from and does not alter the canonical
T001-T036/G0-G22 registries; frozen V1 hashes (MODEL_V1.pt, CAL_V1.json) are unchanged; the
MODEL_V2_RESEARCH_PROTOCOL_V1 lock hash is reproducible from its own source files; and only
V2-001/V2G0 are PASS in this phase, everything later remains NOT_STARTED.
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_canonical_task_registry_untouched_by_v2_namespace() -> None:
    rows = _rows(ROOT / "manifests/task_registry_v1.csv")
    assert len(rows) == 36
    assert [row["task_id"] for row in rows] == [f"T{n:03d}" for n in range(1, 37)]
    assert all(not row["task_id"].startswith("V2") for row in rows)


def test_canonical_gate_registry_untouched_by_v2_namespace() -> None:
    rows = _rows(ROOT / "manifests/gate_registry_v1.csv")
    assert len(rows) == 23
    assert [row["gate_id"] for row in rows] == [f"G{n}" for n in range(23)]
    assert all(not row["gate_id"].startswith("V2") for row in rows)


def test_v2_task_registry_is_a_separate_namespace() -> None:
    rows = _rows(ROOT / "manifests/model_v2/task_registry_v1.csv")
    assert len(rows) == 20  # V2-001..V2-014, additive V2-FL-001..005 and V2-FL-EVAL-001
    assert all(row["task_id"].startswith("V2-") for row in rows)
    expected = ({f"V2-{n:03d}" for n in range(1, 15)}
                | {f"V2-FL-{n:03d}" for n in range(1, 6)} | {"V2-FL-EVAL-001"})
    assert {row["task_id"] for row in rows} == expected


def test_v2_gate_registry_is_a_separate_namespace() -> None:
    rows = _rows(ROOT / "manifests/model_v2/gate_registry_v1.csv")
    assert len(rows) == 18  # V2G0..V2G13 plus the additive federated gates V2FLG0..V2FLEG0
    assert all(row["gate_id"].startswith(("V2G", "V2FLG", "V2FLEG")) for row in rows)
    expected = {f"V2G{n}" for n in range(14)} | {"V2FLG0", "V2FLG1", "V2FLG2", "V2FLEG0"}
    assert {row["gate_id"] for row in rows} == expected


def test_only_v2_001_through_v2_010_and_v2g0_through_v2g9_pass_in_this_phase() -> None:
    task_rows = _rows(ROOT / "manifests/model_v2/task_registry_v1.csv")
    gate_rows = _rows(ROOT / "manifests/model_v2/gate_registry_v1.csv")

    passed_tasks = {row["task_id"] for row in task_rows if row["status"] == "PASS"}
    passed_gates = {row["gate_id"] for row in gate_rows if row["status"] == "PASS"}

    # V2-010..V2-013 and V2G9..V2G12 (gateway, then API runtime integration) have since passed;
    # this test still guards that no other task/gate has silently passed.
    expected_tasks = {
        "V2-001", "V2-002", "V2-003", "V2-004", "V2-006", "V2-007", "V2-008", "V2-009",
        "V2-010", "V2-011", "V2-012", "V2-013", "V2-FL-001", "V2-FL-002",
        "V2-FL-003",
    }
    expected_gates = {
        "V2G0", "V2G1", "V2G2", "V2G3", "V2G4", "V2G5", "V2G6", "V2G7", "V2G8", "V2G9",
        "V2G10", "V2G11", "V2G12", "V2FLG0", "V2FLG1", "V2FLG2",
    }
    assert passed_tasks == expected_tasks
    assert passed_gates == expected_gates

    # V2-005 is the one task whose frozen protocol predeclares a conditional
    # SKIPPED_BY_PROTOCOL terminal state (see manifests/model_v2/task_registry_v1.csv's own
    # V2-005 notes field: "otherwise SKIPPED_BY_PROTOCOL"). It is the only task allowed to be
    # anything other than NOT_STARTED/PASS at this point in the control-plane timeline; every
    # other not-yet-passed task/gate must still be exactly NOT_STARTED. This does not weaken
    # prerequisite checking generally -- see tests/test_v2_005_conditional_prerequisite.py for
    # the narrow, evidence-conditioned semantics that govern this exception.
    other_tasks = [row for row in task_rows if row["task_id"] not in expected_tasks]
    for row in other_tasks:
        if row["task_id"] == "V2-005":
            assert row["status"] in {"NOT_STARTED", "SKIPPED_BY_PROTOCOL"}
        else:
            assert row["status"] == "NOT_STARTED"

    assert all(
        row["status"] == "NOT_STARTED"
        for row in gate_rows
        if row["gate_id"] not in expected_gates
    )


def test_frozen_v1_model_hash_unchanged() -> None:
    assert (
        hash_file(ROOT / "checkpoints/MODEL_V1.pt")
        == "021352eb067932015b657f0570ac155f8ef00af2d43864e13a110d0252bc7bfe"
    )


def test_frozen_cal_v1_hash_unchanged() -> None:
    assert (
        hash_file(ROOT / "artifacts/CAL_V1.json")
        == "d225b20957913439fd532a4de4d23acf573a88d06366e71bf3b8a7673e63479b"
    )


def test_freeze_registry_rows_still_frozen() -> None:
    rows = _rows(ROOT / "manifests/freeze_registry_v1.csv")
    by_id = {row["freeze_id"]: row for row in rows}
    for freeze_id in ("F05", "F06", "F07", "F08", "F09", "F10", "F11", "F14"):
        assert by_id[freeze_id]["current_status"] == "FROZEN"


def test_research_protocol_lock_hash_reproducible() -> None:
    lock = json.loads(
        (ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V1.lock.json").read_text(
            encoding="utf-8"
        )
    )
    assert lock["lock_id"] == "MODEL_V2_RESEARCH_PROTOCOL_V1"
    assert lock["status"] == "FROZEN_RESEARCH_PROTOCOL"
    assert lock["protocol_yaml_sha256"] == hash_file(
        ROOT / "configs/model_v2/research_protocol_v1.yaml"
    )
    assert lock["protocol_md_sha256"] == hash_file(
        ROOT / "docs/MODEL_V2_RESEARCH_PROTOCOL_V1.md"
    )

    subprocess.run(
        [sys.executable, str(ROOT / "scripts/freeze_model_v2_research_protocol_v2001.py")],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    regenerated = json.loads(
        (ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V1.lock.json").read_text(
            encoding="utf-8"
        )
    )
    assert regenerated == lock


def test_no_canonical_freeze_registry_row_added_for_v2_protocol() -> None:
    rows = _rows(ROOT / "manifests/freeze_registry_v1.csv")
    assert all(row["version_id"] != "MODEL_V2_RESEARCH_PROTOCOL_V1" for row in rows)
    lock = json.loads(
        (ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V1.lock.json").read_text(
            encoding="utf-8"
        )
    )
    assert lock["no_new_canonical_freeze_registry_row"] is True
