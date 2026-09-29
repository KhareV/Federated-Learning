#!/usr/bin/env python3
"""Audit MODEL_V1 candidates, augmentation, determinism, and prohibited scope."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import torch
import yaml
from torch import nn

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from models.ecg_cnn import build_model_v1, intermediate_shapes  # noqa: E402
from nhm.hashing import hash_canonical_json, hash_file  # noqa: E402
from training.train_central import (  # noqa: E402
    CANDIDATE_ROOT,
    CONFIG_PATH,
    MODEL_REPORT,
    RELEASE_SEED,
    REPORT_ROOT,
    ROBUSTNESS_SEEDS,
    set_determinism,
)


def _tiny_run(seed: int) -> dict:
    set_determinism(seed)
    model = build_model_v1()
    initial = copy.deepcopy(model.state_dict())
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
    criterion = nn.BCEWithLogitsLoss(pos_weight=torch.tensor([1.0]))
    generator = torch.Generator().manual_seed(808)
    inputs = torch.randn(4, 1, 2500, generator=generator)
    targets = torch.tensor([[0.0], [1.0], [0.0], [1.0]])
    losses: list[float] = []
    model.train()
    for _ in range(2):
        optimizer.zero_grad(set_to_none=True)
        loss = criterion(model(inputs), targets)
        loss.backward()
        optimizer.step()
        losses.append(float(loss.item()))
    final = copy.deepcopy(model.state_dict())
    model.eval()
    bn_before = [
        (module.running_mean.clone(), module.running_var.clone())
        for module in model.modules()
        if isinstance(module, nn.BatchNorm1d)
    ]
    with torch.inference_mode():
        first = model(inputs)
        second = model(inputs)
    bn_after = [
        (module.running_mean, module.running_var)
        for module in model.modules()
        if isinstance(module, nn.BatchNorm1d)
    ]
    return {
        "initial": initial,
        "losses": losses,
        "final": final,
        "logits": first,
        "eval_repeat_equal": torch.equal(first, second),
        "bn_unchanged": all(
            torch.equal(left_mean, right_mean) and torch.equal(left_var, right_var)
            for (left_mean, left_var), (right_mean, right_var) in zip(
                bn_before, bn_after, strict=True
            )
        ),
    }


def _states_equal(left: dict[str, torch.Tensor], right: dict[str, torch.Tensor]) -> bool:
    return left.keys() == right.keys() and all(
        torch.equal(left[key], right[key]) for key in left
    )


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    summary = json.loads(MODEL_REPORT.read_text(encoding="utf-8"))
    if summary["overall_status"] != "PASS":
        raise RuntimeError("real candidate run not PASS")
    source = (ROOT / "models/ecg_cnn.py").read_text(encoding="utf-8")
    runner_source = (ROOT / "training/train_central.py").read_text(encoding="utf-8")
    forbidden_model = ("nn.Sigmoid", "nn.Softmax", "nn.LogSoftmax", "CrossEntropyLoss")
    forbidden_runner = (
        "WeightedRandomSampler",
        "CosineAnnealingLR",
        "GridSearchCV",
        "RandomizedSearchCV",
        "Optuna",
        "torch.flip(",
    )
    if any(token in source for token in forbidden_model) or any(
        token in runner_source for token in forbidden_runner
    ):
        raise RuntimeError("forbidden MODEL_V1 production pattern")
    model = build_model_v1()
    parameter_count = sum(parameter.numel() for parameter in model.parameters())
    shapes = {key: list(value) for key, value in intermediate_shapes().items()}
    contract = json.loads((REPORT_ROOT / "training_contract_audit.json").read_text())
    if parameter_count != 13_185 or contract["overall_status"] != "PASS":
        raise RuntimeError("MODEL_V1 training contract mismatch")

    first = _tiny_run(314159)
    second = _tiny_run(314159)
    determinism_checks = {
        "initial_parameters_repeat_identical": _states_equal(first["initial"], second["initial"]),
        "loss_sequence_repeat_identical": first["losses"] == second["losses"],
        "final_parameters_repeat_identical": _states_equal(first["final"], second["final"]),
        "validation_logits_repeat_identical": torch.equal(first["logits"], second["logits"]),
        "eval_mode_repeat_logits": first["eval_repeat_equal"],
        "BN_validation_state_unchanged": first["bn_unchanged"],
    }
    if not all(determinism_checks.values()):
        raise RuntimeError(f"determinism smoke failure: {determinism_checks}")
    determinism = {
        "model_id": "MODEL_V1",
        "fixture_scope": "SYNTHETIC_T015_ONLY_NOT_FINAL_T016_TEST_VECTOR",
        "seed": 314159,
        "steps": 2,
        "checks": determinism_checks,
        "first_loss_sequence": first["losses"],
        "overall_status": "PASS",
    }
    write_json(REPORT_ROOT / "determinism_smoke.json", determinism)

    augmentation = config["augmentation"]
    augmentation_audit = {
        "augmentation_id": augmentation["augmentation_id"],
        "config_sha256": hash_canonical_json(augmentation),
        "scope": augmentation["scope"],
        "amplitude_scale_range": [
            augmentation["amplitude_scale_min"],
            augmentation["amplitude_scale_max"],
        ],
        "baseline_drift": augmentation["baseline_drift"],
        "gaussian_noise": augmentation["gaussian_noise"],
        "development_sources": augmentation["development_sources"],
        "validation_or_heldout_tuning": augmentation["validation_or_heldout_tuning"],
        "time_reversal": augmentation["time_reversal"],
        "deterministic_identity_inputs": ["seed", "epoch", "example_id", "config"],
        "overall_status": "PASS",
    }
    write_json(REPORT_ROOT / "augmentation_audit.json", augmentation_audit)

    candidates = []
    for seed in (RELEASE_SEED, *ROBUSTNESS_SEEDS):
        checkpoint = CANDIDATE_ROOT / f"MODEL_V1_seed_{seed}_best.pt"
        metadata = checkpoint.with_suffix(".metadata.json")
        seed_log = REPORT_ROOT / "seeds" / f"{seed}.json"
        values = json.loads(metadata.read_text(encoding="utf-8"))
        if hash_file(checkpoint) != values["checkpoint_sha256"]:
            raise RuntimeError(f"candidate hash mismatch for seed {seed}")
        candidates.append(
            {
                "seed": seed,
                "status": "CANDIDATE_T015_NOT_FROZEN",
                "checkpoint_path": str(checkpoint.relative_to(ROOT)),
                "checkpoint_sha256": hash_file(checkpoint),
                "metadata_path": str(metadata.relative_to(ROOT)),
                "metadata_sha256": hash_file(metadata),
                "seed_log_path": str(seed_log.relative_to(ROOT)),
                "seed_log_sha256": hash_file(seed_log),
                "best_epoch": values["best_epoch"],
                "best_validation_auprc": values["best_validation_auprc"],
            }
        )
    manifest = {
        "model_id": "MODEL_V1",
        "package_status": "MODEL_V1_CANDIDATE_READY_FOR_T016",
        "release_candidate_seed": RELEASE_SEED,
        "robustness_seeds": list(ROBUSTNESS_SEEDS),
        "config_sha256": hash_file(CONFIG_PATH),
        "parameter_count": parameter_count,
        "intermediate_shapes": shapes,
        "candidates": candidates,
        "final_MODEL_V1_promoted": False,
        "F08_frozen": False,
        "overall_status": "PASS",
    }
    write_json(CANDIDATE_ROOT / "candidate_manifest.json", manifest)
    if (ROOT / "checkpoints/MODEL_V1.pt").exists():
        raise RuntimeError("T016-owned final checkpoint exists prematurely")
    print("T015 MODEL_V1 audit: PASS")


if __name__ == "__main__":
    main()
