#!/usr/bin/env python3
"""V2-012 method freeze (run BEFORE METHOD_COMMIT): verify the frozen config/corpus/identities,
write the parity-corpus manifest and the benchmark config, and record the method-file hashes.
No export, no benchmark, no artifact."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import yaml

from deployment import gateway_v2 as gw
from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_012"

METHOD_PATHS = [
    "configs/model_v2/gateway_artifact_v2.yaml",
    "deployment/gateway_v2.py",
    "models/gateway_artifact_v2_verify.py",
    "scripts/freeze_v2_012_method.py",
    "scripts/export_gateway_v2.py",
    "scripts/run_gateway_v2_benchmark.py",
    "scripts/build_gateway_manifest_v2.py",
    "tests/fixtures/gateway_parity_corpus_v2_v1.npz",
    "reports/model_v2/v2_012/parity_corpus_manifest.json",
    "reports/model_v2/v2_012/benchmark_config.json",
    "deployment/benchmark.py",
    "deployment/runtime.py",
]


def main() -> None:
    cfg = yaml.safe_load((ROOT / "configs/model_v2/gateway_artifact_v2.yaml").read_text())
    live = {
        "checkpoint": hash_file(ROOT / "checkpoints/MODEL_V2_FINAL.pt"),
        "manifest": hash_file(ROOT / "checkpoints/MODEL_V2_FINAL.manifest.json"),
        "frozen_config": hash_file(ROOT / "configs/model_v2_final_frozen.yaml"),
        "cal": hash_file(ROOT / "artifacts/CAL_V2.json"),
        "preproc": hash_file(ROOT / "manifests/preprocessing/PREPROC_V1.lock.json"),
        "protocol": hash_file(ROOT / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V3.lock.json"),
        "fixture": hash_file(ROOT / "tests/fixtures/model_v2_final_test_vector.npz"),
        "corpus_npz": hash_file(ROOT / gw.PARITY_CORPUS_PATH),
        "v1_artifact": hash_file(ROOT / "artifacts/deployment/MODEL_V1_GATEWAY_FP32.ts"),
    }
    bindings = {
        "checkpoint": cfg["source_model"]["checkpoint_sha256"],
        "manifest": cfg["source_model"]["manifest_sha256"],
        "frozen_config": cfg["source_model"]["frozen_config_sha256"],
        "cal": cfg["calibration"]["sha256"],
        "preproc": cfg["preprocessing"]["lock_sha256"],
        "protocol": cfg["protocol_v3_lock_sha256"],
        "fixture": cfg["canonical_fixture"]["sha256"],
        "corpus_npz": cfg["parity_corpus"]["npz_sha256"],
        "v1_artifact": cfg["matched_v1_comparison"]["v1_artifact_sha256"],
    }
    mismatched = [k for k in live if live[k] != bindings[k]]
    if mismatched:
        raise RuntimeError(f"V2_012_CONFIG_BINDING_MISMATCH:{mismatched}")

    windows = gw.load_parity_corpus(ROOT)
    regenerated = gw.generate_parity_corpus()
    deterministic = bool(np.array_equal(windows, regenerated)
                         and np.array_equal(regenerated, gw.generate_parity_corpus()))
    edge = windows[:8, 0, :]
    corpus_manifest = {
        "corpus_id": gw.CORPUS_ID,
        "path": gw.PARITY_CORPUS_PATH,
        "npz_sha256": live["corpus_npz"],
        "windows_content_sha256": gw.corpus_content_sha256(windows),
        "rows": int(windows.shape[0]),
        "stored_shape": list(windows.shape),
        "window_shape": [1, gw.WINDOW_SAMPLES],
        "dtype": str(windows.dtype),
        "generator": "numpy.random.Generator(PCG64)",
        "seed": gw.CORPUS_SEED,
        "purpose": "engineering conversion equivalence only; no patient data; no labels",
        "scientific_metrics_reported": False,
        "frozen_before_deployment_output_inspection": True,
        "deterministic_regeneration_identical": deterministic,
        "edge_fixture_checks": {
            "zeros": bool(np.all(edge[0] == 0)),
            "plus_one": bool(np.all(edge[1] == 1)),
            "minus_one": bool(np.all(edge[2] == -1)),
            "linear_up": bool(edge[3][0] == np.float32(-3) and edge[3][-1] == np.float32(3)),
            "linear_down": bool(edge[4][0] == np.float32(3) and edge[4][-1] == np.float32(-3)),
            "impulse_single_nonzero": int(np.count_nonzero(edge[7])) == 1
            and bool(edge[7][1250] == np.float32(1.0)),
        },
        "random_rows_within_clip": bool(np.abs(windows[8:]).max() <= gw.CLIP),
        "all_finite": bool(np.isfinite(windows).all()),
        "status": "PASS" if deterministic else "FAIL",
    }
    edge_ok = all(corpus_manifest["edge_fixture_checks"].values())
    if corpus_manifest["status"] != "PASS" or not edge_ok:
        raise RuntimeError("V2_012_PARITY_CORPUS_INVALID")
    (OUT / "parity_corpus_manifest.json").write_text(
        json.dumps(corpus_manifest, indent=2, sort_keys=True) + "\n")
    bench = cfg["benchmark"]
    (OUT / "benchmark_config.json").write_text(json.dumps({
        "config_path": "configs/model_v2/gateway_artifact_v2.yaml",
        "config_sha256": hash_file(ROOT / "configs/model_v2/gateway_artifact_v2.yaml"),
        "device": bench["device"], "batch_size": bench["batch_size"],
        "input_shape": bench["input_shape"], "warmup_count": bench["warmup_count"],
        "measured_count_per_run": bench["measured_count_per_run"],
        "repetitions": bench["repetitions"], "clock": bench["clock"],
        "aggregation": bench["aggregation"], "threads": {"intraop": 1, "interop": 1},
        "memory": cfg["memory"], "boundary": bench["boundary"],
        "excluded_from_timing": bench["excluded_from_timing"],
        "inputs": bench["inputs"], "matched_v1_comparison": cfg["matched_v1_comparison"],
        "frozen_before_any_measurement": True, "observed_results_included": False,
    }, indent=2, sort_keys=True) + "\n")

    artifact_absent = not (ROOT / gw.ARTIFACT_PATH).exists() and not (
        ROOT / gw.MANIFEST_PATH).exists()
    no_results = not any((OUT / n).exists() for n in (
        "export_audit.json", "benchmark_summary.json", "benchmark_runs.csv",
        "synthetic_corpus_parity.csv"))
    (OUT / "method_freeze.json").write_text(json.dumps({
        "owner_task": "V2-012",
        "method_artifact_sha256": {p: hash_file(ROOT / p) for p in METHOD_PATHS
                                   if p != "reports/model_v2/v2_012/method_freeze.json"},
        "config_bindings_verified": True,
        "format": gw.FORMAT, "precision": gw.PRECISION, "tolerance": {"atol": gw.ATOL,
                                                                       "rtol": gw.RTOL},
        "warmup": gw.WARMUP, "measured_per_run": gw.MEASURED, "repetitions": gw.REPETITIONS,
        "gateway_artifact_absent_at_freeze": artifact_absent,
        "benchmark_or_export_result_absent_at_freeze": no_results,
        "v2_012_registry_status_at_freeze": "NOT_STARTED",
        "operational_lineage": "MODEL_V1",
        "status": "PASS" if (artifact_absent and no_results) else "FAIL",
    }, indent=2, sort_keys=True) + "\n")
    print("V2-012 method freeze complete")


if __name__ == "__main__":
    main()
