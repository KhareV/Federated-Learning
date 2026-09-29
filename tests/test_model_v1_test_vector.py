from __future__ import annotations

import ast
import tempfile
from pathlib import Path

import numpy as np
import torch

from models.ecg_cnn import build_model_v1
from nhm.hashing import hash_file
from preprocessing.windowing import normalize_window_zscore
from scripts.generate_model_v1_test_vector_t016 import generate, synthetic_raw_windows

ROOT = Path(__file__).resolve().parents[1]


def test_test_vector_is_synthetic_normalized_and_byte_reproducible() -> None:
    canonical = ROOT / "tests/fixtures/model_v1_test_vector.npz"
    with tempfile.TemporaryDirectory() as directory:
        first = Path(directory) / "first.npz"
        second = Path(directory) / "second.npz"
        generate(ROOT, first)
        generate(ROOT, second)
        assert first.read_bytes() == second.read_bytes() == canonical.read_bytes()
        assert hash_file(first) == hash_file(canonical)
    with np.load(canonical, allow_pickle=False) as fixture:
        raw = fixture["raw_windows_float64"]
        normalized = fixture["normalized_inputs_float32"]
        expected = np.stack([normalize_window_zscore(row) for row in raw]).astype(np.float32)
        assert np.array_equal(raw, synthetic_raw_windows())
        assert np.allclose(normalized[:, 0], expected, atol=1e-7, rtol=1e-7)


def test_vectors_detect_representative_weight_mutation() -> None:
    checkpoint = torch.load(ROOT / "checkpoints/MODEL_V1.pt", weights_only=True)
    with np.load(ROOT / "tests/fixtures/model_v1_test_vector.npz", allow_pickle=False) as fixture:
        inputs = torch.from_numpy(fixture["normalized_inputs_float32"])
    model = build_model_v1()
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()
    with torch.inference_mode():
        baseline = model(inputs)
        model.output.bias[0].add_(0.01)
        mutated = model(inputs)
    assert not torch.equal(baseline, mutated)


def test_t016_production_scripts_do_not_train() -> None:
    forbidden = {"run_seed_training", "optimizer.step"}
    for relative in (
        "scripts/freeze_model_v1_t016.py",
        "scripts/generate_model_v1_test_vector_t016.py",
        "models/model_freeze.py",
    ):
        source = (ROOT / relative).read_text()
        ast.parse(source)
        assert "training.train_central" not in source
        assert not any(token in source for token in forbidden)
