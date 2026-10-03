#!/usr/bin/env python3
"""Create the E2E_REPLAY_SOFTWARE_V1_3 successor lock (V2-013).

E2E_REPLAY_SOFTWARE_V1_2 binds the dashboard route source and DASHBOARD_UI_V1_2, both superseded
by the V2-013 frontend model-identity fix (DASHBOARD_UI_V1_4). The V1 replay evidence itself
(digests, reproducibility) is unchanged: the edit does not alter any request/response behavior
for MODEL_V1. V1_3 re-binds the current route/controller and DASHBOARD_UI_V1_4 and carries the
V1_2 replay facts forward verbatim. V1_2 is never mutated.
"""

from __future__ import annotations

import json
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
PREDECESSOR_PATH = ROOT / "artifacts/E2E_REPLAY_SOFTWARE_V1_2.lock.json"
PREDECESSOR_ID = "E2E_REPLAY_SOFTWARE_V1_2"


def main() -> None:
    predecessor_sha = hash_file(PREDECESSOR_PATH)
    predecessor = json.loads(PREDECESSOR_PATH.read_text(encoding="utf-8"))
    bound = [
        "artifacts/DASHBOARD_UI_V1_4.lock.json" if p == "artifacts/DASHBOARD_UI_V1_2.lock.json"
        else p
        for p in predecessor["bound_artifacts"]
    ]
    dropped = {"lock_id", "predecessor_id", "predecessor_sha256", "checkpoint", "reason",
               "bound_artifacts", "dashboard_ui_lock_id", "dashboard_ui_lock_sha256",
               "canonical_monitoring_route_sha256"}
    lock = {
        **{k: v for k, v in predecessor.items() if k not in dropped},
        "lock_id": "E2E_REPLAY_SOFTWARE_V1_3",
        "predecessor_id": PREDECESSOR_ID,
        "predecessor_sha256": predecessor_sha,
        "checkpoint": "V2-013",
        "reason": (
            "re-bind the current dashboard route and DASHBOARD_UI_V1_4 after the V2-013 "
            "model-identity frontend fix; V1_2 replay digests and reproducibility facts are "
            "carried forward unchanged (MODEL_V1 request/response behavior is unchanged)"
        ),
        "dashboard_ui_lock_id": "DASHBOARD_UI_V1_4",
        "dashboard_ui_lock_sha256": hash_file(ROOT / "artifacts/DASHBOARD_UI_V1_4.lock.json"),
        "canonical_monitoring_route_sha256": hash_file(
            ROOT / "frontend/src/routes/monitoring/+page.svelte"),
        "bound_artifacts": {p: hash_file(ROOT / p) for p in bound},
    }
    dest = ROOT / "artifacts/E2E_REPLAY_SOFTWARE_V1_3.lock.json"
    dest.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    supersedes = {
        "successor_id": "E2E_REPLAY_SOFTWARE_V1_3", "predecessor_id": PREDECESSOR_ID,
        "predecessor_sha256": predecessor_sha,
        "predecessor_status_at_supersession": predecessor["status"],
        "predecessor_preserved_unchanged": True, "reason": lock["reason"],
        "checkpoint": "V2-013",
    }
    sup = ROOT / "artifacts/E2E_REPLAY_SOFTWARE_V1_3.supersedes.json"
    sup.write_text(json.dumps(supersedes, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(hash_file(dest))
    print(hash_file(sup))


if __name__ == "__main__":
    main()
