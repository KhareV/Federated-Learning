"""Narrow successor resolver for the UI-ENH-002 frontend-only lock."""

from __future__ import annotations

import json
from pathlib import Path

from nhm.hashing import hash_file


def v18_bound(root: Path) -> dict[str, str] | None:
    path = root / "artifacts/capstone/CAPSTONE_UI_V1_8.lock.json"
    if not path.exists():
        return None
    lock = json.loads(path.read_text(encoding="utf-8"))
    predecessor = root / "artifacts/capstone/CAPSTONE_UI_V1_7.lock.json"
    if (
        lock.get("lock_id") != "CAPSTONE_UI_V1_8"
        or lock.get("predecessor_id") != "CAPSTONE_UI_V1_7"
        or lock.get("predecessor_sha256") != hash_file(predecessor)
    ):
        raise RuntimeError("CAPSTONE_UI_V1_8_SUCCESSOR_CHAIN_BROKEN")
    previous = json.loads(predecessor.read_text(encoding="utf-8"))
    v16 = root / "artifacts/capstone/CAPSTONE_UI_V1_6.lock.json"
    if (
        previous.get("predecessor_id") != "CAPSTONE_UI_V1_6"
        or previous.get("predecessor_sha256") != hash_file(v16)
    ):
        raise RuntimeError("CAPSTONE_UI_V1_7_SUCCESSOR_CHAIN_BROKEN")
    v19 = root / "artifacts/capstone/CAPSTONE_UI_V1_9.lock.json"
    if v19.exists():
        successor = json.loads(v19.read_text(encoding="utf-8"))
        if (
            successor.get("lock_id") != "CAPSTONE_UI_V1_9"
            or successor.get("predecessor_id") != "CAPSTONE_UI_V1_8"
            or successor.get("predecessor_sha256") != hash_file(path)
        ):
            raise RuntimeError("CAPSTONE_UI_V1_9_SUCCESSOR_CHAIN_BROKEN")
        observatory = root / "artifacts/observatory/NHM_RESEARCH_OBSERVATORY_V1.lock.json"
        if observatory.exists():
            tip = json.loads(observatory.read_text(encoding="utf-8"))
            if (
                tip.get("lock_id") != "NHM_RESEARCH_OBSERVATORY_V1"
                or tip.get("predecessor_id") != "CAPSTONE_UI_V1_9"
                or tip.get("predecessor_sha256") != hash_file(v19)
            ):
                raise RuntimeError("NHM_RESEARCH_OBSERVATORY_V1_SUCCESSOR_CHAIN_BROKEN")
            return dict(tip["bound_artifacts"])
        return dict(successor["bound_artifacts"])
    return dict(lock["bound_artifacts"])
