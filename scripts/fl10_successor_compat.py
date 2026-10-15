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
    # The unified Studio is the next additive successor: older verifiers see ONE merged view (FL10 pins, overridden only where the Studio lock re-pins a file).
    from scripts.studio_successor_compat import accepted_successor as studio_successor

    studio = studio_successor(FL10)
    if studio is not None:
        lock = dict(lock)
        lock["frontend_files"] = dict(studio["frontend_files"])
        lock["bound_files"] = {**lock["bound_files"], **{p: studio["bound_files"][p] for p in studio["repins_predecessor_files"]}}
        lock["repins_predecessor_files"] = sorted(set(lock["repins_predecessor_files"]) | set(studio["repins_predecessor_files"]))
    from scripts import successor_chain

    studio_index = next(i for i, item in enumerate(successor_chain.LINKS) if item.lock_id == "NHM_UNIFIED_LIVE_FEDERATION_STUDIO_001")
    for later_link in successor_chain.LINKS[studio_index + 1:]:
        if not (ROOT / later_link.path).is_file():
            break
        later = successor_chain.validate_link(later_link, ROOT)
        changes = later.get("bound_files", {})
        if not isinstance(changes, dict):
            raise RuntimeError(f"{later_link.lock_id}_BOUND_FILE_DRIFT")
        previous = dict(lock["bound_files"])
        previous_frontend = dict(lock["frontend_files"])
        changed_frontend = {p: d for p, d in later["frontend_files"].items() if previous_frontend.get(p) != d}
        lock = dict(lock)
        lock["frontend_files"] = dict(later["frontend_files"])
        lock["bound_files"] = {**previous, **changes, **changed_frontend}
        lock["repins_predecessor_files"] = sorted(set(lock["repins_predecessor_files"]) | {p for p, d in changes.items() if previous.get(p) != d} | set(changed_frontend))
    if any(not (ROOT / path).is_file() or hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != digest
           for path, digest in lock["bound_files"].items()):
        raise RuntimeError("SUCCESSOR_TIP_BOUND_FILE_DRIFT")
    return lock
