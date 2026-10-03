#!/usr/bin/env python3
"""V2-012: assemble the additive GATEWAY_ARTIFACT_V2 manifest (FROZEN_RESEARCH_GATEWAY) from the
already-frozen export, parity and benchmark evidence. Pure assembly; every value is read back
from files written by the exporter/benchmark."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import yaml

from deployment import gateway_v2 as gw
from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_012"
REPORT = "reports/model_v2/v2_012"


def method_commit() -> str:
    log = subprocess.run(
        ["git", "log", "--diff-filter=A", "--format=%H", "--", "scripts/freeze_v2_012_method.py"],
        cwd=ROOT, capture_output=True, text=True, check=False).stdout.split()
    if not log:
        raise RuntimeError("V2_012_METHOD_COMMIT_NOT_FOUND")
    return log[-1]


def _j(rel: str) -> dict:
    return json.loads((ROOT / rel).read_text())


def main() -> None:
    cfg = yaml.safe_load((ROOT / "configs/model_v2/gateway_artifact_v2.yaml").read_text())
    export = _j(f"{REPORT}/export_audit.json")
    fixture = _j(f"{REPORT}/canonical_fixture_parity.json")
    corpus = _j(f"{REPORT}/synthetic_corpus_parity_summary.json")
    bench = _j(f"{REPORT}/benchmark_summary.json")
    memory = _j(f"{REPORT}/memory_benchmark.json")
    repro = _j(f"{REPORT}/artifact_reproducibility.json")
    model_manifest = _j("checkpoints/MODEL_V2_FINAL.manifest.json")
    from scripts.freeze_v2_012_method import METHOD_PATHS

    artifact = ROOT / gw.ARTIFACT_PATH
    canonical = bench["canonical"]
    manifest = {
        "artifact_id": gw.ARTIFACT_ID,
        "deployment_artifact_id": gw.DEPLOYMENT_ARTIFACT_ID,
        "status": gw.FROZEN_STATUS,
        "owner_task": "V2-012",
        "description": "research-only frozen V2 CPU gateway artifact",
        "artifact": {
            "path": gw.ARTIFACT_PATH, "sha256": hash_file(artifact),
            "bytes": artifact.stat().st_size, "format": gw.FORMAT, "precision": gw.PRECISION,
            "torch_version": export["torch_version"], "byte_reproducible": repro[
                "byte_reproducible"], "semantic_reproducibility": repro["semantic_reproducibility"],
        },
        "source_model": {
            "id": gw.MODEL_ID, "path": "checkpoints/MODEL_V2_FINAL.pt",
            "sha256": hash_file(ROOT / "checkpoints/MODEL_V2_FINAL.pt"),
            "bytes": (ROOT / "checkpoints/MODEL_V2_FINAL.pt").stat().st_size,
            "manifest_sha256": hash_file(ROOT / "checkpoints/MODEL_V2_FINAL.manifest.json"),
            "config_sha256": hash_file(ROOT / "configs/model_v2_final_frozen.yaml"),
            "architecture_id": model_manifest["architecture_id"],
            "parameter_count": model_manifest["parameter_count"],
        },
        "gateway_parameter_count": export["trainable_parameter_count"],
        "input_shape": ["N", 1, gw.WINDOW_SAMPLES],
        "input_dtype": "float32",
        "input_contract": gw.INPUT_ID,
        "output_semantics": gw.OUTPUT_SEMANTICS,
        "calibration": {"id": gw.CALIBRATION_ID, "path": "artifacts/CAL_V2.json",
                        "sha256": hash_file(ROOT / "artifacts/CAL_V2.json"),
                        "applied_by": "wrapper (canonical helpers); not baked into weights"},
        "preprocessing": {"id": "PREPROC_V1", "lock_sha256": hash_file(
            ROOT / "manifests/preprocessing/PREPROC_V1.lock.json")},
        "target_id": model_manifest["target_id"],
        "map_id": model_manifest["label_map_id"],
        "protocol_v3_lock_sha256": hash_file(
            ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V3.lock.json"),
        "parity_corpus": {
            "id": gw.CORPUS_ID, "path": gw.PARITY_CORPUS_PATH,
            "sha256": hash_file(ROOT / gw.PARITY_CORPUS_PATH),
            "windows_content_sha256": cfg["parity_corpus"]["windows_content_sha256"],
            "rows": gw.CORPUS_ROWS,
        },
        "equivalence": {"atol": gw.ATOL, "rtol": gw.RTOL, "comparison_batch_size": 1},
        "fixture_parity": {
            "rows": fixture["rows"], "allclose": fixture["allclose"],
            "max_abs_logit_delta": fixture["native_vs_gateway"]["max_abs_delta"],
            "file_sha256": hash_file(OUT / "canonical_fixture_parity.json"),
        },
        "synthetic_corpus_parity": {
            "rows": corpus["rows"], "allclose": corpus["allclose"],
            "max_abs_logit_delta": corpus["max_abs_logit_delta"],
            "max_rel_logit_delta": corpus["max_rel_logit_delta"],
            "max_raw_probability_delta": corpus["max_raw_probability_delta"],
            "max_calibrated_probability_delta": corpus["max_calibrated_probability_delta"],
            "threshold_decision_disagreements": corpus["threshold_decision_disagreements"],
            "summary_sha256": hash_file(OUT / "synthetic_corpus_parity_summary.json"),
            "csv_sha256": hash_file(OUT / "synthetic_corpus_parity.csv"),
        },
        "benchmark": {
            "config_sha256": hash_file(ROOT / "configs/model_v2/gateway_artifact_v2.yaml"),
            "summary_sha256": hash_file(OUT / "benchmark_summary.json"),
            "memory_sha256": hash_file(OUT / "memory_benchmark.json"),
            "warmup": gw.WARMUP, "measured_per_run": gw.MEASURED, "repetitions": gw.REPETITIONS,
            "aggregation_rule": canonical["aggregation_rule"],
            "canonical_p50_ms": canonical["canonical_p50_ms"],
            "canonical_p95_ms": canonical["canonical_p95_ms"],
            "canonical_throughput_windows_per_second": canonical[
                "canonical_throughput_windows_per_second"],
            "peak_high_water_process_RSS_bytes": canonical["peak_high_water_process_RSS_bytes"],
            "memory_semantics": memory["semantics"],
            "host": bench["host"],
        },
        "int8": "NOT_EVALUATED",
        "status_semantics": {
            "MODEL_V2_RUNTIME_ACCEPTED": "ACCEPTED",
            "official_validation_promotion": "MODEL_V2_NOT_PROMOTED_RELEASE_CI",
            "operational_lineage": "MODEL_V1",
        },
        "method_commit": method_commit(),
        "bound_method_artifacts": {p: hash_file(ROOT / p) for p in METHOD_PATHS},
    }
    path = ROOT / gw.MANIFEST_PATH
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("GATEWAY_ARTIFACT_V2 manifest written", manifest["artifact"]["sha256"])


if __name__ == "__main__":
    main()
