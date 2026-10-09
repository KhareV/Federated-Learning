"""Read-only NHM-FL10-001 successor verification; accepted predecessor bytes are never re-frozen."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from fl10.audit import baseline_unchanged, reconcile
from fl10.bundle import build_bundle
from fl10.charts import build_specs
from fl10.consistency import assert_specs_have_data, check_chart_table
from fl10.runner import frozen_progression, load_state
from fl10.tables import build_tables

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "274323730d1c7355f688ad4c9ff01ecbfb746501"
METHOD_COMMIT = "f91a96a6c5a38432e4fc84f7e760c21874ce2d40"
LOCK_PATH = ROOT / "artifacts/fl10/NHM_FL10_001.lock.json"
PREDECESSOR = "artifacts/final_showcase/NHM_FINAL_SHOWCASE_001.lock.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def at_commit(commit: str, path: str) -> bytes:
    return subprocess.run(["git", "show", f"{commit}:{path}"], cwd=ROOT,
                          capture_output=True, check=True).stdout


def verify_evidence() -> dict[str, Any]:
    if baseline_unchanged()["changed"]:
        raise ValueError("PROTECTED_BASELINE_CHANGED")
    baseline = json.loads((ROOT / "reports/fl10/baseline_hashes.json").read_text())
    pred_hash = sha(ROOT / PREDECESSOR)
    if pred_hash != hashlib.sha256(at_commit(BASELINE, PREDECESSOR)).hexdigest():
        raise ValueError("PREDECESSOR_LOCK_CHANGED")
    method_paths = ("configs/fl10/protocol_v1.json", "configs/fl10/holdout_manifest_v1.json")
    method_hashes = {}
    for path in method_paths:
        current = sha(ROOT / path)
        if current != hashlib.sha256(at_commit(METHOD_COMMIT, path)).hexdigest():
            raise ValueError(f"METHOD_FREEZE_CHANGED:{path}")
        method_hashes[path] = current
    out: dict[str, Any] = {"baseline": BASELINE, "method_commit": METHOD_COMMIT,
                           "predecessor_lock_sha256": pred_hash,
                           "method_hashes": method_hashes,
                           "protected_count": sum(len(baseline[group]) for group in
                                                  ("locks", "protected_files")),
                           "modes": {}}
    reference = frozen_progression()
    for mode in ("modeA", "modeB"):
        run_dir = ROOT / "reports/fl10/runs" / mode
        eval_dir = ROOT / "reports/fl10/eval" / mode
        pub_dir = ROOT / "reports/fl10/publication" / mode
        run = json.loads((run_dir / "run_report.json").read_text())
        if (run["status"] != "COMPLETED" or run["rounds_committed"] != 10
                or run["accepted_updates_total"] != 80
                or run["example_exposures_total"] != 7230
                or len(run["updates"]) != 80 or len(run["client_rounds"]) != 80
                or len(run["rounds"]) != 10 or len(run["state_progression"]) != 11
                or run["candidate"]["promoted"] or run["candidate"]["deployed"]):
            raise ValueError(f"RUN_ACCOUNTING_FAILED:{mode}")
        if mode == "modeA" and any(
            run["state_progression"][str(round_id)]["sha256"] != reference[str(round_id)]
            for round_id in range(4)
        ):
            raise ValueError("CANONICAL_R0_R3_PARITY_FAILED")
        for round_id in range(11):
            load_state(run_dir, round_id,
                       run["state_progression"][str(round_id)]["sha256"])
        for round_row in run["rounds"]:
            if (round_row["accepted_updates"] != 8
                    or round_row["total_accepted_example_weight"] != 723
                    or abs(sum(round_row["weights"].values()) - 1) > 1e-12
                    or not round_row["state_info"]["finite"]):
                raise ValueError(f"ROUND_ACCOUNTING_FAILED:{mode}:{round_row['round']}")
        if mode == "modeB":
            link = json.loads((run_dir / "monitoring_link.json").read_text())
            if (link["monitoring_sessions_executed"] != 1
                    or link["buffer_reused_for_rounds"] != 10
                    or not link["trace"]["verified"]
                    or link["trace"]["rounds_traced"] != 10):
                raise ValueError("MODE_B_MONITORING_TRACE_FAILED")
        prediction_check = reconcile(eval_dir)
        if not prediction_check["all_ok"] or prediction_check["windows"] != 1446:
            raise ValueError(f"PREDICTION_RECONCILIATION_FAILED:{mode}")
        evaluation = json.loads((eval_dir / "evaluation_results.json").read_text())
        if (evaluation["threshold"] != 0.5 or evaluation["calibration"] != "NONE"
                or evaluation["state_digests"] != {
                    f"R{round_id:02d}": run["state_progression"][str(round_id)]["sha256"]
                    for round_id in range(11)
                }):
            raise ValueError(f"EVALUATION_STATE_OR_THRESHOLD_MISMATCH:{mode}")
        bundle = build_bundle(run_dir, eval_dir)
        specs, tables = build_specs(bundle), build_tables(bundle)
        assert_specs_have_data(specs, [f"FL10_FIG{i:02d}" for i in range(1, 21)])
        checks = check_chart_table(specs, tables)
        if len(tables) != 12:
            raise ValueError(f"TABLE_INVENTORY_FAILED:{mode}")
        manifest = json.loads((pub_dir / "export_manifest.json").read_text())
        if len(manifest["figures"]) != 20 or len(manifest["tables"]) != 12:
            raise ValueError(f"EXPORT_INVENTORY_FAILED:{mode}")
        export_count = 0
        for collection in (manifest["figures"], manifest["tables"]):
            for files in collection.values():
                for item in files.values():
                    export_path = (ROOT / item["path"]).resolve()
                    if (not export_path.is_relative_to(pub_dir.resolve())
                            or sha(export_path) != item["sha256"]):
                        raise ValueError(f"EXPORT_HASH_FAILED:{mode}:{item['path']}")
                    export_count += 1
        out["modes"][mode] = {"run_id": run["run_id"],
                              "candidate_digest": run["candidate"]["state_sha256"],
                              "state_digests": {key: value["sha256"] for key, value in
                                                run["state_progression"].items()},
                              "update_digests": [item["update_sha256"] for item in run["updates"]],
                              "accepted_updates": 80, "evaluation_windows": 1446,
                              "chart_table_checks": len(checks), "exports": export_count,
                              "export_manifest_sha256": sha(pub_dir / "export_manifest.json")}
    if out["modes"]["modeA"]["state_digests"] != out["modes"]["modeB"]["state_digests"]:
        raise ValueError("MODE_B_STATE_PARITY_FAILED")
    return out


def verify_lock(path: Path = LOCK_PATH) -> dict[str, Any]:
    evidence = verify_evidence()
    lock = json.loads(path.read_text())
    if (lock["lock_id"] != "NHM_FL10_001"
            or lock["predecessor_commit"] != BASELINE
            or lock["predecessor_lock_sha256"] != evidence["predecessor_lock_sha256"]
            or lock["method_commit"] != METHOD_COMMIT
            or lock["method_hashes"] != evidence["method_hashes"]
            or lock["mode_evidence"] != evidence["modes"]
            or lock["status"] != "PASS"):
        raise ValueError("FL10_LOCK_IDENTITY_OR_EVIDENCE_MISMATCH")
    from scripts.freeze_observatory_v1 import frontend_files
    from scripts.studio_successor_compat import accepted_successor as studio_successor

    studio = studio_successor(path)         # None unless this is the canonical lock and a valid additive Studio successor exists
    predecessor = json.loads((ROOT / PREDECESSOR).read_text())
    repins = sorted(relative for relative, digest in predecessor["bound_files"].items()
                    if (ROOT / relative).is_file() and sha(ROOT / relative) != digest)
    expected_repins = set(lock["repins_predecessor_files"])
    if studio:    # files of the final-showcase lock that the Studio successor (and only it) re-pinned again
        expected_repins |= {relative for relative in studio["repins_predecessor_files"] if relative in predecessor["bound_files"]}
    if sorted(expected_repins) != repins:
        raise ValueError("FL10_PREDECESSOR_REPIN_SET_MISMATCH")
    expected_frontend = studio["frontend_files"] if studio else lock["frontend_files"]
    if set(expected_frontend) != set(frontend_files()) or any(
        sha(ROOT / relative) != digest
        for relative, digest in expected_frontend.items()
    ):
        raise ValueError("FL10_FRONTEND_BINDING_DRIFT")
    for key in ("released_model_changed", "calibration_applied_to_candidate",
                "candidate_promoted_or_deployed", "hardware_work_performed",
                "historical_locks_edited", "automatically_pushed"):
        if lock[key] is not False:
            raise ValueError(f"FL10_SCOPE_DRIFT:{key}")
    if not lock["test_results"]["passed"] or not lock["browser_result"]["passed"]:
        raise ValueError("FL10_UNVERIFIED_ACCEPTANCE")
    for relative, expected in lock["bound_files"].items():
        target = ROOT / relative
        accepted = {expected}
        if studio and relative in studio["repins_predecessor_files"]:
            accepted.add(studio["bound_files"][relative])
        if not target.is_file() or sha(target) not in accepted:
            raise ValueError(f"FL10_LOCK_BOUND_FILE_TAMPER:{relative}")
    return {"status": "PASS", "bound_files": len(lock["bound_files"]),
            "modes": {key: {"candidate_digest": value["candidate_digest"],
                            "accepted_updates": value["accepted_updates"]}
                      for key, value in evidence["modes"].items()}}


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", action="store_true")
    args = parser.parse_args()
    result = verify_lock() if args.lock else verify_evidence()
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
