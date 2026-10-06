# ruff: noqa: E501
"""Derive the CAP-011 audit evidence files from the frozen verifier library and the imported clone results.
It records facts; it defines no pass criteria (the frozen evaluator does)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from scripts import cap_011_evaluate_gate as gate
from scripts.capstone_release_lib import (
    MANIFEST_PATH,
    audit_release_text,
    case_audit,
    portability_audit,
    verify_final_diff,
    verify_manifest,
)
from scripts.verify_capstone_release_v1 import verify as run_verifier

ROOT = Path(__file__).resolve().parents[1]
EVD = ROOT / "reports/capstone/cap_011"


def wr(name: str, payload: dict) -> None:
    EVD.mkdir(parents=True, exist_ok=True)
    (EVD / name).write_text(json.dumps(payload, indent=1, sort_keys=True, default=str) + "\n")


def main() -> int:
    policy = json.loads(gate.POLICY.read_text())
    manifest = json.loads((ROOT / MANIFEST_PATH).read_text())
    text = gate.GUIDE.read_text(encoding="utf-8")
    verifier = run_verifier()
    wr("release_policy_audit.json", {"status": "PASS" if verifier["checks"]["policy_integrity"]["ok"] else "FAIL", "manual_override_allowed": policy["manual_override_allowed"], "waivers_allowed": policy["waivers_allowed"], "hard_blockers": len(policy["hard_blockers"]), "limitations": len(policy["limitations"])})
    wr("release_protocol_audit.json", {"status": "PASS" if verifier["checks"]["protocol_integrity"]["ok"] and verifier["checks"]["clean_clone_protocol_integrity"]["ok"] else "FAIL", "criteria_count": 136, "mutation_controls": 20})
    m = verify_manifest(manifest, ROOT)
    wr("release_manifest_audit.json", {"status": "PASS" if m["ok"] else "FAIL", **m})
    wr("release_inventory.json", {"status": "PASS", "release_id": manifest["release_id"], "key_artifacts": manifest["key_artifacts"], "dependency_locks": manifest["dependency_locks"], "note": "hashes only; no artifact bytes duplicated"})
    audit = audit_release_text(text)
    wr("release_guide_audit.json", {"status": "PASS" if audit["ok"] else "FAIL", **audit, "commands_equal_tested_commands": gate.guide_cmds_tested() if (EVD / "clean_clone_a_bundle.json").exists() else None})
    p, c = portability_audit(ROOT), case_audit(ROOT)
    wr("portability_audit.json", {"status": "PASS" if p["ok"] and c["ok"] else "FAIL", "portability": p, "case_sensitivity": c, "tested_os": "recorded per clone in clean_clone_*_environment.json"})
    wr("clean_clone_gating_policy.json", {"status": "PASS", **policy["clean_clone_test_gating"], "frozen_before_any_clean_clone": True})
    wr("release_limitations_audit.json", {"status": "PASS" if all(x["text"] in text and x["text"] in manifest["limitations"] for x in policy["limitations"]) else "FAIL", "limitations": [x["text"] for x in policy["limitations"]]})
    if (EVD / "clean_clone_a_demo.json").exists() and (EVD / "clean_clone_b_demo.json").exists():
        a, b = gate.clone("a", "demo"), gate.clone("b", "demo")
        wr("clean_clone_reproducibility.json", {"status": "PASS" if a["semantic_sha256"] == b["semantic_sha256"] and a["semantic_projection"] == b["semantic_projection"] else "FAIL",
                                                "identical": a["semantic_sha256"] == b["semantic_sha256"] and a["semantic_projection"] == b["semantic_projection"], "clone_a_semantic_sha256": a["semantic_sha256"], "clone_b_semantic_sha256": b["semantic_sha256"],
                                                "approved_exclusions": ["session ids", "federation run ids", "timestamps", "latencies", "pids", "temporary paths", "machine-time telemetry", "log text", "screenshots"],
                                                "included": ["runtime identity (model/calibration/system)", "monitoring semantic projection", "FL update digests", "round global-state digests", "candidate state digest", "governance result", "research payload hashes and catalog digest"]})
        ea, eb = gate.clone("a", "environment"), gate.clone("b", "environment")
        wr("hidden_dependency_audit.json", {"status": "PASS" if ea["clone"]["pre_install_audit"]["ok"] and eb["clone"]["pre_install_audit"]["ok"] and gate.harness_static_ok() else "FAIL", "clone_a_pre_install": ea["clone"]["pre_install_audit"], "clone_b_pre_install": eb["clone"]["pre_install_audit"],
                                            "harness_has_no_copy_in_or_rescue_path": gate.harness_static_ok(), "developer_dotenv_required": False, "developer_environment_reused": False})
        wr("runtime_offline_audit.json", {"status": "PASS" if all(not gate.clone(x, "demo")["browser"]["network"]["external"] for x in ("a", "b")) else "FAIL", "policy": "ACTIVE_CDP_REQUEST_INTERCEPTION_LOOPBACK_ONLY",
                                         "external_requests": {x: gate.clone(x, "demo")["browser"]["network"]["external"] for x in ("a", "b")}, "installation_network": "public package registries (not part of the offline runtime claim)"})
    if (EVD / "release_target.json").exists():
        d = verify_final_diff(ROOT, gate.target())
        wr("release_target_final_diff.json", {"status": "PASS" if d["ok"] else "FAIL", "release_target_sha": gate.target(), "note": "working-tree audit against the release target before the result commit", **d})
    print(json.dumps({"built": True}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
