from __future__ import annotations

import copy
from pathlib import Path

import torch
import yaml
from torch import nn

from models.ecg_cnn import build_model_v1
from training.train_central import set_determinism

ROOT = Path(__file__).resolve().parents[1]
CONFIG = yaml.safe_load((ROOT / "configs/model_v1.yaml").read_text())


def tiny_train(seed: int) -> tuple[list[float], dict[str, torch.Tensor], torch.Tensor]:
    set_determinism(seed)
    model = build_model_v1()
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
    criterion = nn.BCEWithLogitsLoss(pos_weight=torch.tensor([1.0]))
    generator = torch.Generator().manual_seed(44)
    inputs = torch.randn(4, 1, 2500, generator=generator)
    labels = torch.tensor([[0.0], [1.0], [0.0], [1.0]])
    losses: list[float] = []
    model.train()
    for _ in range(2):
        optimizer.zero_grad(set_to_none=True)
        loss = criterion(model(inputs), labels)
        loss.backward()
        optimizer.step()
        losses.append(float(loss.item()))
    model.eval()
    with torch.inference_mode():
        logits = model(inputs)
    return losses, copy.deepcopy(model.state_dict()), logits


def test_small_training_repeat_is_exact() -> None:
    first = tiny_train(123)
    second = tiny_train(123)
    assert first[0] == second[0]
    for key in first[1]:
        assert torch.equal(first[1][key], second[1][key])
    assert torch.equal(first[2], second[2])


def test_eval_dropout_deterministic_and_bn_state_unchanged() -> None:
    model = build_model_v1()
    model.eval()
    inputs = torch.randn(5, 1, 2500)
    batch_norms = [
        module for module in model.modules() if isinstance(module, nn.BatchNorm1d)
    ]
    before = [
        (module.running_mean.clone(), module.running_var.clone()) for module in batch_norms
    ]
    with torch.inference_mode():
        first = model(inputs)
        second = model(inputs)
    after = [(module.running_mean, module.running_var) for module in batch_norms]
    assert torch.equal(first, second)
    for (mean_before, var_before), (mean_after, var_after) in zip(before, after, strict=True):
        assert torch.equal(mean_before, mean_after)
        assert torch.equal(var_before, var_after)


def test_checkpoint_round_trip(tmp_path: Path) -> None:
    set_determinism(7)
    model = build_model_v1().eval()
    inputs = torch.randn(2, 1, 2500)
    with torch.inference_mode():
        expected = model(inputs)
    path = tmp_path / "candidate.pt"
    torch.save({"state_dict": model.state_dict()}, path)
    loaded = build_model_v1().eval()
    loaded.load_state_dict(torch.load(path, weights_only=False)["state_dict"])
    with torch.inference_mode():
        actual = loaded(inputs)
    assert torch.equal(expected, actual)
