"""Read-only checks of the additive NHM_UNIFIED_LIVE_FEDERATION_STUDIO_001 lock and its tamper controls."""

from __future__ import annotations

import json

import pytest

from scripts.verify_unified_studio_001 import FLAGS_FALSE, LOCK_PATH, verify_lock

pytestmark = pytest.mark.skipif(not LOCK_PATH.exists(), reason="the Studio lock is created at the end of the work (after every gate)")
REJECT = (ValueError, RuntimeError)


def test_studio_successor_lock_verifies_including_the_whole_older_chain():
    result = verify_lock()
    assert result["status"] == "PASS" and len(result["older_chain"]) == 14 and set(result["older_chain"].values()) == {"PASS"}
    assert set(result["live_runs"]) == {"3", "10"}


def _tampered(tmp_path, mutate):
    lock = json.loads(LOCK_PATH.read_text())
    mutate(lock)
    path = tmp_path / "tampered.lock.json"
    path.write_text(json.dumps(lock))
    return path


@pytest.mark.parametrize("name,mutate", [
    ("predecessor digest", lambda l: l.update(predecessor_lock_sha256="0" * 64)),
    ("predecessor commit", lambda l: l.update(predecessor_commit="0" * 40)),
    ("lock id", lambda l: l.update(lock_id="NHM_UNIFIED_LIVE_FEDERATION_STUDIO_FORGED")),
    ("status", lambda l: l.update(status="FAIL")),
    ("repin set", lambda l: l["repins_predecessor_files"].pop()),
    ("frontend digest", lambda l: l["frontend_files"].update({sorted(l["frontend_files"])[0]: "0" * 64})),
    ("frontend file removed from binding", lambda l: l["frontend_files"].pop(sorted(l["frontend_files"])[0])),
    ("bound file digest", lambda l: l["bound_files"].update({sorted(l["bound_files"])[0]: "0" * 64})),
    ("live run state digest", lambda l: l["live_runs"]["10"]["state_digests"].update({"10": "0" * 64})),
    ("live run evidence digest", lambda l: l["live_runs"]["3"].update(evidence_sha256="0" * 64)),
    ("clerk claim", lambda l: l.update(connected_clerk_two_user_e2e="PASS")),
    ("unverified tests", lambda l: l["test_results"].update(passed=False)),
    ("unverified browser", lambda l: l["browser_result"].update(passed=False)),
])
def test_studio_lock_rejects_tampering(tmp_path, name, mutate):
    with pytest.raises(REJECT):
        verify_lock(_tampered(tmp_path, mutate), with_older_chain=False)


@pytest.mark.parametrize("flag", FLAGS_FALSE)
def test_studio_lock_rejects_every_scope_claim(tmp_path, flag):
    with pytest.raises(REJECT):
        verify_lock(_tampered(tmp_path, lambda l: l.update({flag: True})), with_older_chain=False)


def test_a_tampered_copy_does_not_inherit_the_successor_repins(tmp_path):
    from scripts.studio_successor_compat import accepted_successor
    from scripts.verify_fl10_001 import LOCK_PATH as FL10_LOCK

    assert accepted_successor(FL10_LOCK)["lock_id"] == "NHM_UNIFIED_LIVE_FEDERATION_STUDIO_001"
    copy = tmp_path / "NHM_FL10_001.lock.json"
    copy.write_text(FL10_LOCK.read_text())
    assert accepted_successor(copy) is None            # only the canonical historical path is honoured; substituted paths keep their original tamper controls
