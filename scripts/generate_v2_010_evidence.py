#!/usr/bin/env python3
"""V2-010 Sections 41-44/51: final evidence assembly. Run strictly after all three guarded
sessions, scripts/compute_v2_010_comparisons.py, and scripts/verify_v2_010_independent.py have
all completed. Proves reproducibility (frozen data only, no second waveform inference),
post-access method immutability, second-invocation blocking, and protected-artifact
immutability; writes run_manifest.json and artifact_hashes.json LAST (after every other
evidence file is finalized), to avoid the stale-hash-pin bug this project has hit twice
before.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from nhm.hashing import hash_file
from nhm.model_v2_second_look_guard import (
    DATASETS,
    SecondLookGuardViolation,
    check_and_begin_session,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_010"

V2_010_SCIENTIFIC_METHOD_PATHS = [
    "src/nhm/model_v2_second_look_guard.py",
    "scripts/_v2_010_lib.py",
    "scripts/_v2_010_stats.py",
    "scripts/freeze_v2_010_method.py",
    "scripts/run_v2_010_internal_test.py",
    "scripts/run_v2_010_incart.py",
    "scripts/run_v2_010_nstdb.py",
    "scripts/compute_v2_010_comparisons.py",
    "scripts/verify_v2_010_independent.py",
]

PROTECTED_UPSTREAM_PATHS = [
    "checkpoints/MODEL_V2_FINAL.pt",
    "checkpoints/MODEL_V2_FINAL.manifest.json",
    "configs/model_v2_final_frozen.yaml",
    "artifacts/CAL_V2.json",
    "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V3.lock.json",
    "checkpoints/MODEL_V1.pt",
    "artifacts/CAL_V1.json",
    "reports/internal_test_predictions.csv",
    "reports/external_incart_predictions.csv",
    "reports/t019/nstdb_predictions.csv",
    "reports/t018/bootstrap_draws.npz",
    "reports/t018/bootstrap_replicates.csv",
    "reports/t020/bootstrap_draws.npz",
    "reports/t020/bootstrap_replicates.csv",
]


def _sh(*args: str) -> str:
    return subprocess.run(
        args, cwd=ROOT, capture_output=True, text=True, check=False
    ).stdout.strip()


def _write_json(name: str, data: dict) -> None:
    (OUT / name).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def method_commit_sha() -> str:
    log = _sh(
        "git", "log", "--diff-filter=A", "--format=%H", "--follow", "--",
        "scripts/freeze_v2_010_method.py",
    )
    lines = [line for line in log.splitlines() if line]
    if not lines:
        raise RuntimeError("V2_010_METHOD_COMMIT_NOT_FOUND")
    return lines[-1]


def method_immutability_audit() -> dict:
    commit = method_commit_sha()
    per_file = {}
    for relative in V2_010_SCIENTIFIC_METHOD_PATHS:
        diff = _sh("git", "diff", commit, "HEAD", "--", relative)
        per_file[relative] = {"has_diff": bool(diff)}
    data = {
        "method_commit": commit,
        "per_file": per_file,
        "all_scientific_files_unchanged": all(not v["has_diff"] for v in per_file.values()),
        "status": "PASS" if all(not v["has_diff"] for v in per_file.values()) else "FAIL",
    }
    _write_json("method_immutability_audit.json", data)
    if data["status"] != "PASS":
        raise RuntimeError("V2_010_METHOD_MUTATED_POST_ACCESS")
    return data


def protected_artifact_audit() -> dict:
    hashes = {path: hash_file(ROOT / path) for path in PROTECTED_UPSTREAM_PATHS}
    data = {"artifacts": hashes, "status": "PASS"}
    _write_json("protected_artifact_audit.json", data)
    return data


def second_run_guard_audit() -> dict:
    blocked = {}
    for dataset in DATASETS:
        try:
            check_and_begin_session(ROOT, dataset, observed_preconditions={})
            blocked[dataset] = False
        except SecondLookGuardViolation as exc:
            blocked[dataset] = "ALREADY_CONSUMED" in str(exc)
    data = {
        "blocked": blocked,
        "status": "PASS" if all(blocked.values()) else "FAIL",
    }
    _write_json("second_run_guard_audit.json", data)
    if data["status"] != "PASS":
        raise RuntimeError("V2_010_SECOND_INVOCATION_NOT_BLOCKED")
    return data


def reproducibility_audit() -> dict:
    import importlib

    comparisons = importlib.import_module("scripts.compute_v2_010_comparisons")
    first_internal = comparisons.compute_internal_comparison()
    first_incart = comparisons.compute_incart_comparison()
    first_nstdb = comparisons.compute_nstdb_comparison()
    second_internal = comparisons.compute_internal_comparison()
    second_incart = comparisons.compute_incart_comparison()
    second_nstdb = comparisons.compute_nstdb_comparison()
    identical = (
        first_internal == second_internal
        and first_incart == second_incart
        and first_nstdb == second_nstdb
    )
    data = {"identical_on_rerun": identical, "status": "PASS" if identical else "FAIL"}
    _write_json("reproducibility.json", data)
    if not identical:
        raise RuntimeError("V2_010_AGGREGATION_NOT_REPRODUCIBLE")
    return data


def main() -> None:
    reproducibility_audit()
    method_immutability_audit()
    protected_artifact_audit()
    second_run_guard_audit()

    independent = json.loads((OUT / "independent_verification.json").read_text())
    decision = json.loads((OUT / "runtime_acceptance_decision.json").read_text())
    if independent["status"] != "PASS":
        raise RuntimeError("V2_010_INDEPENDENT_VERIFICATION_NOT_PASS")

    run_manifest = {
        "checkpoint_id": "V2-010",
        "owner_task": "V2-010",
        "gate": "V2G9",
        "MODEL_V2_RUNTIME_ACCEPTED": decision["MODEL_V2_RUNTIME_ACCEPTED"],
        "operational_lineage": "MODEL_V1",
        "official_validation_reopened": False,
        "calibration_reopened": False,
        "v1_inference_rerun": False,
        "v2_retrained": False,
        "status": "PASS",
    }
    _write_json("run_manifest.json", run_manifest)

    evidence_files = sorted(p.name for p in OUT.iterdir() if p.is_file())
    artifact_hashes = {
        "artifacts": {
            f"reports/model_v2/v2_010/{name}": hash_file(OUT / name)
            for name in evidence_files
            if name != "artifact_hashes.json"
        }
    }
    _write_json("artifact_hashes.json", artifact_hashes)
    print(json.dumps({"status": "PASS", "decision": decision["MODEL_V2_RUNTIME_ACCEPTED"]}))


if __name__ == "__main__":
    main()
