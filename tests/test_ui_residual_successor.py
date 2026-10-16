"""NHM_UI_RESIDUAL_REPAIR_001: additive successor of NHM_HARDWARE_LIVE_UNIFIED_001 (non-hardware residual UI repair)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import successor_chain
from scripts.freeze_observatory_v1 import frontend_files

ROOT = Path(__file__).resolve().parents[1]
LOCK_ID = "NHM_UI_RESIDUAL_REPAIR_001"
PREDECESSOR = "NHM_HARDWARE_LIVE_UNIFIED_001"


def _link() -> successor_chain.Link:
    return next(link for link in successor_chain.LINKS if link.lock_id == LOCK_ID)


def test_successor_chains_from_the_accepted_unified_lock_and_binds_the_current_tree() -> None:
    link = _link()
    assert Path(link.predecessor_path).name.startswith(PREDECESSOR)
    lock = successor_chain.validate_link(link, ROOT)
    assert lock["status"] == "PASS"
    assert lock["predecessor_commit"] == "21a5fad1bea34fc197a797f55dbda7ca39fded3f"
    assert set(lock["frontend_files"]) == set(frontend_files())
    assert all(successor_chain.sha256((ROOT / p).read_bytes()) == d for p, d in lock["frontend_files"].items())
    # hardware is explicitly out of this lock's scope
    assert lock["hardware_functionality_changed"] is False and lock["hardware_experiments_run"] is False
    assert lock["physical_e2e_verified"] is False


def test_the_predecessor_lock_bytes_are_the_committed_ones() -> None:
    link = _link()
    lock = json.loads((ROOT / link.path).read_text())
    import hashlib

    assert lock["predecessor_lock_sha256"] == hashlib.sha256((ROOT / link.predecessor_path).read_bytes()).hexdigest()


@pytest.mark.parametrize("field", ["historical_locks_edited", "released_model_changed", "automatically_pushed", "frozen_scientific_evidence_edited"])
def test_scope_forgery_is_rejected(field: str) -> None:
    link = _link()
    forged = json.loads((ROOT / link.path).read_text())
    forged[field] = True
    with pytest.raises(RuntimeError, match=f"{LOCK_ID}_SUCCESSOR_CHAIN_BROKEN:SCOPE_DRIFT:{field}"):
        successor_chain.validate_link(link, ROOT, lock_override=forged)
