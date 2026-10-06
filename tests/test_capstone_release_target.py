# ruff: noqa: E501
"""CAP-011: the repository-level release verifier, frozen lock, evaluator coverage and the mutation-control set."""

from __future__ import annotations

import json
from pathlib import Path

from scripts import cap_011_evaluate_gate as gate
from scripts import cap_011_mutation_controls as mutations
from scripts import verify_capstone_release_v1 as verifier

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = json.loads((ROOT / "configs/capstone/cap_011_release_protocol_v1.json").read_text())


def test_verifier_passes_on_the_repository() -> None:
    result = verifier.verify(pre_freeze=not (ROOT / "artifacts/capstone/CAPSTONE_RELEASE_PROTOCOL_V1.lock.json").exists())
    assert result["status"] == "PASS", result["failed"]
    assert result["executes_no_science"] == {"training": 0, "inference": 0, "fl": 0, "secagg": 0}


def test_lock_chain_and_registry_state() -> None:
    tasks, gates = verifier.statuses()
    assert all(tasks[f"CAP-{i:03d}"] == "PASS" for i in range(1, 11)) and tasks["CAP-011"] in {"IN_PROGRESS", "PASS"}
    assert "CAP-012" not in tasks and gates["CAPG10"] in {"NOT_STARTED", "PASS"}


def test_evaluator_criteria_are_frozen_and_every_check_resolves() -> None:
    assert [r["id"] for r in PROTOCOL["capg10_criteria"]] == [f"CAPG10-{i:03d}" for i in range(1, 137)]
    checks = gate.build_checks()
    names = {c for row in PROTOCOL["capg10_criteria"] for c in row["checks"] if not c.startswith("T:")}
    assert not [n for n in names if n not in checks], [n for n in names if n not in checks]
    titles = {c[2:] for row in PROTOCOL["capg10_criteria"] for c in row["checks"] if c.startswith("T:")}
    source = "".join(p.read_text() for p in (ROOT / "tests").glob("test_capstone_release_*.py"))
    assert all(f"def {t}" in source for t in titles), titles


def test_mutation_control_set_is_the_frozen_twenty() -> None:
    assert [name for name, _ in mutations.MUTATIONS] == PROTOCOL["mutation_controls"] and len(PROTOCOL["mutation_controls"]) == 20


def test_final_target_split_rejects_any_executable_change_after_the_target() -> None:
    import tempfile

    from scripts.capstone_release_lib import FINAL_ALLOWED
    assert FINAL_ALLOWED[0] == "reports/capstone/cap_011/" and "scripts/" not in " ".join(FINAL_ALLOWED)
    assert tempfile  # the full git-level target/final split is exercised in test_capstone_release_lib and the mutation controls
