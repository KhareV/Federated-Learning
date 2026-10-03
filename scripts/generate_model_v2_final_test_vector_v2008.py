#!/usr/bin/env python3
"""V2-008 Section 16/17: generate the deterministic, no-patient-data synthetic fixed-vector
package for MODEL_V2_FINAL. Mirrors scripts/generate_model_v1_test_vector_t016.py's
deterministic-NPZ pattern exactly (fixed ZIP timestamps, sorted array names, ZIP_STORED) so
the fixture itself is byte-reproducible, not just numerically close. Predeclared generation:
VECTOR_0=all zeros, VECTOR_1=a fixed-formula analytic sinusoid (no RNG), VECTOR_2=fixed-seed
pseudorandom (numpy.random.default_rng, documented seed) -- exactly the three archetypes the
V2-008 prompt recommends, each reproducible from pure arithmetic/a documented seed, with no
real ECG waveform and no dataset-derived summary statistic.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import sys
import zipfile
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from models.model_v2_architectures import ModelV2TcnMean  # noqa: E402
from nhm.hashing import hash_file  # noqa: E402
from preprocessing.windowing import NORMALIZATION_EPSILON, normalize_window_zscore  # noqa: E402

TEST_VECTOR_ID = "MODEL_V2_FINAL_SYNTHETIC_TEST_VECTOR_V1"
FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
ANALYTIC_FREQUENCY_HZ = 1.0
ANALYTIC_SAMPLE_RATE_HZ = 250
PSEUDORANDOM_SEED = 20260927


def synthetic_raw_windows() -> np.ndarray:
    """Three nonconstant, patient-data-free vectors: all-zeros, a fixed-formula analytic
    sinusoid (deterministic, no RNG), and a fixed-seed pseudorandom vector."""
    index = np.arange(2500, dtype=np.float64)
    vector_0 = np.zeros(2500, dtype=np.float64)
    vector_1 = 100.0 * np.sin(
        2.0 * math.pi * ANALYTIC_FREQUENCY_HZ * index / ANALYTIC_SAMPLE_RATE_HZ
    )
    rng = np.random.default_rng(PSEUDORANDOM_SEED)
    vector_2 = rng.normal(loc=0.0, scale=50.0, size=2500)
    return np.stack([vector_0, vector_1, vector_2]).astype(np.float64)


def array_bytes(array: np.ndarray) -> bytes:
    stream = io.BytesIO()
    np.lib.format.write_array(stream, array, allow_pickle=False)
    return stream.getvalue()


def write_deterministic_npz(path: Path, arrays: dict[str, np.ndarray]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in sorted(arrays):
            info = zipfile.ZipInfo(f"{name}.npy", date_time=FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o600 << 16
            archive.writestr(info, array_bytes(arrays[name]))


def generate(root: Path, output: Path, checkpoint_path: Path, expected_sha: str) -> dict:
    checkpoint = root / checkpoint_path
    if hash_file(checkpoint) != expected_sha:
        raise RuntimeError("MODEL_V2_FINAL_CHECKPOINT_HASH_MISMATCH")
    payload = torch.load(checkpoint, map_location="cpu", weights_only=False)
    model = ModelV2TcnMean()
    model.load_state_dict(payload["state_dict"], strict=True)
    model.eval()
    raw = synthetic_raw_windows()
    normalized = np.stack(
        [normalize_window_zscore(row, epsilon=NORMALIZATION_EPSILON) for row in raw]
    ).astype(np.float32)
    normalized = normalized[:, None, :]
    with torch.inference_mode():
        logits = model(torch.from_numpy(normalized)).cpu().numpy().astype(np.float32)
    arrays = {
        "expected_logits_float32": logits,
        "normalized_inputs_float32": normalized,
        "raw_windows_float64": raw,
        "synthetic_ids_utf8": np.asarray(
            ["SYNTH_ALL_ZEROS_V1", "SYNTH_ANALYTIC_SINUSOID_V1", "SYNTH_FIXED_SEED_PRNG_V1"],
            dtype="S32",
        ),
    }
    write_deterministic_npz(output, arrays)
    return {"sha256": hash_file(output), "expected_logits": logits.tolist()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "tests/fixtures/model_v2_final_test_vector.npz"
    )
    parser.add_argument(
        "--checkpoint", type=Path,
        default=ROOT / "checkpoints/model_v2/v2_007_official_validation/"
        "V2-007-TCNMEAN-S20260927_best.pt",
    )
    parser.add_argument(
        "--expected-sha", default=(
            "89418edcc2c13f0edd9a36666bac560ad922dd4700b4b6dd19b56d067d4eff9b"
        ),
    )
    parser.add_argument("--metadata", type=Path)
    arguments = parser.parse_args()
    result = generate(ROOT, arguments.output, arguments.checkpoint, arguments.expected_sha)
    if arguments.metadata:
        metadata = {
            "test_vector_id": TEST_VECTOR_ID,
            "generator_version": "V2008_V1",
            "synthetic": True,
            "patient_data": False,
            "number_of_vectors": 3,
            "raw_shape": [3, 2500],
            "normalized_input_shape": [3, 1, 2500],
            "expected_logit_shape": [3, 1],
            "normalization_id": "PER_WINDOW_ZSCORE_V1",
            "normalization_epsilon": NORMALIZATION_EPSILON,
            "checkpoint_sha256": arguments.expected_sha,
            "expected_logit_dtype": "float32",
            "logit_tolerance_id": "MODEL_V2_FINAL_LOGIT_TOLERANCE_V1",
            "atol": 1e-7,
            "rtol": 1e-7,
            "npz_sha256": result["sha256"],
            "pseudorandom_seed": PSEUDORANDOM_SEED,
            "analytic_frequency_hz": ANALYTIC_FREQUENCY_HZ,
            "analytic_sample_rate_hz": ANALYTIC_SAMPLE_RATE_HZ,
        }
        arguments.metadata.parent.mkdir(parents=True, exist_ok=True)
        arguments.metadata.write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
