#!/usr/bin/env python3
"""Generate byte-deterministic synthetic MODEL_V1 inference vectors."""

from __future__ import annotations

import argparse
import io
import json
import sys
import zipfile
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from models.ecg_cnn import build_model_v1  # noqa: E402
from nhm.hashing import hash_file  # noqa: E402
from preprocessing.windowing import normalize_window_zscore  # noqa: E402

TEST_VECTOR_ID = "MODEL_V1_SYNTHETIC_TEST_VECTOR_V1"
EXPECTED_CHECKPOINT_SHA = "021352eb067932015b657f0570ac155f8ef00af2d43864e13a110d0252bc7bfe"
FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


def synthetic_raw_windows() -> np.ndarray:
    """Three nonconstant vectors built only from exact integer arithmetic."""
    index = np.arange(2500, dtype=np.int64)
    first = (index % 101) - 50
    second = ((index * 17) % 211) - 105 + ((index % 250) == 0) * 180
    third = ((index // 25) % 2) * 80 - 40 + ((index * 7) % 31) - 15
    return np.stack([first, second, third]).astype(np.float64)


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


def generate(root: Path, output: Path) -> dict[str, object]:
    checkpoint = root / "checkpoints/MODEL_V1.pt"
    if hash_file(checkpoint) != EXPECTED_CHECKPOINT_SHA:
        raise RuntimeError("MODEL_CHECKPOINT_HASH_MISMATCH")
    payload = torch.load(checkpoint, map_location="cpu", weights_only=True)
    model = build_model_v1()
    model.load_state_dict(payload["state_dict"], strict=True)
    model.eval()
    raw = synthetic_raw_windows()
    normalized = np.stack([normalize_window_zscore(row) for row in raw]).astype(np.float32)
    normalized = normalized[:, None, :]
    with torch.inference_mode():
        logits = model(torch.from_numpy(normalized)).cpu().numpy().astype(np.float32)
    arrays = {
        "expected_logits_float32": logits,
        "normalized_inputs_float32": normalized,
        "raw_windows_float64": raw,
        "synthetic_ids_utf8": np.asarray(
            ["SYNTH_INTEGER_SAW_V1", "SYNTH_PULSE_MOD_V1", "SYNTH_STEP_MOD_V1"],
            dtype="S24",
        ),
    }
    write_deterministic_npz(output, arrays)
    return {"sha256": hash_file(output), "expected_logits": logits.tolist()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=ROOT / "tests/fixtures/model_v1_test_vector.npz"
    )
    parser.add_argument("--metadata", type=Path)
    arguments = parser.parse_args()
    result = generate(ROOT, arguments.output)
    if arguments.metadata:
        metadata = {
            "test_vector_id": TEST_VECTOR_ID,
            "generator_version": "T016_V1",
            "synthetic": True,
            "patient_data": False,
            "number_of_vectors": 3,
            "raw_shape": [3, 2500],
            "normalized_input_shape": [3, 1, 2500],
            "expected_logit_shape": [3, 1],
            "normalization_id": "PER_WINDOW_ZSCORE_V1",
            "normalization_epsilon": 1e-8,
            "checkpoint_sha256": EXPECTED_CHECKPOINT_SHA,
            "expected_logit_dtype": "float32",
            "logit_tolerance_id": "MODEL_V1_LOGIT_TOLERANCE_V1",
            "atol": 1e-6,
            "rtol": 1e-6,
            "npz_sha256": result["sha256"],
        }
        arguments.metadata.parent.mkdir(parents=True, exist_ok=True)
        arguments.metadata.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
