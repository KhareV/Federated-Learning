#!/usr/bin/env python3
"""V2-014 evidence verifier: verifies the lock-bound method files and, when the committed clone-1
evidence package exists, every recorded hash and cross-reference -- it does not trust prose.

Usage: python -m scripts.verify_v2_014_evidence [--out FILE]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "artifacts/MODEL_V2_COMPLETE_REPRO_PROTOCOL_V1.lock.json"
EVIDENCE = ROOT / "reports/model_v2/v2_014"
SYNTH_FINAL = "3f0b7762ae7e05f21eb1709521404ed4d7968cae34f89e1797a0cbabd47c70e4"
SYNTH_DIGEST = "e234b755f1d90eb9bc3d9ae4d437904d32b6e453dc476187238191cf409a352e"
GATEWAY = "25ec0eed4dc9e2b4603229243d538ee58d33bcd8f8fe88efac681e94eb06b11f"
FL_INIT = "6a2923ca87793fb78571b4cffad4026f8b4ce99d9dfcb3abe885e259c68a572f"


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=check)


def _blob_sha(target: str, path: str) -> str | None:
    shown = subprocess.run(["git", "show", f"{target}:{path}"], cwd=ROOT, capture_output=True)
    return hashlib.sha256(shown.stdout).hexdigest() if shown.returncode == 0 else None


def _sha_lines(rows: list[str]) -> str:
    return hashlib.sha256("\n".join(sorted(rows)).encode()).hexdigest()


def verify_clone_package(package: Path, lock: dict[str, Any], label: str) -> dict[str, Any]:
    manifest = json.loads((package / "evidence_manifest.json").read_text())
    mismatched = [name for name, digest in manifest["files"].items()
                  if not (package / name).exists() or hash_file(package / name) != digest]
    repro = json.loads((package / "reproducibility_manifest.json").read_text())
    target = repro["clone_target_sha"]
    ancestor = _git("merge-base", "--is-ancestor", target, "HEAD", check=False).returncode == 0
    changed_since_target = [p for p in lock["bound_artifacts"]
                            if _blob_sha(target, p) != hash_file(ROOT / p)]
    live_bound_drift = [p for p, h in lock["bound_artifacts"].items() if hash_file(ROOT / p) != h]
    statuses_ok = all(v in ("PASS", None) for v in repro["check_statuses"].values())
    deps = json.loads((package / "dependency_audit_python.json").read_text())
    fe = json.loads((package / "frontend_report.json").read_text())
    inventory = json.loads((package / "inventory.json").read_text())
    artifacts = json.loads((package / "artifacts.json").read_text())
    live_components = _sha_lines([f"{r['component']}|{hash_file(ROOT / r['lock_path'])}"
                                  for r in inventory["components"]])
    tracked_pt = sorted(p for p in _git("ls-files").stdout.splitlines() if p.endswith(".pt"))
    live_checkpoints = _sha_lines([f"{p}|{hash_file(ROOT / p)}" for p in tracked_pt])
    nodes_file = package / "regression.nodes.txt"
    current_nodes = set(line for line in subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:warnings"], cwd=ROOT,
        capture_output=True, text=True).stdout.splitlines() if "::" in line)
    clone_nodes = set(nodes_file.read_text().splitlines())
    regression = json.loads((package / "regression.json").read_text())
    synth = json.loads((package / "synthetic-fl.json").read_text())
    gateway = json.loads((package / "gateway.json").read_text())
    checks = {
        "manifest_file_hashes_all_match": not mismatched,
        "clone_result_PASS": repro["result"] == "PASS" and not repro["failed_checks"]
        and not repro["failed_steps"],
        "clone_label_and_mode": repro["label"] == label,
        "clone_target_is_ancestor_of_HEAD": ancestor,
        "method_files_unchanged_since_clone_target": not changed_since_target,
        "method_files_unchanged_at_HEAD": not live_bound_drift,
        "requirements_lock_hash_matches": deps["requirements_dev_lock_sha256"] == hash_file(
            ROOT / "requirements-dev.lock") == repro["requirements_lock_sha256"],
        "package_lock_hash_matches": fe["package_lock_sha256"] == hash_file(
            ROOT / "frontend/package-lock.json") == repro["package_lock_sha256"],
        "component_inventory_hash_matches_live": live_components == repro[
            "component_lock_inventory_sha256"],
        "checkpoint_inventory_hash_matches_live": live_checkpoints == repro[
            "checkpoint_inventory_sha256"] == artifacts["checkpoint_inventory_sha256"],
        "gateway_sha_matches": repro["gateway_canonical_sha256"] == gateway[
            "canonical_sha256"] == GATEWAY == hash_file(
                ROOT / "artifacts/deployment/MODEL_V2_GATEWAY_FP32.ts"),
        "fl_init_sha_matches": repro["FL_INIT_V2_sha256"] == FL_INIT,
        "synthetic_fl_final_and_digest": repro["v2_fl_005_final_state_sha256"] == SYNTH_FINAL
        == synth["final_state_sha256"] and repro["v2_fl_005_replay_digest"] == SYNTH_DIGEST,
        "regression_clean_and_node_list_subset_of_current": regression["status"] == "PASS"
        and regression["failed_tests"] == 0 and clone_nodes <= current_nodes,
        "regression_node_list_sha_matches_file": hashlib.sha256(
            "\n".join(nodes_file.read_text().splitlines()).encode()).hexdigest() == repro[
            "python_test_node_list_sha256"],
        "firewall_flags": not (repro["real_waveform_datasets_accessed"]
                               or repro["manual_source_copy"] or repro["manual_data_copy"]
                               or repro["manual_dependency_rescue"] or repro["CI_queried"]
                               or repro["CI_triggered"]),
        "all_check_statuses_PASS": statuses_ok,
        "frontend_PASS": fe["status"] == "PASS",
        "one_shot_guards_consumed": all(
            json.loads((ROOT / f"artifacts/{n}.json").read_text())["status"] == "COMPLETED"
            for n in ("V2_FL_INTERNAL_TEST_ACCESS_V1", "V2_FL_INCART_ACCESS_V1"))}
    return {"label": label, "target_sha": target, "checks": checks,
            "mismatched_files": mismatched, "changed_since_target": changed_since_target,
            "nodes_added_since_clone": len(current_nodes - clone_nodes),
            "status": "PASS" if all(checks.values()) else "FAIL"}


def verify() -> dict[str, Any]:
    lock = json.loads(LOCK.read_text())
    drift = [p for p, h in lock["bound_artifacts"].items() if hash_file(ROOT / p) != h]
    result: dict[str, Any] = {
        "lock": "artifacts/MODEL_V2_COMPLETE_REPRO_PROTOCOL_V1.lock.json",
        "lock_bound_files": len(lock["bound_artifacts"]), "lock_drift": drift,
        "packages": {}}
    ok = not drift
    for label in ("clone1", "clone2"):
        package = EVIDENCE / label
        if package.exists():
            try:
                result["packages"][label] = verify_clone_package(package, lock, label) if (
                    label == "clone1") else verify_final_package(package, lock)
            except Exception as exc:
                result["packages"][label] = {"status": "FAIL",
                                             "error": f"{type(exc).__name__}: {exc}"}
            ok &= result["packages"][label]["status"] == "PASS"
    result["evidence_present"] = sorted(result["packages"])
    result["status"] = "PASS" if ok else "FAIL"
    return result


def verify_final_package(package: Path, lock: dict[str, Any]) -> dict[str, Any]:
    manifest = json.loads((package / "evidence_manifest.json").read_text())
    mismatched = [name for name, digest in manifest["files"].items()
                  if not (package / name).exists() or hash_file(package / name) != digest]
    repro = json.loads((package / "reproducibility_manifest.json").read_text())
    ancestor = _git("merge-base", "--is-ancestor", repro["clone_target_sha"], "HEAD",
                    check=False).returncode == 0
    checks = {"manifest_file_hashes_all_match": not mismatched,
              "clone_result_PASS": repro["result"] == "PASS" and not repro["failed_checks"],
              "mode_final": repro["mode"] == "final", "target_is_ancestor_of_HEAD": ancestor,
              "firewall_flags": not (repro["real_waveform_datasets_accessed"]
                                     or repro["manual_source_copy"] or repro["manual_data_copy"]
                                     or repro["manual_dependency_rescue"])}
    return {"label": "clone2", "target_sha": repro["clone_target_sha"], "checks": checks,
            "mismatched_files": mismatched, "status": "PASS" if all(checks.values()) else "FAIL"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out")
    args = parser.parse_args()
    result = verify()
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": result["status"], "evidence_present": result["evidence_present"]}))
    if result["status"] != "PASS":
        sys.exit(1)


if __name__ == "__main__":
    main()
