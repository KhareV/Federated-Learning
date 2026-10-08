"""Accept only an exact-byte FL10 successor to the frozen final-showcase lock.

Historical locks remain untouched. Mutation tests that substitute a historical lock path
do not inherit successor re-pins, so their original tamper controls remain meaningful.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FINAL = ROOT / "artifacts/final_showcase/NHM_FINAL_SHOWCASE_001.lock.json"
FL10 = ROOT / "artifacts/fl10/NHM_FL10_001.lock.json"


def accepted_successor(historical_path: Path = FINAL) -> dict[str, Any] | None:
    if historical_path.resolve() != FINAL.resolve() or not FL10.exists():
        return None
    lock = json.loads(FL10.read_text())
    expected = hashlib.sha256(FINAL.read_bytes()).hexdigest()
    if (lock.get("lock_id") != "NHM_FL10_001"
            or lock.get("predecessor_lock_sha256") != expected
            or lock.get("predecessor_commit") !=
            "274323730d1c7355f688ad4c9ff01ecbfb746501"):
        raise RuntimeError("FL10_SUCCESSOR_CHAIN_BROKEN")
    return lock
