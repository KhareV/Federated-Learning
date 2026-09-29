#!/usr/bin/env python3
"""Generate T013/F06 aggregate provenance without rewriting T011/T012 history."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from evaluation.leakage_audit import verify_frozen_split  # noqa: E402
from nhm.hashing import hash_file  # noqa: E402
from nhm.run_manifest import (  # noqa: E402
    artifact_record,
    create_run_manifest,
    write_run_manifest,
)
from preprocessing.freeze import verify_preproc_freeze  # noqa: E402
from preprocessing.mitdb_windows import verify_cache_manifest  # noqa: E402


def read_json(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def write_json(relative: str, value: dict) -> Path:
    path = ROOT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path


def main() -> None:
    verify_frozen_split(ROOT)
    lock_verification = verify_preproc_freeze(ROOT)
    cache_verification = verify_cache_manifest(
        ROOT, hash_file(ROOT / "manifests/preprocessing/PREPROC_V1.lock.json")
    )
    if cache_verification["status"] != "PASS":
        raise RuntimeError(f"cache verification failed: {cache_verification}")

    components = {
        "T011_resampler": {
            "path": "reports/preprocessing/resampler_causality.json",
            "status": read_json("reports/preprocessing/resampler_causality.json")[
                "overall_status"
            ],
        },
        "T012_filters": {
            "path": "reports/preprocessing/filter_causality.json",
            "status": read_json("reports/preprocessing/filter_causality.json")["overall_status"],
        },
        "T012_gap_policy": {
            "path": "reports/preprocessing/gap_tests.json",
            "status": read_json("reports/preprocessing/gap_tests.json")["overall_status"],
        },
        "T013_windows": {
            "path": "reports/preprocessing/window_tests.json",
            "status": read_json("reports/preprocessing/window_tests.json")["overall_status"],
        },
        "T013_quality": {
            "path": "reports/preprocessing/quality_tests.json",
            "status": read_json("reports/preprocessing/quality_tests.json")["overall_status"],
        },
        "T013_synchronization": {
            "path": "reports/preprocessing/sync_tests.json",
            "status": read_json("reports/preprocessing/sync_tests.json")["overall_status"],
        },
        "T013_real_window_audit": {
            "path": "reports/t013/real_window_audit.json",
            "status": read_json("reports/t013/real_window_audit.json")["overall_status"],
        },
        "F06_lock": {
            "path": "manifests/preprocessing/PREPROC_V1.lock.json",
            "status": lock_verification["status"],
        },
        "cache_staleness_guard": {
            "path": "manifests/windows/MITDB_WINDOWS_V1.cache.csv",
            "status": cache_verification["status"],
        },
    }
    overall = "PASS" if all(value["status"] == "PASS" for value in components.values()) else "FAIL"
    aggregate = {
        "gate_id": "G6",
        "preproc_id": "PREPROC_V1",
        "upstream_evidence_policy": "REFERENCED_BY_SHA256_NOT_REGENERATED_BY_T013",
        "components": {
            name: {
                **value,
                "sha256": hash_file(ROOT / value["path"]),
            }
            for name, value in components.items()
        },
        "scope": {
            "real_mitdb_evidence": ["window build", "labels", "leakage audit"],
            "synthetic_fixture_evidence": ["gap propagation", "quality hard failures"],
            "generic_sync_fixture_evidence": True,
            "hardware_validation": "NOT_PERFORMED_T004_BLOCKED_HARDWARE",
            "wearable_validation": "NOT_PERFORMED_G16_OPEN",
        },
        "overall_status": overall,
    }
    if overall != "PASS":
        raise RuntimeError(f"G6 aggregate failure: {components}")
    aggregate_path = write_json("reports/preprocessing/causality_tests.json", aggregate)

    inputs = [
        ROOT / "manifests/splits/MITDB_SPLIT_V1.lock.json",
        ROOT / "manifests/labels/AAMI_SVF_MAP_V1.yaml",
        ROOT / "reports/preprocessing/resampler_causality.json",
        ROOT / "reports/preprocessing/filter_causality.json",
        ROOT / "reports/preprocessing/gap_tests.json",
    ]
    outputs = [
        ROOT / "manifests/windows/MITDB_WINDOWS_V1.csv",
        ROOT / "manifests/windows/MITDB_WINDOWS_V1.cache.csv",
        ROOT / "manifests/preprocessing/PREPROC_V1.lock.json",
        ROOT / "reports/preprocessing/window_tests.json",
        ROOT / "reports/preprocessing/quality_tests.json",
        ROOT / "reports/preprocessing/sync_tests.json",
        aggregate_path,
        ROOT / "reports/t013/window_distribution.json",
        ROOT / "reports/t013/real_window_audit.json",
        ROOT / "reports/t013/preproc_freeze_audit.json",
    ]
    manifest = create_run_manifest(
        ROOT,
        run_id="T013-WINDOWING-QUALITY-SYNC-PREPROC-V1",
        phase_id="T013",
        task_id="T013",
        config_path=ROOT / "configs/preproc_v1.yaml",
        dependency_snapshot_path=ROOT / "reports/t001/dependencies.txt",
        input_artifacts=[artifact_record(path, ROOT) for path in inputs],
        output_artifacts=[artifact_record(path, ROOT) for path in outputs],
        notes=(
            "Partition-first real MITDB window construction after frozen MITDB_SPLIT_V1; "
            "QUALITY_V1 was hashed before held-out construction and remained unchanged. "
            "No model training/evaluation. T011/T012 evidence was referenced, not regenerated. "
            "Hardware timing/clipping semantics remain VERIFICATION_REQUIRED_T004."
        ),
    )
    run_manifest = ROOT / "reports/t013/run_manifest.json"
    write_run_manifest(manifest, run_manifest, ROOT / "contracts/run_manifest_v1.schema.json")

    hash_paths = [
        ROOT / "preprocessing/windowing.py",
        ROOT / "preprocessing/sync.py",
        ROOT / "preprocessing/quality.py",
        ROOT / "preprocessing/mitdb_windows.py",
        ROOT / "configs/preproc_v1.yaml",
        ROOT / "configs/quality_v1.yaml",
        *outputs,
        run_manifest,
    ]
    artifact_hashes = {
        "manifest_version": "1.0",
        "algorithm": "sha256",
        "rule": "exact file bytes; this manifest excludes itself to avoid a circular digest",
        "artifacts": {
            str(path.relative_to(ROOT)): hash_file(path) for path in sorted(set(hash_paths))
        },
        "upstream_frozen_hashes": {
            str(path.relative_to(ROOT)): hash_file(path) for path in inputs[:2]
        },
    }
    write_json("reports/t013/artifact_hashes.json", artifact_hashes)
    print("T013 evidence: PASS")


if __name__ == "__main__":
    main()
