"""Read-only checks of the additive FL10 lock and its tamper controls."""

import json

import pytest

from scripts.verify_fl10_001 import LOCK_PATH, verify_lock


def test_fl10_successor_lock_verifies():
    assert verify_lock()["status"] == "PASS"


@pytest.mark.parametrize("change", ["predecessor", "method", "artifact", "frontend", "scope"])
def test_fl10_successor_rejects_tampering(tmp_path, change):
    lock = json.loads(LOCK_PATH.read_text())
    if change == "predecessor":
        lock["predecessor_lock_sha256"] = "0" * 64
    elif change == "method":
        lock["method_hashes"]["configs/fl10/protocol_v1.json"] = "0" * 64
    elif change == "artifact":
        path = "reports/fl10/eval/modeA/evaluation_results.json"
        lock["bound_files"][path] = "0" * 64
    elif change == "frontend":
        path = sorted(lock["frontend_files"])[0]
        lock["frontend_files"][path] = "0" * 64
    else:
        lock["candidate_promoted_or_deployed"] = True
    changed = tmp_path / "tampered.lock.json"
    changed.write_text(json.dumps(lock))
    with pytest.raises(ValueError):
        verify_lock(changed)
