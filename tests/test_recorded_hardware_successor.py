from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import successor_chain
from scripts.freeze_observatory_v1 import frontend_files


ROOT = Path(__file__).resolve().parents[1]
LOCK_ID = "NHM_RECORDED_HARDWARE_FL_001"


def _link() -> successor_chain.Link:
    return next(link for link in successor_chain.LINKS if link.lock_id == LOCK_ID)


def test_recorded_hardware_successor_is_exact_and_complete() -> None:
    link = _link()
    lock = successor_chain.validate_link(link, ROOT)
    expected = lock["frontend_files"]
    actual = set(frontend_files())
    assert set(expected) == actual
    assert all(successor_chain.sha256((ROOT / path).read_bytes()) == digest for path, digest in expected.items())
    assert lock["physical_e2e_verified"] is False
    assert lock["atlas_scenarios_verified"] is True
    assert lock["clerk_two_user_browser_verified"] is True


@pytest.mark.parametrize("field", ["historical_locks_edited", "released_model_changed", "automatically_pushed"])
def test_recorded_hardware_successor_rejects_scope_forgery(field: str) -> None:
    link = _link()
    forged = json.loads((ROOT / link.path).read_text())
    forged[field] = True
    with pytest.raises(RuntimeError, match=f"{LOCK_ID}_SUCCESSOR_CHAIN_BROKEN:SCOPE_DRIFT:{field}"):
        successor_chain.validate_link(link, ROOT, lock_override=forged)

