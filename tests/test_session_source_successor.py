"""NHM_SESSION_SOURCE_MIXED_TOPOLOGY_001: additive successor of NHM_HARDWARE_V2_OBSERVATORY_001 (History session as a signal source, one recorded client + seven peers, federation replay fix)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import successor_chain
from scripts.freeze_observatory_v1 import frontend_files

ROOT = Path(__file__).resolve().parents[1]
LOCK_ID = "NHM_SESSION_SOURCE_MIXED_TOPOLOGY_001"
PREDECESSOR = "NHM_HARDWARE_V2_OBSERVATORY_001"


def _link() -> successor_chain.Link:
    return next(link for link in successor_chain.LINKS if link.lock_id == LOCK_ID)


def test_successor_chains_from_the_accepted_unified_lock_and_binds_the_current_tree() -> None:
    link = _link()
    assert Path(link.predecessor_path).name.startswith(PREDECESSOR)
    lock = successor_chain.validate_link(link, ROOT)
    assert lock["status"] == "PASS"
    assert lock["predecessor_commit"] == "bf335bbd63d29f556f9dde376c12baf6cb97f768"
    # Once a later additive successor exists, the tree matches the chain tip, not this (historical) link.
    expected = successor_chain.tip_frontend_map(ROOT) or lock["frontend_files"]
    assert set(expected) == set(frontend_files())
    assert all(successor_chain.sha256((ROOT / p).read_bytes()) == d for p, d in expected.items())
    # hardware functionality WAS extended here (and says so); physical devices and the deployed service remain unverified
    assert lock["hardware_functionality_changed"] is True and lock["hardware_experiments_run"] is True
    assert lock["physical_esp32_verified"] is False and lock["real_render_verified"] is False and lock["evidence_level"] == "VERIFIED_LOCAL_RENDER_REPLICA"
    for path in ("studio/hardware_v2.py", "studio/session_source.py"):
        assert successor_chain.sha256((ROOT / path).read_bytes()) == lock["bound_files"][path]


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
