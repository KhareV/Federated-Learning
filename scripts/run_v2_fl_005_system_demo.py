#!/usr/bin/env python3
"""V2-FL-005 one-command ENGINEERING demo / canonical driver (WEARABLE_SIM_FL_SYSTEM_V1).

  python -m scripts.run_v2_fl_005_system_demo              cohort, 3 rounds, routing rejections,
                                                           SecAgg shadow, restart/resume
  python -m scripts.run_v2_fl_005_system_demo --preflight  cohort structural preflight only
  python -m scripts.run_v2_fl_005_system_demo --verify     two fresh-process runs + event replay
  python -m scripts.run_v2_fl_005_system_demo --canonical  verify + write reports/model_v2/v2_fl_005

Engineering only: no efficacy metric, no checkpoint, no real dataset access. Internal modes
(--full-run, --phase) are used for fresh-process execution."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from federated.wearable_fl_runner_v1 import (
    build_cohort,
    cohort_manifest,
    firewall_audit,
    run_digest,
    run_full,
    run_part1,
    run_part2,
    structural_coverage,
)
from federated.wearable_fl_system_v1 import replay_control_plane, state_spec_sha
from nhm.hashing import hash_bytes, hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_fl_005"
LOCK = ROOT / "artifacts/V2_FL_WEARABLE_SYSTEM_PROTOCOL_V1.lock.json"
MODULE = "scripts.run_v2_fl_005_system_demo"


def _write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def manifest_sha(manifest: dict[str, Any]) -> str:
    return hash_bytes(json.dumps(manifest, sort_keys=True).encode())


def preflight(target: Path | None) -> dict[str, Any]:
    profiles, datasets, _ = build_cohort()
    manifest = cohort_manifest(profiles, datasets)
    failed = structural_coverage(datasets)
    result = {
        "cohort_id": manifest["cohort_id"], "cohort_manifest_sha256": manifest_sha(manifest),
        "requirements": {"min_trainable": 32, "min_positive": 8, "min_negative": 8},
        "clients": {c["client_id"]: {**c["counts"], "dataset_sha256": c["dataset_sha256"]}
                    for c in manifest["clients"]},
        "participant_overlap": len({c["participant_id"] for c in manifest["clients"]}) != 8,
        "clients_failing_structural_coverage": failed,
        "model_outputs_inspected": False, "model_trained": False,
        "status": "PASS" if not failed else "FAIL"}
    if target is not None:
        _write(target / "cohort_preflight.json", result)
        _write(target / "cohort_manifest_candidate.json", manifest)
    return result


def _spawn(*args: str) -> None:
    subprocess.run([sys.executable, "-m", MODULE, *args], cwd=ROOT, check=True)


def full_run(directory: Path) -> dict[str, Any]:
    started = time.perf_counter()
    directory.mkdir(parents=True, exist_ok=True)
    profiles, datasets, manifest_map = build_cohort()
    manifest = cohort_manifest(profiles, datasets)
    cohort_sha = manifest_sha(manifest)
    continuous = run_full(datasets, manifest_map, shadow=True)
    resume = directory / "resume"
    _spawn("--phase", "part1", "--scratch", str(resume), "--json", str(directory / "part1.json"))
    _spawn("--phase", "part2", "--scratch", str(resume), "--json", str(directory / "part2.json"))
    part1 = json.loads((directory / "part1.json").read_text())
    part2 = json.loads((directory / "part2.json").read_text())
    report = continuous["report"]
    restart = {
        "resume_artifact_state_sha256": part1["resume"]["state_file_sha256"],
        "resume_artifact_coordinator_sha256": part1["resume"]["coordinator_json_sha256"],
        "fresh_process": part1["pid"] != part2["pid"] and part2["pid"] != os.getpid(),
        "resumed_from_round": part2["resumed_from_round"],
        "continuous_final_sha256": report["final_global_state_sha256"],
        "resumed_final_sha256": part2["final_global_state_sha256"],
        "round_2_state_matches_continuous": part1["global_state_sha256"]
        == report["state_progression"]["2"]["sha256"],
        "round_3_rejection_codes": [r["code"] for r in part2["round_3_rejections"]]}
    restart["exact_match"] = restart["continuous_final_sha256"] == restart["resumed_final_sha256"]
    for name in ("state.bin", "coordinator.json"):
        (resume / name).unlink(missing_ok=True)
    resume.rmdir()
    digest = run_digest(report, continuous["events"], restart)
    summary = {
        "cohort_manifest_sha256": cohort_sha,
        "dataset_sha256": {c: m["dataset_sha"] for c, m in manifest_map.items()},
        "report": report, "restart": restart, "semantic_digest": digest,
        "spec_sha256": state_spec_sha(continuous["state"]), "firewall": firewall_audit(),
        "wall_clock_seconds_not_in_digest": time.perf_counter() - started}
    _write(directory / "summary.json", summary)
    _write(directory / "events.json", continuous["events"])
    _write(directory / "cohort_manifest.json", manifest)
    return summary


def verify_lock() -> dict[str, Any]:
    if not LOCK.exists():
        sys.exit("V2_FL_WEARABLE_SYSTEM_PROTOCOL_V1 lock must exist before canonical execution")
    if not subprocess.run(["git", "log", "--format=%H", "-n", "1", "--",
                           "artifacts/V2_FL_WEARABLE_SYSTEM_PROTOCOL_V1.lock.json"], cwd=ROOT,
                          capture_output=True, text=True, check=True).stdout.strip():
        sys.exit("method lock must be COMMITTED before canonical execution")
    if subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True,
                      text=True, check=True).stdout.strip():
        sys.exit("working tree must be clean before canonical execution")
    lock = json.loads(LOCK.read_text())
    drift = [p for p, h in lock["bound_artifacts"].items() if hash_file(ROOT / p) != h]
    if drift:
        sys.exit(f"V2_FL_WEARABLE_SYSTEM_METHOD_DRIFT:{drift}")
    return lock


def _manifest_from(path: Path) -> dict[str, dict[str, Any]]:
    manifest = json.loads(path.read_text())
    return {c["client_id"]: {"participant_id": c["participant_id"], "session_id": c["session_id"],
                             "dataset_sha": c["dataset_sha256"]} for c in manifest["clients"]}


def verify(scratch: Path, evidence: Path | None) -> dict[str, Any]:
    runs = []
    for label in ("run_1", "run_2"):
        directory = scratch / label
        _spawn("--full-run", str(directory))
        runs.append(json.loads((directory / "summary.json").read_text()))
    one, two = runs
    events = json.loads((scratch / "run_1/events.json").read_text())
    replay = replay_control_plane(events, _manifest_from(scratch / "run_1/cohort_manifest.json"),
                                  one["spec_sha256"])
    update_hashes = [[r["report"]["rounds"][k]["update_sha256"] for k in ("1", "2", "3")]
                     for r in runs]
    flags = {
        "client_dataset_hashes_identical": one["dataset_sha256"] == two["dataset_sha256"],
        "update_hashes_identical_24": update_hashes[0] == update_hashes[1]
        and sum(len(x) for x in update_hashes[0]) == 24,
        "round_state_hashes_identical": one["report"]["state_progression"]
        == two["report"]["state_progression"],
        "rejection_outcomes_identical": [x["rejections"] for x in one["report"]["rounds"].values()]
        == [x["rejections"] for x in two["report"]["rounds"].values()],
        "final_sha_identical": one["report"]["final_global_state_sha256"]
        == two["report"]["final_global_state_sha256"],
        "semantic_digest_identical": one["semantic_digest"] == two["semantic_digest"],
        "restart_exact_match_both_runs": one["restart"]["exact_match"]
        and two["restart"]["exact_match"]}
    repro = {**flags, "run_1_semantic_digest": one["semantic_digest"],
             "run_2_semantic_digest": two["semantic_digest"], "real_dataset_access": False,
             "status": "PASS" if all(flags.values()) else "FAIL"}
    replay_result = {
        "event_count": len(events), "accepted_updates": replay["accepted"],
        "rejected_updates": replay["rejected"], "decision_mismatches": replay["mismatches"],
        "replayed_coordinator_identity": replay["identity"],
        "recorded_coordinator_identity": one["report"]["coordinator_identity"],
        "committed_rounds": replay["committed_rounds"],
        "waveforms_regenerated": False, "model_retrained": False,
        "status": "PASS" if replay["identity"] == one["report"]["coordinator_identity"]
        and not replay["mismatches"] else "FAIL"}
    result = {"runs": runs, "reproducibility": repro, "event_replay": replay_result}
    if evidence is not None:
        _write_evidence(evidence, result, events, scratch)
    return result


def _write_evidence(out: Path, result: dict[str, Any], events: list[dict[str, Any]],
                    scratch: Path) -> None:
    one = result["runs"][0]
    report = one["report"]
    _write(out / "federation_run.json", {
        "experiment_id": "WEARABLE_SIM_FL_SYSTEM_V1", "rounds": 3, "clients_per_round": 8,
        "expected_updates": 24,
        "accepted_updates": sum(r["accepted"] for r in report["rounds"].values()),
        "local_training_calls": sum(r["local_training_calls"] for r in report["rounds"].values()),
        "failed_updates": 0, "aggregation_failures": 0,
        "nonfinite_states": sum(not s["finite"] for s in report["state_progression"].values()),
        "rejected_injected_attempts": [r for rd in report["rounds"].values()
                                       for r in rd["rejections"]],
        "round_reports": report["rounds"], "state_progression": report["state_progression"],
        "scientific_model_fits_added": 0, "scientific_checkpoints_added": 0,
        "starts_from": "FL_INIT_V2", "validation_or_best_round_or_selection": False,
        "efficacy_metrics_computed": False})
    _write(out / "secagg_shadow.json", report["secagg_shadow"])
    _write(out / "restart_resume.json", one["restart"])
    _write(out / "reproducibility.json", result["reproducibility"])
    _write(out / "event_replay.json", result["event_replay"])
    _write(out / "finite_inference_smoke.json", report["inference_smoke"])
    _write(out / "semantic_replay_digest.json", {
        "replay_id": "WEARABLE_SIM_FL_SYSTEM_REPLAY_V1", "digest": one["semantic_digest"],
        "run_2_digest": result["runs"][1]["semantic_digest"],
        "excluded": ["wall-clock", "process IDs", "timings", "diagnostic losses/norms",
                     "cryptographic randomness"]})
    hits = [h for r in report["rounds"].values() for h in r["server_boundary_forbidden_hits"]]
    _write(out / "server_data_locality_audit.json", {
        "raw_ECG_visible": False, "PPG_visible": False, "SpO2_streams_visible": False,
        "labels_visible": False, "SimulationTruth_visible": False, "minibatches_visible": False,
        "observed_records_visible": False, "forbidden_hits": hits,
        "clear_model_updates_visible_on_plain_fedavg_path": True,
        "plain_fedavg_update_privacy_claimed": False,
        "server_receives": ["update envelopes (identity metadata, hashes, example counts)",
                            "model-state deltas"],
        "status": "PASS" if not hits else "FAIL"})
    _write(out / "firewall_audit.json", {
        **one["firewall"], "TRAIN": False, "VALIDATION": False, "CALIBRATION": False,
        "INTERNAL_TEST": False, "INCART": False, "NSTDB": False, "BIDMC": False,
        "WEARABLE_V1": False, "WEARABLE_SIM_V1": True,
        "status": "PASS" if not one["firewall"]["real_loader_modules_imported"] else "FAIL"})
    _write(out / "cohort_manifest_run.json",
           json.loads((scratch / "run_1/cohort_manifest.json").read_text()))
    _write(out / "events.json", events)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--canonical", action="store_true")
    parser.add_argument("--full-run", metavar="DIR")
    parser.add_argument("--phase", choices=("part1", "part2"))
    parser.add_argument("--scratch")
    parser.add_argument("--json")
    args = parser.parse_args()
    if args.phase:
        profiles, datasets, manifest_map = build_cohort()
        cohort_sha = manifest_sha(cohort_manifest(profiles, datasets))
        runner = run_part1 if args.phase == "part1" else run_part2
        _write(Path(args.json), runner(datasets, manifest_map, Path(args.scratch), cohort_sha))
        return
    if args.full_run:
        full_run(Path(args.full_run))
        return
    if args.preflight:
        print(json.dumps(preflight(OUT), indent=2)[:4000])
        return
    if args.canonical:
        verify_lock()
        with tempfile.TemporaryDirectory(prefix="v2_fl_005_") as scratch:
            result = verify(Path(scratch), OUT)
        print(json.dumps({"reproducibility": result["reproducibility"]["status"],
                          "event_replay": result["event_replay"]["status"]}, indent=2))
        return
    with tempfile.TemporaryDirectory(prefix="v2_fl_005_demo_") as scratch:
        if args.verify:
            result = verify(Path(scratch), None)
            print(json.dumps({"reproducibility": result["reproducibility"]["status"],
                              "event_replay": result["event_replay"]["status"]}, indent=2))
        else:
            summary = full_run(Path(scratch))
            print(json.dumps({
                "final_global_state_sha256": summary["report"]["final_global_state_sha256"],
                "semantic_digest": summary["semantic_digest"],
                "restart_exact_match": summary["restart"]["exact_match"],
                "secagg_shadow": summary["report"]["secagg_shadow"]["status"]}, indent=2))


if __name__ == "__main__":
    main()
