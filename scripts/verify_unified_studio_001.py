# ruff: noqa: E501
"""Read-only NHM_UNIFIED_LIVE_FEDERATION_STUDIO_001 verification. Accepted predecessor bytes are never re-frozen; the lock is an additive successor of NHM_FL10_001.

``verify_evidence`` checks facts that do not depend on the lock (preservation of frozen science and historical locks, the recorded run evidence, the live-run evidence files).
``verify_lock`` additionally checks the lock against the working tree and runs the entire older verifier chain."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from scripts import successor_chain

ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "artifacts/unified_studio/NHM_UNIFIED_LIVE_FEDERATION_STUDIO_001.lock.json"
PREDECESSOR = "artifacts/fl10/NHM_FL10_001.lock.json"
FL10_COMMIT = successor_chain.FL10_COMMIT
EVIDENCE = "reports/unified_live_fl"
# Anything that defines frozen science, training mathematics, the frozen 3-round backend or the recorded evidence: must be byte-identical to the FL10 commit.
PROTECTED_SURFACE = ("reports/model_v2", "reports/fl10", "reports/final_showcase", "configs/fl10", "federated", "models", "checkpoints", "training", "preprocessing", "privacy", "simulation", "product", "src", "final_showcase",
                     "fl10/charts.py", "fl10/tables.py", "fl10/figures.py", "fl10/evaluate.py", "fl10/metrics.py", "fl10/bundle.py", "fl10/holdout.py", "capstone_persistence", "contracts")
ALLOWED_ARTIFACT_PREFIX = "artifacts/unified_studio/"
FLAGS_FALSE = ("released_model_changed", "calibration_applied_to_candidate", "candidate_promoted_or_deployed", "hardware_work_performed", "historical_locks_edited", "automatically_pushed", "frozen_scientific_evidence_edited")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def verify_evidence() -> dict[str, Any]:
    from fl10.audit import baseline_unchanged

    out: dict[str, Any] = {"predecessor_commit": FL10_COMMIT}
    changed = [p for p in git("diff", "--name-only", FL10_COMMIT, "--", *PROTECTED_SURFACE).splitlines() if p]
    if changed:
        raise ValueError(f"PROTECTED_SURFACE_CHANGED:{changed[:5]}")
    historical = []
    for line in git("diff", "--name-status", FL10_COMMIT, "--", "artifacts").splitlines():
        code, _, path = line.partition("\t")
        additive_amendment = code == "A" and re.fullmatch(r"artifacts/(?:capstone|final_eval_repair|ufl_lite)/[A-Z]+(?:_[A-Z0-9]+)*_PROTOCOL_V1\.amendment_[0-9_]+\.json", path) is not None
        if path and not path.startswith(ALLOWED_ARTIFACT_PREFIX) and not additive_amendment:      # only NEW compatibility amendments (FL10's mechanism) may appear; no historical file is modified or deleted
            historical.append(line)
    if historical:
        raise ValueError(f"HISTORICAL_LOCK_OR_AMENDMENT_CHANGED:{historical[:5]}")
    if baseline_unchanged()["changed"]:
        raise ValueError("FL10_PROTECTED_BASELINE_CHANGED")
    if hashlib.sha256(subprocess.run(["git", "show", f"{FL10_COMMIT}:{PREDECESSOR}"], cwd=ROOT, capture_output=True, check=True).stdout).hexdigest() != sha(ROOT / PREDECESSOR):
        raise ValueError("PREDECESSOR_LOCK_CHANGED")
    out["predecessor_lock_sha256"] = sha(ROOT / PREDECESSOR)
    runs: dict[str, Any] = {}
    modes = [(3, 24, ""), (10, 80, "")] + ([(10, 80, "_modeB")] if (ROOT / EVIDENCE / "run_evidence_10round_modeB.json").exists() else [])
    for n, expected_updates, suffix in modes:
        ev = json.loads((ROOT / EVIDENCE / f"run_evidence_{n}round{suffix}.json").read_text())
        if suffix and ev["source_mode"] != "LIVE_MONITORED_SITE_00":
            raise ValueError("MODE_B_EVIDENCE_WRONG_SOURCE_MODE")
        records = ev["metric_table"]
        if (ev["status"] != "COMPLETED" or ev["accepted_updates_total"] != expected_updates or len(records) != n + 1 or any(r["status"] != "COMPLETED" for r in records) or ev["threshold"] != 0.5 or ev["calibration"] != "NONE"
                or ev["candidate"]["promoted"] or ev["candidate"]["deployed"]):
            raise ValueError(f"LIVE_RUN_EVIDENCE_FAILED:{n}")
        if not all(x["equals_recorded_fl10_digest"] and x["equals_recorded_fl10_metrics"] for x in ev["lineage_vs_recorded"] if x["round"] <= (10 if n == 10 else 3)):
            raise ValueError(f"LIVE_RUN_DOES_NOT_REPRODUCE_RECORDED_STATES:{n}")
        if set(ev["figures"].values()) != {"AVAILABLE"} or len(ev["figures"]) != 20 or len(ev["tables"]) != 12 or ev["export_counts"] != {"figures": 20, "tables": 12, "data": ev["export_counts"]["data"]}:
            raise ValueError(f"LIVE_RUN_FIGURE_TABLE_EXPORT_INVENTORY_FAILED:{n}")
        if not all(a["accepted_updates"] == 8 and abs(a["weights_sum"] - 1) < 1e-12 and a["clients"] == 8 for a in ev["round_accounting"]) or len(ev["round_accounting"]) != n:
            raise ValueError(f"LIVE_RUN_ROUND_ACCOUNTING_FAILED:{n}")
        runs[f"{n}{suffix}"] = {"run_id": ev["run_id"], "evidence_sha256": sha(ROOT / EVIDENCE / f"run_evidence_{n}round{suffix}.json"), "state_digests": {str(r["round"]): r["state_digest"] for r in records}, "export_manifest_sha256": ev["export_manifest_sha256"]}
    out["live_runs"] = runs
    for name in ("studio_browser_verification.json",):
        report = json.loads((ROOT / EVIDENCE / "browser" / name).read_text())
        if not report["passed"] or report["failed"]:
            raise ValueError("BROWSER_VERIFICATION_NOT_PASSED")
    pretrained: dict[str, Any] = {}
    for label, count in (("pretrained 10-round", 11), ("pretrained 3-round", 4)):
        gen = (report.get("evidence") or {}).get(f"{label}_generalisation")
        if (gen is None or gen["base_model"]["model_id"] != "MODEL_V2_FINAL" or gen["base_model"].get("checkpoint_sha256") not in (None, "89418edcc2c13f0edd9a36666bac560ad922dd4700b4b6dd19b56d067d4eff9b")
                or gen["integrity"] != {"r0_digest_equals_frozen_v2": True, "r0_predictions_equal_frozen_v2": True} or len(gen["rounds"]) != count or gen["rounds"][0]["digest"] != gen["baseline"]["digest"]
                or len({r["digest"] for r in gen["rounds"]}) != count):
            raise ValueError(f"PRETRAINED_GENERALISATION_EVIDENCE_FAILED:{label}")
        pretrained[label] = {"R0_equals_frozen_v2": True, "rounds": count, f"R{count - 1}_AUPRC": gen["rounds"][count - 1]["AUPRC"], "frozen_v2_AUPRC": gen["baseline"]["AUPRC"]}
    out["pretrained_generalisation"] = pretrained
    sidebar = json.loads((ROOT / EVIDENCE / "browser" / "sidebar_verification.json").read_text())
    if not sidebar["passed"] or sidebar["failed"] or sidebar["total"] < 19:
        raise ValueError("SIDEBAR_BROWSER_VERIFICATION_NOT_PASSED")
    out["sidebar_checks"] = sidebar["total"]
    tests = json.loads((ROOT / EVIDENCE / "local_test_report.json").read_text())
    if not tests["passed"]:
        raise ValueError("LOCAL_TEST_REPORT_NOT_PASSED")
    out["browser_checks"] = report["total"]
    out["tests_sha256"] = sha(ROOT / EVIDENCE / "local_test_report.json")
    return out


def older_chain() -> dict[str, str]:
    """Every accepted older verifier must still pass against the current tree (successor-aware)."""
    from scripts import (
        verify_capstone_ui_v1,
        verify_capstone_ui_v1_1,
        verify_capstone_ui_v1_2,
        verify_capstone_ui_v1_3,
        verify_capstone_ui_v1_4,
        verify_capstone_ui_v1_5,
        verify_capstone_ui_v1_6,
        verify_capstone_ui_v1_7,
        verify_capstone_ui_v1_8,
        verify_capstone_ui_v1_9,
        verify_final_showcase,
        verify_fl10_001,
        verify_obs_diag_001,
        verify_observatory_v1,
    )

    results = {}
    for name, module in (("CAPSTONE_UI_V1", verify_capstone_ui_v1), ("CAPSTONE_UI_V1_1", verify_capstone_ui_v1_1), ("CAPSTONE_UI_V1_2", verify_capstone_ui_v1_2), ("CAPSTONE_UI_V1_3", verify_capstone_ui_v1_3),
                         ("CAPSTONE_UI_V1_4", verify_capstone_ui_v1_4), ("CAPSTONE_UI_V1_5", verify_capstone_ui_v1_5), ("CAPSTONE_UI_V1_6", verify_capstone_ui_v1_6), ("CAPSTONE_UI_V1_7", verify_capstone_ui_v1_7),
                         ("CAPSTONE_UI_V1_8", verify_capstone_ui_v1_8), ("CAPSTONE_UI_V1_9", verify_capstone_ui_v1_9), ("NHM_RESEARCH_OBSERVATORY_V1", verify_observatory_v1), ("NHM_OBS_DIAG_001", verify_obs_diag_001),
                         ("NHM_FINAL_SHOWCASE_001", verify_final_showcase)):
        result = module.verify_lock() if module is verify_final_showcase else module.verify()      # final showcase: the lock check; the others expose verify()
        ok = bool(result.get("obs_diag_chain_verified") and result.get("v1_chain_verified")) if module is verify_final_showcase else result.get("status") == "PASS"   # the final-showcase lock carries its own status word
        if not ok:
            raise ValueError(f"OLDER_VERIFIER_FAILED:{name}")
        results[name] = "PASS"
    if verify_fl10_001.verify_lock()["status"] != "PASS":
        raise ValueError("OLDER_VERIFIER_FAILED:NHM_FL10_001")
    results["NHM_FL10_001"] = "PASS"
    from scripts.cap_010_protected_audit import all_locks

    unverified = sorted(k for k, v in all_locks().items() if not v.get("verified"))      # CAP-001..010 amended-lock chain, research catalog, history evidence
    if unverified:
        raise ValueError(f"OLDER_LOCK_AUDIT_FAILED:{unverified}")
    results["CAPSTONE_AMENDED_LOCK_AUDITS"] = "PASS"
    return results


def verify_lock(path: Path = LOCK_PATH, *, with_older_chain: bool = True) -> dict[str, Any]:
    evidence = verify_evidence()
    lock = json.loads(path.read_text())
    link = successor_chain.LINKS[-1]
    successor_chain.validate_link(link, ROOT, lock_override=lock)           # id, PASS, predecessor digest, bytes at the immutable predecessor commit, scope flags, frontend binding
    if lock.get("provisional") is not False:
        raise ValueError("STUDIO_LOCK_IS_PROVISIONAL")
    if lock["predecessor_commit"] != FL10_COMMIT or lock["predecessor_lock_sha256"] != evidence["predecessor_lock_sha256"]:
        raise ValueError("STUDIO_PREDECESSOR_IDENTITY_MISMATCH")
    for flag in FLAGS_FALSE:
        if lock[flag] is not False:
            raise ValueError(f"STUDIO_SCOPE_DRIFT:{flag}")
    predecessor = json.loads((ROOT / PREDECESSOR).read_text())
    repins = sorted(relative for relative, digest in predecessor["bound_files"].items() if (ROOT / relative).is_file() and sha(ROOT / relative) != digest)
    if lock["repins_predecessor_files"] != repins:
        raise ValueError("STUDIO_PREDECESSOR_REPIN_SET_MISMATCH")
    from scripts.freeze_observatory_v1 import frontend_files

    if set(lock["frontend_files"]) != set(frontend_files()) or any(sha(ROOT / r) != d for r, d in lock["frontend_files"].items()):
        raise ValueError("STUDIO_FRONTEND_BINDING_DRIFT")
    for relative, expected in lock["bound_files"].items():
        target = ROOT / relative
        if not target.is_file() or sha(target) != expected:
            raise ValueError(f"STUDIO_LOCK_BOUND_FILE_TAMPER:{relative}")
    if lock["live_runs"] != evidence["live_runs"] or lock["evidence"]["tests_sha256"] != evidence["tests_sha256"]:
        raise ValueError("STUDIO_LOCK_EVIDENCE_MISMATCH")
    if lock["connected_clerk_two_user_e2e"] != "NOT EXECUTED":
        raise ValueError("STUDIO_CLERK_CLAIM_NOT_PERMITTED")
    if not lock["test_results"]["passed"] or not lock["browser_result"]["passed"]:
        raise ValueError("STUDIO_UNVERIFIED_ACCEPTANCE")
    older = older_chain() if with_older_chain else {}
    return {"status": "PASS", "bound_files": len(lock["bound_files"]), "frontend_files": len(lock["frontend_files"]), "repins": len(repins), "older_chain": older, "live_runs": {k: v["run_id"] for k, v in evidence["live_runs"].items()}}


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", action="store_true")
    args = parser.parse_args()
    print(json.dumps(verify_lock() if args.lock else verify_evidence(), sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
