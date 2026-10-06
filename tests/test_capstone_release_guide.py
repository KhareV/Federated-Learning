# ruff: noqa: E501
"""CAP-011: release guide claims, commands and scope statements."""

from __future__ import annotations

import json
from pathlib import Path

from scripts import capstone_release_lib as lib

ROOT = Path(__file__).resolve().parents[1]
TEXT = (ROOT / "docs/capstone/CAPSTONE_RELEASE_GUIDE_V1.md").read_text()
CLEAN = json.loads((ROOT / "configs/capstone/cap_011_clean_clone_protocol_v1.json").read_text())
POLICY = json.loads((ROOT / "configs/capstone/cap_011_release_policy_v1.json").read_text())
NON_COMMANDS = {"cd nhm-capstone", "export PYTHONPATH=src:.", "export CAP010_OUT=<EMPTY_DIRECTORY_OUTSIDE_REPO>"}


def test_guide_audit_passes_and_has_required_statements() -> None:
    audit = lib.audit_release_text(TEXT)
    assert audit["ok"], audit
    assert POLICY["release_claim"] in TEXT


def test_guide_commands_equal_the_protocol_commands() -> None:
    commands = set(lib.guide_commands(TEXT))
    displays = {c["display"] for c in CLEAN["commands"]}
    assert displays <= commands, sorted(displays - commands)          # every tested command is documented verbatim
    assert commands - displays <= NON_COMMANDS, sorted(commands - displays - NON_COMMANDS)   # nothing untested is documented
    assert any("run_capstone_faculty_demo --acknowledge-demo-auth" in c and "--build" in c and "--prewarm-federation" in c for c in commands)


def test_guide_contains_every_limitation_and_no_raw_data_step() -> None:
    for item in POLICY["limitations"]:
        assert item["text"] in TEXT, item
    assert "Initial dependency installation may require Internet access" in TEXT and "requires only loopback networking" in TEXT
    assert "does not claim full raw-data retraining/evaluation from a clean clone" in TEXT
    lowered = TEXT.lower()
    for dataset in ("mit-bih", "incart", "nstdb", "bidmc"):
        for line in lowered.splitlines():
            if dataset in line and "second-look" not in line:
                assert "not" in line or "belong" in line, line       # datasets are only mentioned as NOT required
    assert "wfdb" not in lowered and "acquire-mitdb" not in lowered and "make acquire" not in lowered
