# ruff: noqa: E501
"""Fail-closed verification of the CLERK-LIVE-001 connected layer (lock chain, UI successor chain, protocol, runbook claims). No network, no Clerk."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from scripts.capstone_release_lib import audit_release_text

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "artifacts/clerk_connected/CLERK_LIVE_001_PROTOCOL_V1.lock.json"


def verify(*, pre_freeze: bool = False) -> dict:
    checks: dict[str, dict] = {}

    def record(name: str, ok: bool, detail: object = "") -> None:
        checks[name] = {"ok": bool(ok), "detail": detail}

    from scripts.cap_011_protected_audit import all_locks
    from scripts.verify_capstone_ui_v1 import verify as v1
    from scripts.verify_capstone_ui_v1_1 import verify as v11
    from scripts.verify_capstone_ui_v1_2 import verify as v12
    from scripts.verify_capstone_ui_v1_3 import verify as v13

    locks = all_locks()
    record("prior_capstone_lineage", all(v["verified"] for v in locks.values()), {"locks": len(locks)})
    record("ui_chain_v1_to_v1_3", all(f()["status"] == "PASS" for f in (v1, v11, v12, v13)))
    config = json.loads((ROOT / "configs/clerk_connected/clerk_live_001_protocol_v1.json").read_text())
    record("protocol_integrity", config["criteria_count"] == len(config["clerkg0_criteria"]) == 88 and len(config["mutation_controls"]) == 20)
    record("runbook_claims", audit_release_text((ROOT / "docs/capstone/CLERK_CONNECTED_RUNBOOK_V1.md").read_text(), require=False)["ok"])
    if LOCK.exists():
        from scripts.cap_006_protected_audit import verify_amended_lock

        r = verify_amended_lock(LOCK, "CLERK_LIVE_001_PROTOCOL_V1.amendment_*.json")
        record("connected_lock", not r["mismatches"] and not r["broken_chain_links"], {"mismatches": r["mismatches"][:5]})
    else:
        record("connected_lock", pre_freeze, "absent (allowed only with --pre-freeze)")
    ok = all(v["ok"] for v in checks.values())
    return {"status": "PASS" if ok else "FAIL", "failed": [k for k, v in checks.items() if not v["ok"]], "checks": checks}


if __name__ == "__main__":
    res = verify(pre_freeze="--pre-freeze" in sys.argv)
    print(json.dumps(res, sort_keys=True))
    raise SystemExit(0 if res["status"] == "PASS" else 1)
