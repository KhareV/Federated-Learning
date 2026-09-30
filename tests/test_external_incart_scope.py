from __future__ import annotations

import ast
import copy
from pathlib import Path

import numpy as np
import torch

from models.model_freeze import load_frozen_model_v1

ROOT = Path(__file__).resolve().parents[1]


def test_external_production_path_has_no_training_or_adaptation() -> None:
    source = (ROOT / "evaluation/external_incart.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert "train" not in attributes
    assert "backward" not in attributes
    assert "step" not in attributes
    assert "fit_temperature" not in names
    assert "select_f1_threshold" not in names
    assert "load_internal_population" not in names


def test_external_eval_mode_does_not_update_batchnorm() -> None:
    model, _ = load_frozen_model_v1(ROOT)
    before = copy.deepcopy(model.state_dict())
    model.eval()
    fixture = torch.from_numpy(np.zeros((2, 1, 2500), dtype=np.float32))
    with torch.inference_mode():
        first = model(fixture)
        second = model(fixture)
    assert torch.equal(first, second)
    assert all(torch.equal(before[key], model.state_dict()[key]) for key in before)


def test_method_forbids_external_fit_and_alternate_models() -> None:
    text = (ROOT / "configs/external_incart_v1.yaml").read_text(encoding="utf-8")
    for required in (
        "batchnorm_adaptation: true",
        "normalization_fit: true",
        "calibration_fit: true",
        "threshold_search: true",
        "lead_search: true",
        "alternate_seed_evaluation: true",
    ):
        assert required in text
