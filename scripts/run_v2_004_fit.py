#!/usr/bin/env python3
"""V2-004: one architecture-causality fit (one architecture x one outer fold x one seed, D1 or
D2). Mirrors scripts/run_model_v1_cv_reference_fit_v2002.py's training-loop semantics exactly
(same optimizer/scheduler construction, same strict best-checkpoint comparison, same
early-stop rule, same reload-consistency check), reusing training.train_central's actual
primitives rather than reimplementing them. The ONLY experimental variable across fits is
which pre-registered architecture (models.model_v2_architectures) is freshly instantiated.
OPTIMISE plays the "TRAIN" role (augmented) and INNER_VALIDATION plays the "VALIDATION" role
(not augmented) for checkpoint selection; OUTER_TEST is loaded only after the selected
checkpoint is finalized and hash-recorded. Run as one fresh Python process per fit.
"""

from __future__ import annotations

import argparse
import csv
import json
import platform

import numpy as np
import torch
from torch import nn

import scripts._v2_004_lib as lib
from nhm.hashing import hash_file
from nhm.model_v2_run_manifest import create_model_v2_run_manifest, validate_model_v2_run_manifest

OUT_DIR = lib.ROOT / "reports/model_v2/v2_004"
RUNS_DIR = OUT_DIR / "runs"
CHECKPOINT_DIR = lib.ROOT / "checkpoints/model_v2/v2_004_arch_causality"


def _outer_loader(outer_population: lib.WindowPopulation, *, seed: int, config: dict) -> object:
    dataset = lib.ModelV1WindowDataset(
        outer_population, training=False, seed=seed, augmentation_config=config["augmentation"]
    )
    return lib.DataLoader(
        dataset,
        batch_size=config["training"]["batch_size"],
        shuffle=False,
        drop_last=False,
        num_workers=0,
    )


def run_fit(architecture_id: str, stage: str, outer_fold: int, seed: int) -> dict:
    exp_id = lib.experiment_id(stage, architecture_id, outer_fold, seed)
    roles = lib.role_groups_for_fold(outer_fold)
    lib.verify_role_closure(roles)

    config, config_sha256 = lib.load_frozen_model_v1_config()

    optimise_population, _optimise_meta = lib.load_role_population(
        role="OPTIMISE",
        stage_id="V2-004_TRAIN_SELECT",
        requested_outer_fold=outer_fold,
        experiment_outer_fold=outer_fold,
        architecture_id=architecture_id,
        seed=seed,
        participant_group_ids=roles.optimise_groups,
        access_purpose="training (augmented, used to fit model parameters)",
        dataset_partition_label="TRAIN",
    )
    inner_population, _inner_meta = lib.load_role_population(
        role="INNER_VALIDATION",
        stage_id="V2-004_TRAIN_SELECT",
        requested_outer_fold=outer_fold,
        experiment_outer_fold=outer_fold,
        architecture_id=architecture_id,
        seed=seed,
        participant_group_ids=roles.inner_groups,
        access_purpose="checkpoint selection / early stopping (no augmentation)",
        dataset_partition_label="VALIDATION",
    )

    pos_weight_info = lib.derive_pos_weight(optimise_population.labels)
    pos_weight_info["source_partition"] = "OPTIMISE"

    role_population_row = {
        "experiment_id": exp_id,
        "architecture_id": architecture_id,
        "stage": stage,
        "outer_fold": outer_fold,
        "seed": seed,
        "optimise_patients": len(roles.optimise_groups),
        "optimise_windows": int(optimise_population.labels.size),
        "optimise_positive": int(optimise_population.labels.sum()),
        "optimise_negative": int(
            optimise_population.labels.size - optimise_population.labels.sum()
        ),
        "inner_patients": len(roles.inner_groups),
        "inner_windows": int(inner_population.labels.size),
        "inner_positive": int(inner_population.labels.sum()),
        "inner_negative": int(inner_population.labels.size - inner_population.labels.sum()),
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
        optimise_population, inner_population, seed=seed, config=config
    )

    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    checkpoint_path = CHECKPOINT_DIR / f"{exp_id}_best.pt"

    best = -lib.math.inf
    best_epoch = 0
    non_improvement = 0
    best_metrics: dict | None = None
    best_logits: np.ndarray | None = None
    epoch_logs: list[dict] = []
    start = lib.time.perf_counter()
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
            inner_population.labels,
            inner_population.participant_group_ids,
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
                "outer_fold": outer_fold,
                "seed": seed,
                "epoch": epoch,
                "train_loss": float(loss_sum / count),
                "inner_validation_loss": validation_loss,
                "inner_validation_auprc": validation_auprc,
                "learning_rate": old_lr,
                "improved": improved,
                "non_improvement_count": non_improvement,
            }
        )
        if non_improvement >= config["training"]["early_stopping_patience"]:
            stop_reason = "EARLY_STOP_PATIENCE_7_NON_IMPROVING_EPOCHS"
            break

    wall_seconds = float(lib.time.perf_counter() - start)
    if best_metrics is None or best_logits is None:
        raise RuntimeError("no candidate checkpoint selected")

    saved = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    reloaded = lib.build_architecture(architecture_id).eval()
    reloaded.load_state_dict(saved["state_dict"])
    _, reload_logits, _ = lib._validate(
        reloaded,
        validation_loader,
        criterion,
        inner_population.labels,
        inner_population.participant_group_ids,
    )
    if not bool(np.array_equal(best_logits, reload_logits)):
        raise RuntimeError("selected checkpoint reload logits differ from training-time logits")

    checkpoint_sha256 = hash_file(checkpoint_path)
    checkpoint_finalized = True

    outer_population, outer_meta = lib.load_role_population(
        role="OUTER_TEST",
        stage_id="V2-004_OUTER_EVAL",
        requested_outer_fold=outer_fold,
        experiment_outer_fold=outer_fold,
        architecture_id=architecture_id,
        seed=seed,
        participant_group_ids=roles.outer_groups,
        checkpoint_finalized=checkpoint_finalized,
        access_purpose="one canonical outer-fold prediction pass",
        dataset_partition_label="VALIDATION",
    )
    role_population_row.update(
        {
            "outer_patients": len(roles.outer_groups),
            "outer_windows": int(outer_population.labels.size),
            "outer_positive": int(outer_population.labels.sum()),
            "outer_negative": int(outer_population.labels.size - outer_population.labels.sum()),
        }
    )

    outer_loader = _outer_loader(outer_population, seed=seed, config=config)
    reloaded.eval()
    outer_logits: list[np.ndarray] = []
    outer_example_ids: list[str] = []
    outer_groups_seen: list[str] = []
    with torch.inference_mode():
        for inputs, _targets, example_ids, groups in outer_loader:
            logits = reloaded(inputs)
            outer_logits.append(logits.cpu().numpy().reshape(-1))
            outer_example_ids.extend(example_ids)
            outer_groups_seen.extend(groups)
    outer_raw_logits = np.concatenate(outer_logits)
    if not np.all(np.isfinite(outer_raw_logits)):
        non_finite_detected = True
        raise RuntimeError("nonfinite outer-test logits")
    outer_raw_probabilities = 1.0 / (1.0 + np.exp(-outer_raw_logits))

    label_by_example = dict(
        zip(outer_population.example_ids, outer_population.labels.tolist(), strict=True)
    )
    prediction_rows = []
    for example_id, group, raw_logit, raw_probability in zip(
        outer_example_ids, outer_groups_seen, outer_raw_logits, outer_raw_probabilities,
        strict=True,
    ):
        meta = outer_meta[example_id]
        prediction_rows.append(
            {
                "example_id": example_id,
                "participant_group_id": group,
                "record_id": meta["record_id"],
                "prediction_timestamp_us": meta["prediction_timestamp_us"],
                "outer_fold": outer_fold,
                "seed": seed,
                "architecture_id": architecture_id,
                "label": label_by_example[example_id],
                "raw_logit": float(raw_logit),
                "raw_probability": float(raw_probability),
                "selected_epoch": best_epoch,
                "experiment_id": exp_id,
                "checkpoint_sha256": checkpoint_sha256,
            }
        )
    prediction_rows.sort(key=lambda r: r["example_id"])

    from sklearn.metrics import average_precision_score, roc_auc_score

    outer_auprc = float(average_precision_score(outer_population.labels, outer_raw_probabilities))
    outer_auroc = (
        float(roc_auc_score(outer_population.labels, outer_raw_probabilities))
        if len(np.unique(outer_population.labels)) == 2
        else None
    )

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    fit_dir = RUNS_DIR / exp_id
    fit_dir.mkdir(parents=True, exist_ok=True)

    predictions_path = fit_dir / "outer_predictions.csv"
    with predictions_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, lineterminator="\n", fieldnames=list(prediction_rows[0].keys())
        )
        writer.writeheader()
        writer.writerows(prediction_rows)

    training_curve_path = fit_dir / "training_curve.csv"
    with training_curve_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, lineterminator="\n", fieldnames=list(epoch_logs[0].keys())
        )
        writer.writeheader()
        writer.writerows(epoch_logs)

    fit_summary = {
        "experiment_id": exp_id,
        "architecture_id": architecture_id,
        "stage": stage,
        "outer_fold": outer_fold,
        "seed": seed,
        "selected_epoch": best_epoch,
        "best_inner_validation_auprc": best,
        "best_inner_validation_metrics": best_metrics,
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
        "outer_eligible_windows": int(outer_population.labels.size),
        "outer_auprc": outer_auprc,
        "outer_auroc": outer_auroc,
        "pos_weight": pos_weight_info["pos_weight"],
        "pos_weight_source": "OPTIMISE",
        "role_population": role_population_row,
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
        phase_id="V2-004",
        task_id="V2-004",
        config_path=lib.V2_CONFIG_PATH,
        dependency_snapshot_path=None,
        input_artifacts=[],
        output_artifacts=[],
        seed=seed,
        notes=f"V2-004 {stage} fit {exp_id}: architecture={architecture_id} "
        f"outer_fold={outer_fold} seed={seed}",
    )
    run_manifest["input_artifacts"] = [
        {
            "path": "manifests/model_v2/cv/MITDB_TRAIN_CV_V2_V1.csv",
            "sha256": hash_file(lib.OUTER_CV_CSV),
        },
        {
            "path": "manifests/model_v2/cv/MITDB_TRAIN_INNER_V2_V1.csv",
            "sha256": hash_file(lib.INNER_CV_CSV),
        },
        {"path": "configs/model_v1.yaml", "sha256": config_sha256},
    ]
    run_manifest["output_artifacts"] = [
        {
            "path": str(predictions_path.relative_to(lib.ROOT)),
            "sha256": hash_file(predictions_path),
        },
        {
            "path": str(training_curve_path.relative_to(lib.ROOT)),
            "sha256": hash_file(training_curve_path),
        },
        {"path": str(checkpoint_path.relative_to(lib.ROOT)), "sha256": checkpoint_sha256},
    ]
    run_manifest["corrective_checkpoint"] = None
    schema_path = lib.ROOT / "contracts/model_v2_run_manifest_v1.schema.json"
    validate_model_v2_run_manifest(run_manifest, schema_path)
    (fit_dir / "run_manifest.json").write_text(
        json.dumps(run_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(
        f"{exp_id}: PASS selected_epoch={best_epoch} inner_AUPRC={best:.6f} "
        f"outer_AUPRC={outer_auprc:.6f} outer_AUROC={outer_auroc}"
    )
    return fit_summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--architecture", required=True, choices=list(lib.ARCHITECTURE_IDS))
    parser.add_argument("--stage", required=True, choices=["D1", "D2"])
    parser.add_argument("--outer-fold", type=int, required=True, choices=list(lib.OUTER_FOLDS))
    parser.add_argument("--seed", type=int, required=True, choices=list(lib.ALL_SEEDS))
    args = parser.parse_args()
    run_fit(args.architecture, args.stage, args.outer_fold, args.seed)


if __name__ == "__main__":
    main()
