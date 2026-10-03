#!/usr/bin/env python3
"""V2-007: one finalist fit (one architecture x one seed, no fold dimension -- one fixed
FINAL TRAIN-only inner split). Mirrors scripts/run_v2_004_fit.py's training-loop semantics
exactly (same optimizer/scheduler construction, same strict best-checkpoint comparison, same
early-stop rule, same reload-consistency check). OPTIMISE plays the "TRAIN" role (augmented,
gradient updates, pos_weight source); FINAL_INNER_VALIDATION plays the "VALIDATION" role (no
augmentation, no gradient updates) for scheduler/early-stop/checkpoint-selection. After the
checkpoint is finalized and reload-verified, a TRAIN-source diagnostic (all 27 TRAIN groups,
eval-mode only) is scored for descriptive development-to-validation-gap reporting -- this
NEVER touches official VALIDATION and never influences checkpoint selection. Run as one fresh
Python process per fit.
"""

from __future__ import annotations

import argparse
import csv
import json
import platform

import numpy as np
import torch
from torch import nn

import scripts._v2_007_lib as lib
from nhm.hashing import hash_file
from nhm.model_v2_run_manifest import create_model_v2_run_manifest, validate_model_v2_run_manifest

OUT_DIR = lib.ROOT / "reports/model_v2/v2_007"
RUNS_DIR = OUT_DIR / "runs"
CHECKPOINT_DIR = lib.ROOT / "checkpoints/model_v2/v2_007_official_validation"


def run_fit(architecture_id: str, seed: int) -> dict:
    exp_id = lib.experiment_id(architecture_id, seed)
    schedule_id = next(
        f["schedule_id"] for f in lib.FINALISTS if f["architecture_id"] == architecture_id
    )
    optimise_groups, final_inner_groups = lib.load_final_inner_roles()
    lib.verify_final_inner_closure(optimise_groups, final_inner_groups)

    config, config_sha256 = lib.load_frozen_model_v1_config()

    optimise_population, _optimise_meta = lib.load_role_population(
        role="OPTIMISE",
        stage_id="V2-007_TRAIN_SELECT",
        architecture_id=architecture_id,
        schedule_id=schedule_id,
        seed=seed,
        participant_group_ids=optimise_groups,
        access_purpose="training (augmented, used to fit model parameters)",
        dataset_partition_label="TRAIN",
    )
    final_inner_population, _final_inner_meta = lib.load_role_population(
        role="FINAL_INNER_VALIDATION",
        stage_id="V2-007_TRAIN_SELECT",
        architecture_id=architecture_id,
        schedule_id=schedule_id,
        seed=seed,
        participant_group_ids=final_inner_groups,
        access_purpose="checkpoint selection / scheduler / early stopping (no augmentation)",
        dataset_partition_label="VALIDATION",
    )

    pos_weight_info = lib.derive_pos_weight(optimise_population.labels)
    pos_weight_info["source_partition"] = "OPTIMISE"

    role_population_row = {
        "experiment_id": exp_id,
        "architecture_id": architecture_id,
        "schedule_id": schedule_id,
        "seed": seed,
        "optimise_patients": len(optimise_groups),
        "optimise_windows": int(optimise_population.labels.size),
        "optimise_positive": int(optimise_population.labels.sum()),
        "optimise_negative": int(
            optimise_population.labels.size - optimise_population.labels.sum()
        ),
        "final_inner_patients": len(final_inner_groups),
        "final_inner_windows": int(final_inner_population.labels.size),
        "final_inner_positive": int(final_inner_population.labels.sum()),
        "final_inner_negative": int(
            final_inner_population.labels.size - final_inner_population.labels.sum()
        ),
        "pos_weight": pos_weight_info["pos_weight"],
    }

    lib.set_determinism(seed)
    model = lib.build_architecture(architecture_id).to("cpu")
    parameter_count = sum(p.numel() for p in model.parameters() if p.requires_grad)
    if parameter_count != lib.EXPECTED_PARAMETER_COUNTS[architecture_id]:
        raise RuntimeError(
            f"{architecture_id} parameter count {parameter_count} != expected "
            f"{lib.EXPECTED_PARAMETER_COUNTS[architecture_id]}"
        )
    criterion = nn.BCEWithLogitsLoss(
        pos_weight=torch.tensor([pos_weight_info["pos_weight"]], dtype=torch.float32)
    )
    optimizer, scheduler = lib.build_optimizer_and_scheduler(model, config)
    train_dataset, train_loader, validation_loader = lib._make_loaders(
        optimise_population, final_inner_population, seed=seed, config=config
    )

    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    checkpoint_path = CHECKPOINT_DIR / f"{exp_id}_best.pt"

    best = float("-inf")
    best_epoch = 0
    non_improvement = 0
    best_metrics: dict | None = None
    best_logits: np.ndarray | None = None
    epoch_logs: list[dict] = []
    import time as _time

    start = _time.perf_counter()
    initial_lr = float(optimizer.param_groups[0]["lr"])
    lr_reductions = 0
    stop_reason = "MAX_EPOCHS"
    non_finite_detected = False

    for epoch in range(1, config["training"]["max_epochs"] + 1):
        train_dataset.set_epoch(epoch)
        model.train()
        loss_sum = 0.0
        count = 0
        for inputs, targets, _example_ids, _groups in train_loader:
            optimizer.zero_grad(set_to_none=True)
            logits = model(inputs)
            if logits.shape != targets.shape:
                raise RuntimeError(f"BCE shape mismatch: {logits.shape} vs {targets.shape}")
            loss = criterion(logits, targets)
            if not torch.isfinite(loss):
                non_finite_detected = True
                raise RuntimeError("nonfinite training loss")
            loss.backward()
            optimizer.step()
            loss_sum += float(loss.item()) * inputs.shape[0]
            count += inputs.shape[0]
        validation_loss, validation_logits, metrics = lib._validate(
            model,
            validation_loader,
            criterion,
            final_inner_population.labels,
            final_inner_population.participant_group_ids,
        )
        if not np.all(np.isfinite(validation_logits)):
            non_finite_detected = True
            raise RuntimeError("nonfinite validation logits")
        validation_auprc = float(metrics["AUPRC"])
        improved = validation_auprc > best
        if improved:
            best = validation_auprc
            best_epoch = epoch
            best_metrics = metrics
            best_logits = validation_logits.copy()
            non_improvement = 0
            torch.save(
                lib._checkpoint_payload(
                    model,
                    seed=seed,
                    epoch=epoch,
                    validation_auprc=validation_auprc,
                    config_sha256=config_sha256,
                ),
                checkpoint_path,
            )
        else:
            non_improvement += 1
        old_lr = float(optimizer.param_groups[0]["lr"])
        scheduler.step(validation_auprc)
        new_lr = float(optimizer.param_groups[0]["lr"])
        if new_lr < old_lr:
            lr_reductions += 1
        epoch_logs.append(
            {
                "experiment_id": exp_id,
                "architecture_id": architecture_id,
                "seed": seed,
                "epoch": epoch,
                "train_loss": float(loss_sum / count),
                "final_inner_validation_loss": validation_loss,
                "final_inner_validation_auprc": validation_auprc,
                "learning_rate": old_lr,
                "improved": improved,
                "non_improvement_count": non_improvement,
            }
        )
        if non_improvement >= config["training"]["early_stopping_patience"]:
            stop_reason = "EARLY_STOP_PATIENCE_7_NON_IMPROVING_EPOCHS"
            break

    wall_seconds = float(_time.perf_counter() - start)
    if best_metrics is None or best_logits is None:
        raise RuntimeError("no candidate checkpoint selected")

    saved = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    reloaded = lib.build_architecture(architecture_id).eval()
    reloaded.load_state_dict(saved["state_dict"])
    _, reload_logits, _ = lib._validate(
        reloaded,
        validation_loader,
        criterion,
        final_inner_population.labels,
        final_inner_population.participant_group_ids,
    )
    if not bool(np.array_equal(best_logits, reload_logits)):
        raise RuntimeError("selected checkpoint reload logits differ from training-time logits")

    checkpoint_sha256 = hash_file(checkpoint_path)
    checkpoint_finalized = True

    # Post-checkpoint TRAIN-source diagnostic: all 27 TRAIN groups, eval mode, no augmentation,
    # no gradient. Descriptive only -- never influences checkpoint selection, never touches
    # official VALIDATION.
    all_groups = lib.all_train_groups()
    diagnostic_population, _diag_meta = lib.load_role_population(
        role="FINAL_INNER_VALIDATION",
        stage_id="V2-007_TRAIN_DIAGNOSTIC",
        architecture_id=architecture_id,
        schedule_id=schedule_id,
        seed=seed,
        participant_group_ids=all_groups,
        checkpoint_finalized=checkpoint_finalized,
        access_purpose="descriptive TRAIN-source development diagnostic (not unbiased)",
        dataset_partition_label="VALIDATION",
    )

    reloaded.eval()
    _diag_logits, diag_probs, _diag_ids, _diag_groups = lib.score_checkpoint(
        reloaded, diagnostic_population, seed=seed, config=config,
    )

    from sklearn.metrics import average_precision_score, roc_auc_score

    diag_labels = diagnostic_population.labels
    source_train_auprc = float(average_precision_score(diag_labels, diag_probs))
    source_train_auroc = (
        float(roc_auc_score(diag_labels, diag_probs))
        if len(np.unique(diag_labels)) == 2
        else None
    )

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    fit_dir = RUNS_DIR / exp_id
    fit_dir.mkdir(parents=True, exist_ok=True)

    training_curve_path = fit_dir / "training_curve.csv"
    with training_curve_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, lineterminator="\n", fieldnames=list(epoch_logs[0].keys()))
        writer.writeheader()
        writer.writerows(epoch_logs)

    fit_summary = {
        "experiment_id": exp_id,
        "architecture_id": architecture_id,
        "schedule_id": schedule_id,
        "seed": seed,
        "selected_epoch": best_epoch,
        "best_final_inner_validation_auprc": best,
        "best_final_inner_validation_metrics": best_metrics,
        "checkpoint_path": str(checkpoint_path.relative_to(lib.ROOT)),
        "checkpoint_sha256": checkpoint_sha256,
        "parameter_count": parameter_count,
        "epochs_completed": len(epoch_logs),
        "stop_epoch": len(epoch_logs),
        "stop_reason": stop_reason,
        "lr_reductions": lr_reductions,
        "initial_learning_rate": initial_lr,
        "final_learning_rate": float(optimizer.param_groups[0]["lr"]),
        "wall_clock_seconds": wall_seconds,
        "checkpoint_reload_consistency": "PASS",
        "non_finite_detected": non_finite_detected,
        "pos_weight": pos_weight_info["pos_weight"],
        "pos_weight_source": "OPTIMISE",
        "role_population": role_population_row,
        "source_train_diagnostic": {
            "windows": int(diag_labels.size),
            "source_train_auprc": source_train_auprc,
            "source_train_auroc": source_train_auroc,
            "descriptive_only_not_unbiased": True,
        },
        "environment": {
            "torch_version": torch.__version__,
            "numpy_version": np.__version__,
            "platform": platform.platform(),
        },
    }
    (fit_dir / "fit_summary.json").write_text(
        json.dumps(fit_summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    run_manifest = create_model_v2_run_manifest(
        lib.ROOT,
        run_id=exp_id,
        phase_id="V2-007",
        task_id="V2-007",
        config_path=lib.V2_CONFIG_PATH,
        dependency_snapshot_path=None,
        input_artifacts=[],
        output_artifacts=[],
        seed=seed,
        notes=f"V2-007 fit {exp_id}: architecture={architecture_id} seed={seed}",
    )
    run_manifest["input_artifacts"] = [
        {"path": "manifests/model_v2/cv/MITDB_TRAIN_FINAL_INNER_V2_V1.csv",
         "sha256": hash_file(lib.FINAL_INNER_CSV)},
        {"path": "configs/model_v1.yaml", "sha256": config_sha256},
    ]
    run_manifest["output_artifacts"] = [
        {"path": str(training_curve_path.relative_to(lib.ROOT)),
         "sha256": hash_file(training_curve_path)},
        {"path": str(checkpoint_path.relative_to(lib.ROOT)), "sha256": checkpoint_sha256},
    ]
    run_manifest["corrective_checkpoint"] = None
    schema_path = lib.ROOT / "contracts/model_v2_run_manifest_v1.schema.json"
    validate_model_v2_run_manifest(run_manifest, schema_path)
    (fit_dir / "run_manifest.json").write_text(
        json.dumps(run_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(
        f"{exp_id}: PASS selected_epoch={best_epoch} final_inner_AUPRC={best:.6f} "
        f"source_train_AUPRC={source_train_auprc:.6f}"
    )
    return fit_summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--architecture", required=True, choices=["MODEL_V2_TCN_MEAN", "MODEL_V2_TCN_MEANMAX"]
    )
    parser.add_argument("--seed", type=int, required=True, choices=list(lib.SEEDS))
    args = parser.parse_args()
    run_fit(args.architecture, args.seed)


if __name__ == "__main__":
    main()
