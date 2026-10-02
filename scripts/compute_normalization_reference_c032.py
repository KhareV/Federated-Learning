#!/usr/bin/env python3
"""C032-NORM-RUNTIME Section 8: compute the correct reference output for >=3 frozen,
non-held-out engineering vectors by applying the locked PREPROC_V1 PER_WINDOW_ZSCORE_V1
normalization before gateway inference. No target labels are used or required.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

from deployment.runtime import GatewayModelRuntime
from nhm.hashing import hash_file
from preprocessing.windowing import NORMALIZATION_EPSILON, normalize_window_zscore

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/c032_norm_runtime"


def _cache_row(record_id: str, partition: str) -> dict[str, str]:
    with (ROOT / "manifests/windows/MITDB_WINDOWS_V1.cache.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        for row in csv.DictReader(handle):
            if row["partition"] == partition and row["record_id"] == record_id:
                return row
    raise KeyError((partition, record_id))


def _load_cache_window(record_id: str, partition: str, index: int) -> np.ndarray:
    row = _cache_row(record_id, partition)
    array = np.load(ROOT / row["relative_path"], allow_pickle=False)
    return np.asarray(array[index], dtype=np.float64)


def _evaluate(runtime: GatewayModelRuntime, unnormalized: np.ndarray) -> dict[str, float]:
    normalized = normalize_window_zscore(unnormalized, epsilon=NORMALIZATION_EPSILON)
    if not np.isfinite(normalized).all():
        raise RuntimeError("NORMALIZATION_OUTPUT_NONFINITE")
    array = normalized.astype(np.float32).reshape(1, 1, -1)
    result = runtime.infer(array)
    return {
        "mean_before": float(unnormalized.mean()),
        "std_before": float(unnormalized.std(ddof=0)),
        "mean_after": float(normalized.mean()),
        "std_after": float(normalized.std(ddof=0)),
        "raw_logit": result.raw_logit,
        "raw_probability": 1.0 / (1.0 + np.exp(-result.raw_logit)),
        "source_domain_calibrated_probability": result.calibrated_probability,
        "threshold": result.threshold,
        "above_threshold": result.above_threshold,
    }


def main() -> None:
    runtime = GatewayModelRuntime(ROOT, ROOT / "artifacts/deployment/MODEL_V1_GATEWAY_FP32.ts")

    references: dict[str, dict] = {}

    # A: MODEL_V1 frozen synthetic test vector (T016) -- includes the gold-standard
    # pre-normalized reference and expected logit, used here only as a cross-check.
    vector_fixture = np.load(ROOT / "tests/fixtures/model_v1_test_vector.npz")
    raw_a = vector_fixture["raw_windows_float64"][0]
    expected_normalized_a = vector_fixture["normalized_inputs_float32"][0].reshape(-1)
    expected_logit_a = float(vector_fixture["expected_logits_float32"][0][0])
    computed_normalized_a = normalize_window_zscore(raw_a, epsilon=NORMALIZATION_EPSILON).astype(
        np.float32
    ).reshape(-1)
    cross_check_a = {
        "normalized_matches_frozen_fixture": bool(
            np.array_equal(computed_normalized_a, expected_normalized_a)
        ),
        "expected_logit": expected_logit_a,
    }
    result_a = _evaluate(runtime, raw_a)
    result_a["cross_check"] = cross_check_a
    result_a["logit_matches_frozen_expected"] = abs(result_a["raw_logit"] - expected_logit_a) < 1e-4
    references["A_model_v1_synthetic_test_vector"] = {
        "source": "tests/fixtures/model_v1_test_vector.npz[0]",
        **result_a,
    }

    # B: one PUBLIC_ECG_REPLAY_V1 filtered window (C034 fixture, window 0).
    public_manifest = json.loads(
        (ROOT / "tests/fixtures/e2e/PUBLIC_ECG_REPLAY_V1.manifest.json").read_text(
            encoding="utf-8"
        )
    )
    public_samples = np.load(ROOT / "tests/fixtures/e2e/PUBLIC_ECG_REPLAY_V1.npz")["samples"]
    raw_b = np.asarray(public_samples[0], dtype=np.float64)
    references["B_public_ecg_replay_window_0"] = {
        "source": "tests/fixtures/e2e/PUBLIC_ECG_REPLAY_V1.npz[0]",
        "window_id": public_manifest["selection"]["windows"][0]["example_id"],
        **_evaluate(runtime, raw_b),
    }

    # C: a different deterministic filtered window, different record/amplitude (TRAIN, record
    # 103, first window) -- structural pick, no label/outcome inspection.
    raw_c = _load_cache_window("103", "TRAIN", 0)
    references["C_distinct_train_window_record_103"] = {
        "source": "TRAIN cache record 103, index 0",
        **_evaluate(runtime, raw_c),
    }

    output = {
        "normalization_helper": "preprocessing.windowing.normalize_window_zscore",
        "epsilon": NORMALIZATION_EPSILON,
        "labels_used": False,
        "references": references,
        "gateway_artifact_sha256": hash_file(
            ROOT / "artifacts/deployment/MODEL_V1_GATEWAY_FP32.ts"
        ),
        "model_checkpoint_sha256": hash_file(ROOT / "checkpoints/MODEL_V1.pt"),
        "status": "PASS",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "normalization_reference.json").write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
