"""Accept only an exact-identity NHM_UNIFIED_LIVE_FEDERATION_STUDIO_001 successor of the frozen NHM_FL10_001 lock.

Historical locks remain untouched. Mutation tests that substitute a historical lock path do not inherit the successor's re-pins, so their tamper controls stay meaningful.
The chain check (lock id, PASS, predecessor digest, bytes at the immutable predecessor commit, scope flags) is the single implementation in ``successor_chain``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts import successor_chain

ROOT = Path(__file__).resolve().parents[1]
FL10 = ROOT / "artifacts/fl10/NHM_FL10_001.lock.json"
STUDIO = ROOT / "artifacts/unified_studio/NHM_UNIFIED_LIVE_FEDERATION_STUDIO_001.lock.json"


def accepted_successor(historical_path: Path = FL10) -> dict[str, Any] | None:
    if historical_path.resolve() != FL10.resolve() or not STUDIO.exists():
        return None
    link = successor_chain.LINKS[-1]
    if link.lock_id != "NHM_UNIFIED_LIVE_FEDERATION_STUDIO_001":
        raise RuntimeError("STUDIO_SUCCESSOR_NOT_REGISTERED_IN_THE_CHAIN")
    return successor_chain.validate_link(link, ROOT)
