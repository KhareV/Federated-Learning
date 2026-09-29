from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import torch

from evaluation.calibration import apply_operating_threshold, source_domain_calibrated_probability
from models.ecg_cnn import build_model_v1

ROOT = Path(__file__).resolve().parents[1]


def test_frozen_calibration_semantics_are_applied_without_fit() -> None:
    cal = {"temperature": 2.0, "threshold": 0.6}
    logits = np.asarray([0.0, 2.0])
    probabilities = source_domain_calibrated_probability(logits, cal)
    assert np.allclose(probabilities, [0.5, 1 / (1 + np.exp(-1.0))])
    assert apply_operating_threshold(np.asarray([0.5999, 0.6]), cal).tolist() == [0, 1]


def test_batching_does_not_change_eval_logits() -> None:
    torch.manual_seed(7)
    model = build_model_v1().eval()
    values = torch.linspace(-1, 1, steps=3 * 2500).reshape(3, 1, 2500)
    with torch.inference_mode():
        batched = model(values)
        separate = torch.cat([model(values[index : index + 1]) for index in range(3)])
    assert torch.equal(batched, separate)


def test_production_path_has_no_fitting_or_training_calls() -> None:
    source = (ROOT / "evaluation/internal_test.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    attributes = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert "optimizer" not in names
    assert "step" not in attributes
    assert "backward" not in attributes
    assert "train" not in attributes
    assert "fit_temperature" not in names
    assert "select_f1_threshold" not in names


def test_no_patient_macro_auprc_or_window_bootstrap_api() -> None:
    sources = "\n".join(
        (ROOT / relative).read_text(encoding="utf-8")
        for relative in (
            "evaluation/metrics.py",
            "evaluation/bootstrap.py",
            "evaluation/internal_test.py",
        )
    )
    assert "patient_macro_AUPRC" not in sources
    assert "mean_patient_AUPRC" not in sources
    assert "bootstrap_windows" not in sources
