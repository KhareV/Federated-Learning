"""V2-FL-003: deterministic MODEL_V2 FedProx runner (LABEL mu candidates and selected-mu transfer
conditions). Mirrors federated.model_v2_non_iid_runner (V2-FL-002) with only the local
objective changed. Reads ONLY MIT-BIH TRAIN, VALIDATION and (feature/combined) NSTDB
pure-noise records via the frozen FL_FEATURE_NOISE_V1 training construction; every access is
firewall-gated and ledgered."""

from __future__ import annotations

import copy
import math
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch
import yaml

from federated.aggregation import ClientUpdate, aggregate_weighted_deltas
from federated.client_manifest import SITE_IDS
from federated.evaluation import evaluate_model
from federated.feature_noise import build_noise_bank, transform_population
from federated.fedavg_runner import (
    _write_csv,
    _write_json,
    choose_best_round,
    flower_reference_parity,
    normalized_population,
    stable_convergence,
)
from federated.model_adapter import restore_state, serialize_state
from federated.model_v2_fedprox import train_local_fedprox_epoch_v2
from federated.model_v2_fl import fresh_initial_state_v2, fresh_model_v2, set_determinism, state_sha
from federated.model_v2_non_iid_runner import per_patient_metrics
from federated.non_iid_runner import load_sites
from nhm.hashing import hash_file
from nhm.model_v2_partition_guard import _append_ledger, check_partition_allowed
from training.train_central import WindowPopulation, load_population

STAGE_ID = "V2-FL-003"
ALLOWED = ("TRAIN", "VALIDATION", "NSTDB")
CONFIG_RELATIVE = "configs/model_v2/fedprox_v2.yaml"
OUT_RELATIVE = "reports/model_v2/v2_fl_003"
CKPT_RELATIVE = "checkpoints/model_v2/v2_fl_003"
NSTDB_ROLE = "NSTDB_PURE_NOISE_TRAINING_RESOURCE"


def mu_token(mu: float) -> str:
    return str(mu).replace(".", "p")


def run_key(condition: str, mu: float, role: str) -> tuple[str, str, str]:
    """(experiment_id, report subdirectory, checkpoint subdirectory)."""
    if role == "candidate":
        stem = f"FL_LABEL_FEDPROX_MODEL_V2_MU_{mu_token(mu)}"
        return stem, f"candidates/mu_{mu_token(mu)}", "candidates"
    return (f"FL_{condition.upper()}_FEDPROX_MODEL_V2_MU_{mu_token(mu)}",
            f"transfer/{condition}", "transfer")


def _ledger(root: Path, partition: str, access_type: str, rows: int | None, tag: str,
            source: str) -> None:
    _append_ledger(root, {
        "timestamp_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "stage_id": STAGE_ID, "experiment_id": tag, "partition": partition,
        "access_type": access_type, "rows": rows, "source_path": source})


def guarded_population(root: Path, partition: str, tag: str) -> WindowPopulation:
    check_partition_allowed(partition, STAGE_ID, ("TRAIN", "VALIDATION"))
    population = load_population(partition)
    _ledger(root, partition, "waveform_read", int(population.labels.size), tag,
            "frozen MITDB_WINDOWS_V1 caches (load_population)")
    return population


def guarded_noise_bank(root: Path, tag: str) -> dict[str, np.ndarray]:
    check_partition_allowed("NSTDB", STAGE_ID, ALLOWED)
    bank, _ = build_noise_bank(root)
    _ledger(root, "NSTDB", NSTDB_ROLE, sum(int(v.size) for v in bank.values()), tag,
            "data/raw/nstdb/1.0.0/{bw,em,ma} (FL_FEATURE_NOISE_V1 pure-noise records)")
    return bank


def save_checkpoint(path: Path, state: dict[str, np.ndarray], *, experiment_id: str, mu: float,
                    round_number: int, auprc: float, config_sha: str, manifest_sha: str) -> None:
    model = fresh_model_v2()
    restore_state(model, state)
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save({
        "checkpoint_id": experiment_id, "model_architecture_id": "MODEL_V2_TCN_MEAN",
        "initialization_id": "FL_INIT_V2", "FL_method": "FEDPROX_METHOD_V2", "mu": mu,
        "round": round_number, "validation_AUPRC": auprc, "config_sha256": config_sha,
        "client_manifest_sha256": manifest_sha, "transport_id": "FL_STATE_TRANSPORT_V1",
        "aggregation_id": "SAMPLE_COUNT_WEIGHTED_MODEL_DELTA_V1", "calibration": "NONE",
        "supersedes_model_v2_final": False, "state_dict": copy.deepcopy(model.state_dict())},
        path)


def run_fedprox(root: Path, condition: str, mu: float, role: str) -> dict[str, Any]:
    started = time.monotonic()
    config_path = root / CONFIG_RELATIVE
    config = yaml.safe_load(config_path.read_text())
    cond = config["conditions"][condition]
    experiment_id, report_sub, ckpt_sub = run_key(condition, mu, role)
    out = root / OUT_RELATIVE / report_sub
    manifest_path = root / "manifests/clients" / cond["path"]
    manifest_sha = hash_file(manifest_path)
    if manifest_sha != cond["sha256"]:
        raise RuntimeError("MANIFEST_SHA_MISMATCH")
    sites = load_sites(manifest_path)
    seed = int(config["initialization"]["seed"])
    set_determinism(seed)
    train = guarded_population(root, "TRAIN", experiment_id)
    validation = guarded_population(root, "VALIDATION", experiment_id)
    clean_train = normalized_population(train)
    validation_inputs = normalized_population(validation)
    group_to_site = {g: s for s, groups in sites.items() for g in groups}
    site_indices = {s: np.flatnonzero(np.isin(train.participant_group_ids, groups))
                    for s, groups in sites.items()}
    train_inputs, noise_fixtures = clean_train, []
    if cond["feature_noise"]:
        bank = guarded_noise_bank(root, experiment_id)
        site_for_example = {str(e): group_to_site[str(g)] for e, g in zip(
            train.example_ids, train.participant_group_ids, strict=True)}
        train_inputs, noise_fixtures = transform_population(
            np.asarray(train.waveforms, dtype=np.float64), train.example_ids,
            site_for_example, bank)
    pos_weight = float(np.sum(train.labels == 0) / np.sum(train.labels == 1))
    if not math.isclose(pos_weight, float(config["loss"]["pos_weight"]), rel_tol=0,
                        abs_tol=1e-15):
        raise RuntimeError("global TRAIN pos_weight mismatch")
    global_state = fresh_initial_state_v2(seed)
    initial_sha = state_sha(global_state)
    if initial_sha != config["initialization"]["round_0_state_sha256"]:
        raise RuntimeError("ROUND0_STATE_NOT_FL_INIT_V2")
    model = fresh_model_v2()
    restore_state(model, global_state)
    metrics0, _, _ = evaluate_model(model, validation_inputs, validation.labels,
                                    validation.participant_group_ids, pos_weight=pos_weight,
                                    partition="VALIDATION")
    if metrics0["AUPRC"] != config["initialization"]["round_0_validation_AUPRC"]:
        raise RuntimeError("ROUND0_VALIDATION_DIFFERS_FROM_V2_FL_001: STOP")

    def row(round_number: int, metrics: dict[str, Any], sha: str, **extra: Any) -> dict[str, Any]:
        base = {
            "round": round_number, "client_count": 0, "total_examples": 0,
            "training_weighted_mean_loss": "", "validation_windows": int(validation.labels.size),
            "validation_AUPRC": metrics["AUPRC"], "validation_AUROC": metrics["AUROC"],
            "validation_raw_F1_at_0_5": metrics["pooled_F1"],
            "validation_precision_at_0_5": metrics["precision"],
            "validation_sensitivity_at_0_5": metrics["sensitivity"],
            "validation_specificity_at_0_5": metrics["specificity"],
            "validation_patient_macro_F1_at_0_5": metrics["patient_macro_F1"],
            "validation_BCE": metrics["BCE"], "global_state_sha256": sha, "bytes_received": 0,
            "bytes_sent": 0, "finite_state": True, "selected_best_so_far": False,
            "round_wall_seconds": ""}
        base.update(extra)
        return base

    rounds = [row(0, metrics0, initial_sha)]
    clients: list[dict[str, Any]] = []
    states: dict[int, dict[str, np.ndarray]] = {0: copy.deepcopy(global_state)}
    server_payload = len(serialize_state(global_state))
    parity: dict[str, Any] | None = None
    total_rounds = int(config["training"]["rounds"])
    for round_number in range(1, total_rounds + 1):
        tick = time.monotonic()
        updates: list[ClientUpdate] = []
        losses: list[tuple[float, int]] = []
        for site in SITE_IDS:
            indices = site_indices[site]
            result = train_local_fedprox_epoch_v2(
                global_state=global_state, inputs=train_inputs[indices],
                labels=train.labels[indices], site_id=site, round_number=round_number,
                experiment_id=config["shuffle_seed_namespace"], base_seed=seed,
                batch_size=int(config["training"]["batch_size"]),
                learning_rate=float(config["optimizer"]["learning_rate"]),
                weight_decay=float(config["optimizer"]["weight_decay"]), pos_weight=pos_weight,
                mu=mu)
            if result.examples_seen != indices.size:
                raise RuntimeError("client sample-count weight mismatch")
            updates.append(result.update)
            losses.append((result.mean_loss, result.examples_seen))
            labels = train.labels[indices]
            clients.append({
                "round": round_number, "site_id": site, "patient_count": len(sites[site]),
                "num_examples": result.examples_seen,
                "positive_examples": int(np.sum(labels == 1)),
                "negative_examples": int(np.sum(labels == 0)), "mu": mu,
                "shuffle_seed": result.shuffle_seed, "batch_count": result.batch_count,
                "local_epoch": 1, "optimizer": "AdamW",
                "learning_rate": config["optimizer"]["learning_rate"],
                "weight_decay": config["optimizer"]["weight_decay"],
                "local_training_loss": result.mean_loss, "update_norm": result.update_norm,
                "update_bytes": result.update_bytes, "status": "PASS"})
        if round_number == 1:
            parity = flower_reference_parity(global_state, updates)
            if parity["status"] != "PASS":
                raise RuntimeError("aggregation parity")
        global_state, _ = aggregate_weighted_deltas(global_state, updates)
        if not all(np.isfinite(v).all() for v in global_state.values()
                   if np.issubdtype(v.dtype, np.floating)):
            raise RuntimeError("nonfinite state")
        states[round_number] = copy.deepcopy(global_state)
        model = fresh_model_v2()
        restore_state(model, global_state)
        metrics, _, _ = evaluate_model(model, validation_inputs, validation.labels,
                                       validation.participant_group_ids,
                                       pos_weight=pos_weight, partition="VALIDATION")
        total = sum(u.num_examples for u in updates)
        prior = max([float(r["validation_AUPRC"]) for r in rounds if int(r["round"]) >= 1]
                    + [-math.inf])
        rounds.append(row(
            round_number, metrics, state_sha(global_state), client_count=len(updates),
            total_examples=total,
            training_weighted_mean_loss=sum(a * n for a, n in losses) / total,
            bytes_received=sum(int(r["update_bytes"]) for r in clients[-8:]),
            bytes_sent=server_payload * 8,
            selected_best_so_far=float(metrics["AUPRC"]) > prior,
            round_wall_seconds=round(time.monotonic() - tick, 3)))
        print(f"{experiment_id} round {round_number:02d} AUPRC={metrics['AUPRC']:.4f}",
              flush=True)
    best_round = choose_best_round(rounds)
    best_row = next(r for r in rounds if int(r["round"]) == best_round)
    config_sha = hash_file(config_path)
    ckpt_dir = root / CKPT_RELATIVE / ckpt_sub
    best_path = ckpt_dir / f"{experiment_id}_best.pt"
    final_path = ckpt_dir / f"{experiment_id}_round{total_rounds}.pt"
    save_checkpoint(best_path, states[best_round], experiment_id=experiment_id, mu=mu,
                    round_number=best_round, auprc=float(best_row["validation_AUPRC"]),
                    config_sha=config_sha, manifest_sha=manifest_sha)
    save_checkpoint(final_path, states[total_rounds], experiment_id=experiment_id, mu=mu,
                    round_number=total_rounds, auprc=float(rounds[-1]["validation_AUPRC"]),
                    config_sha=config_sha, manifest_sha=manifest_sha)
    best_model = fresh_model_v2()
    restore_state(best_model, states[best_round])
    best_metrics, logits, probs = evaluate_model(
        best_model, validation_inputs, validation.labels, validation.participant_group_ids,
        pos_weight=pos_weight, partition="VALIDATION")
    predictions = [{
        "example_id": str(e), "participant_group_id": str(g), "label": int(y),
        "raw_logit": format(float(lg), ".17g"),
        "raw_sigmoid_probability": format(float(p), ".17g"),
        "prediction_at_0_5": int(p >= 0.5), "round": best_round}
        for e, g, y, lg, p in zip(validation.example_ids, validation.participant_group_ids,
                                  validation.labels, logits, probs, strict=True)]
    _write_csv(out / "validation_predictions.csv", predictions)
    # Patient metrics are computed ONLY after the checkpoint round is fixed (epoch selection and
    # mu selection are distinct operations).
    patient = per_patient_metrics(validation.labels, probs, validation.participant_group_ids)
    _write_json(out / "validation_patient_metrics.json", patient)
    diagnostics, defined = {}, []
    for site in SITE_IDS:
        idx = site_indices[site]
        labels = train.labels[idx]
        site_metrics, _, _ = evaluate_model(
            best_model, clean_train[idx], labels, train.participant_group_ids[idx],
            pos_weight=pos_weight, partition="SITE_LOCAL_TRAIN_DIAGNOSTIC")
        if len(np.unique(labels)) < 2:
            site_metrics["AUPRC"] = None
        else:
            defined.append(float(site_metrics["AUPRC"]))
        diagnostics[site] = {**site_metrics, "label": "SITE_LOCAL_TRAIN_DIAGNOSTIC"}
    _write_csv(out / "round_log.csv", rounds)
    _write_csv(out / "client_rounds.csv", clients)
    stability = stable_convergence(rounds, clients)
    sent = sum(int(r["bytes_sent"]) for r in rounds)
    received = sum(int(r["bytes_received"]) for r in rounds)
    report = {
        "role": role, "condition": condition, "mu": mu, "experiment_id": experiment_id,
        "manifest_id": cond["manifest"], "manifest_sha256": manifest_sha,
        "config_sha256": config_sha, "round_0_state_sha256": initial_sha,
        "round_0_validation": metrics0, "best_round": best_round, "best_validation": best_metrics,
        "round_50_validation_AUPRC": rounds[-1]["validation_AUPRC"],
        "round_50_validation": next(r for r in rounds if int(r["round"]) == total_rounds),
        "best_checkpoint": f"{CKPT_RELATIVE}/{ckpt_sub}/{experiment_id}_best.pt",
        "best_checkpoint_sha256": hash_file(best_path),
        "round_50_checkpoint": f"{CKPT_RELATIVE}/{ckpt_sub}/{experiment_id}_round{total_rounds}.pt",
        "round_50_checkpoint_sha256": hash_file(final_path),
        "client_updates": len(clients), "stability": stability, "aggregation_parity": parity,
        "site_local_train_diagnostics": diagnostics,
        "site_local_train_summary": {
            "defined_AUPRC_sites": len(defined), "undefined_AUPRC_sites": 8 - len(defined),
            "mean_AUPRC": float(np.mean(defined)) if defined else None,
            "label": "SITE_LOCAL_TRAIN_DIAGNOSTIC", "held_out_client_generalization_claim": False},
        "validation_patient_summary": {k: patient[k] for k in (
            "VALIDATION_PATIENT_MACRO_AUPRC_V2", "VALIDATION_PATIENT_WORST_AUPRC_V2",
            "finite_AUPRC_patients", "undefined_AUPRC_patients")},
        "communication": {
            "server_to_client_bytes_per_round": server_payload * 8,
            "client_to_server_bytes_per_round": int(sum(
                int(c["update_bytes"]) for c in clients[:8])),
            "total_logical_payload_bytes": sent + received, "network_traffic_measured": False},
        "wall_seconds": round(time.monotonic() - started, 1),
        "noise_fixtures": noise_fixtures,
        "nstdb_role": NSTDB_ROLE if cond["feature_noise"] else None,
        "CAL_V2_applied": False, "central_checkpoint_loaded_as_initialization": False,
        "status": "COMPLETE"}
    _write_json(out / "result.json", report)
    return report
