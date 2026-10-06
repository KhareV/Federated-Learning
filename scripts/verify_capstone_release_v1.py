# ruff: noqa: E501
"""CAPSTONE_RELEASE_VERIFIER_V1: fail-closed verification of the release layer and the protected product.
Performs no training, inference, FL, SecAgg or scientific calculation; only hashing, JSON/CSV parsing and git queries.
Usage: python -m scripts.verify_capstone_release_v1 [--pre-freeze]   (last stdout line is a JSON result; rc 0 = PASS)"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from scripts.capstone_release_lib import (
    MANIFEST_PATH,
    audit_release_text,
    case_audit,
    guide_commands,
    portability_audit,
    sha256_file,
    verify_manifest,
)

ROOT = Path(__file__).resolve().parents[1]
POLICY = "configs/capstone/cap_011_release_policy_v1.json"
CLEAN = "configs/capstone/cap_011_clean_clone_protocol_v1.json"
PROTOCOL = "configs/capstone/cap_011_release_protocol_v1.json"
GUIDE = "docs/capstone/CAPSTONE_RELEASE_GUIDE_V1.md"
LOCK = ROOT / "artifacts/capstone/CAPSTONE_RELEASE_PROTOCOL_V1.lock.json"
NON_COMMAND_GUIDE_LINES = {"cd nhm-capstone", "export PYTHONPATH=src:.", "export CAP010_OUT=<EMPTY_DIRECTORY_OUTSIDE_REPO>"}


def load(rel: str) -> dict:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def statuses() -> tuple[dict[str, str], dict[str, str]]:
    out = []
    for name, key in (("task", "task_id"), ("gate", "gate_id")):
        with (ROOT / f"manifests/capstone/{name}_registry_v1.csv").open(newline="", encoding="utf-8") as h:
            out.append({r[key]: r["status"] for r in csv.DictReader(h)})
    return out[0], out[1]


def verify(*, pre_freeze: bool = False) -> dict:
    checks: dict[str, dict] = {}

    def record(name: str, ok: bool, detail: object = "") -> None:
        checks[name] = {"ok": bool(ok), "detail": detail}

    # ---- phase / registry state (CAP-001..010 PASS; CAP-011 may be IN_PROGRESS or PASS) ----
    tasks, gates = statuses()
    record("tasks_cap001_010_pass", all(tasks.get(f"CAP-{i:03d}") == "PASS" for i in range(1, 11)))
    record("gates_capg0_9_pass", all(gates.get(f"CAPG{i}") == "PASS" for i in range(10)))
    record("cap011_state", tasks.get("CAP-011") in {"IN_PROGRESS", "PASS"} and gates.get("CAPG10") in {"NOT_STARTED", "PASS"}, {"CAP-011": tasks.get("CAP-011"), "CAPG10": gates.get("CAPG10")})
    record("no_cap012", "CAP-012" not in tasks)
    # ---- prior lineage ----
    from scripts.cap_011_protected_audit import all_locks

    locks = all_locks()
    bad = sorted(k for k, v in locks.items() if not v["verified"])
    record("prior_lineage", not bad, {"locks": len(locks), "failed": bad})
    # ---- policy / protocols ----
    policy, clean, protocol = load(POLICY), load(CLEAN), load(PROTOCOL)
    record("policy_integrity", policy["policy_id"] == "CAPSTONE_RELEASE_POLICY_V1" and policy["status"] == "FROZEN_PRE_RELEASE_POLICY" and policy["manual_override_allowed"] is False and policy["waivers_allowed"] is False
           and len(policy["hard_blockers"]) == 23 and len(policy["limitations"]) == 21 and policy["clean_clone_test_gating"]["unexpected_skips_allowed"] == 0)
    record("protocol_integrity", protocol["protocol_id"] == "CAPSTONE_RELEASE_PROTOCOL_V1" and protocol["criteria_count"] == len(protocol["capg10_criteria"]) == 136 and len(protocol["mutation_controls"]) == 20
           and protocol["release_claim"] == policy["release_claim"])
    record("clean_clone_protocol_integrity", clean["protocol_id"] == "CAPSTONE_CLEAN_CLONE_PROTOCOL_V1" and len(clean["prohibited"]) >= 12 and all(c["id"] and c["display"] for c in clean["commands"]))
    # ---- manifest ----
    manifest = load(MANIFEST_PATH)
    m = verify_manifest(manifest, ROOT)
    record("manifest_and_key_hashes", m["ok"], m["failures"])
    record("manifest_matches_policy", manifest["release_claim"] == policy["release_claim"] and manifest["limitations"] == [x["text"] for x in policy["limitations"]])
    # ---- guide ----
    text = (ROOT / GUIDE).read_text(encoding="utf-8")
    audit = audit_release_text(text)
    record("guide_claims", audit["ok"], audit)
    displays = {c["display"] for c in clean["commands"]}
    cmds = set(guide_commands(text))
    record("guide_commands_are_tested_commands", displays <= cmds and cmds - displays <= NON_COMMAND_GUIDE_LINES, {"missing": sorted(displays - cmds), "extra": sorted(cmds - displays - NON_COMMAND_GUIDE_LINES)})
    record("guide_limitations", all(x["text"] in text for x in policy["limitations"]))
    # ---- portability / case ----
    p = portability_audit(ROOT)
    record("portability", p["ok"], p["hits"][:5])
    c = case_audit(ROOT)
    record("case_collisions", c["ok"], c["case_collisions"][:5])
    # ---- the release lock (absent only before the freeze) ----
    if LOCK.exists():
        from scripts.cap_006_protected_audit import verify_amended_lock

        r = verify_amended_lock(LOCK, "CAPSTONE_RELEASE_PROTOCOL_V1.amendment_*.json")
        record("release_lock", not r["mismatches"] and not r["broken_chain_links"], {"mismatches": r["mismatches"][:5]})
        record("release_lock_binds_release_layer", all(rel in json.loads(LOCK.read_text())["bound_files"] for rel in (POLICY, CLEAN, PROTOCOL, GUIDE, MANIFEST_PATH, "scripts/verify_capstone_release_v1.py", "scripts/run_capstone_clean_release.py", "scripts/cap_011_evaluate_gate.py")))
    else:
        record("release_lock", pre_freeze, "release lock absent (allowed only with --pre-freeze)")
    ok = all(v["ok"] for v in checks.values())
    return {"status": "PASS" if ok else "FAIL", "prior_lineage_verified": checks["prior_lineage"]["ok"], "failed": [k for k, v in checks.items() if not v["ok"]], "checks": checks,
            "executes_no_science": {"training": 0, "inference": 0, "fl": 0, "secagg": 0}, "verifier_sha256": sha256_file(Path(__file__))}


if __name__ == "__main__":
    result = verify(pre_freeze="--pre-freeze" in sys.argv)
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result["status"] == "PASS" else 1)
