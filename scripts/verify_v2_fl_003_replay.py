#!/usr/bin/env python3
"""Fresh-process verification of V2-FL-003: mu=0 round-1 aggregate re-run, selection recomputed
twice against the frozen lock, every candidate/transfer run's best-round reconstruction, round-1
replay from FL_INIT_V2 (identical global-state SHA), checkpoint hashes and exact VALIDATION
prediction replay. Usage: python -m scripts.verify_v2_fl_003_replay <run_label>"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np
import torch
import yaml

from federated.aggregation import aggregate_weighted_deltas
from federated.client_manifest import SITE_IDS
from federated.evaluation import evaluate_model
from federated.feature_noise import transform_population
from federated.fedavg_runner import choose_best_round, normalized_population
from federated.model_adapter import restore_state
from federated.model_v2_fedprox import CANDIDATES, WORST_ID, select_mu, train_local_fedprox_epoch_v2
from federated.model_v2_fedprox_runner import (
    CONFIG_RELATIVE,
    guarded_noise_bank,
    guarded_population,
    mu_token,
    run_key,
)
from federated.model_v2_fl import fresh_initial_state_v2, fresh_model_v2, set_determinism, state_sha
from federated.non_iid_runner import load_sites
from nhm.hashing import hash_file
from scripts.select_v2_fedprox_mu import load_rows

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_fl_003"


def verify_run(label: str, condition: str, mu: float, role: str, config: dict, cache: dict) -> dict:
    cond = config["conditions"][condition]
    _, sub, _ = run_key(condition, mu, role)
    result = json.loads((OUT / sub / "result.json").read_text())
    with (OUT / sub / "round_log.csv").open(newline="") as handle:
        rounds = list(csv.DictReader(handle))
    tag = f"replay_{label}_{sub.replace('/', '_')}"
    seed = int(config["initialization"]["seed"])
    set_determinism(seed)
    if "train" not in cache:
        cache["train"] = guarded_population(ROOT, "TRAIN", tag)
        cache["validation"] = guarded_population(ROOT, "VALIDATION", tag)
        cache["clean"] = normalized_population(cache["train"])
        cache["val_inputs"] = normalized_population(cache["validation"])
    train, validation = cache["train"], cache["validation"]
    manifest_path = ROOT / "manifests/clients" / cond["path"]
    sites = load_sites(manifest_path)
    inputs = cache["clean"]
    if cond["feature_noise"]:
        key = ("noise", cond["manifest"])
        if key not in cache:
            group_to_site = {g: s for s, groups in sites.items() for g in groups}
            site_for_example = {str(e): group_to_site[str(g)] for e, g in zip(
                train.example_ids, train.participant_group_ids, strict=True)}
            cache[key], _ = transform_population(
                np.asarray(train.waveforms, dtype=np.float64), train.example_ids,
                site_for_example, guarded_noise_bank(ROOT, tag))
        inputs = cache[key]
    pos_weight = float(np.sum(train.labels == 0) / np.sum(train.labels == 1))
    initial = fresh_initial_state_v2(seed)
    updates = []
    for site in SITE_IDS:
        idx = np.flatnonzero(np.isin(train.participant_group_ids, sites[site]))
        updates.append(train_local_fedprox_epoch_v2(
            global_state=initial, inputs=inputs[idx], labels=train.labels[idx], site_id=site,
            round_number=1, experiment_id=config["shuffle_seed_namespace"], base_seed=seed,
            batch_size=64, learning_rate=0.001, weight_decay=0.0001, pos_weight=pos_weight,
            mu=mu).update)
    replay_state, _ = aggregate_weighted_deltas(initial, updates)
    payload = torch.load(ROOT / result["best_checkpoint"], map_location="cpu",
                         weights_only=False)
    model = fresh_model_v2()
    restore_state(model, {k: v.numpy().copy() for k, v in payload["state_dict"].items()})
    _, logits, probs = evaluate_model(
        model, cache["val_inputs"], validation.labels, validation.participant_group_ids,
        pos_weight=pos_weight, partition="VALIDATION")
    with (OUT / sub / "validation_predictions.csv").open(newline="") as handle:
        stored = list(csv.DictReader(handle))
    exact = len(stored) == len(logits) and all(
        r["raw_logit"] == format(float(x), ".17g")
        and r["raw_sigmoid_probability"] == format(float(p), ".17g")
        for r, x, p in zip(stored, logits, probs, strict=True))
    data = {
        "run": sub, "mu": mu,
        "round_0_is_FL_INIT_V2": rounds[0]["global_state_sha256"] == config["initialization"][
            "round_0_state_sha256"],
        "round_1_replay_sha256": state_sha(replay_state),
        "round_1_stored_sha256": rounds[1]["global_state_sha256"],
        "round_1_identical": state_sha(replay_state) == rounds[1]["global_state_sha256"],
        "best_round_recomputed": choose_best_round(rounds),
        "best_round_recorded": result["best_round"], "best_checkpoint_round": int(
            payload["round"]),
        "best_checkpoint_sha_matches": hash_file(ROOT / result["best_checkpoint"]) == result[
            "best_checkpoint_sha256"],
        "round_50_checkpoint_sha_matches": hash_file(ROOT / result["round_50_checkpoint"])
        == result["round_50_checkpoint_sha256"],
        "manifest_sha_matches_frozen": hash_file(manifest_path) == cond["sha256"],
        "validation_predictions_replayed_identically": bool(exact)}
    data["status"] = "PASS" if (
        data["round_0_is_FL_INIT_V2"] and data["round_1_identical"]
        and data["best_round_recomputed"] == data["best_round_recorded"]
        == data["best_checkpoint_round"] and data["best_checkpoint_sha_matches"]
        and data["round_50_checkpoint_sha_matches"] and data["manifest_sha_matches_frozen"]
        and exact) else "FAIL"
    return data


def mu0_rerun(config: dict, cache: dict) -> dict:
    """Re-run the mu=0 LABEL round-1 aggregate in this fresh process (mandatory repeat)."""
    train = cache["train"]
    sites = load_sites(ROOT / "manifests/clients/NONIID_LABEL_V1.csv")
    seed = int(config["initialization"]["seed"])
    set_determinism(seed)
    initial = fresh_initial_state_v2(seed)
    pos_weight = float(np.sum(train.labels == 0) / np.sum(train.labels == 1))
    updates = []
    for site in SITE_IDS:
        idx = np.flatnonzero(np.isin(train.participant_group_ids, sites[site]))
        updates.append(train_local_fedprox_epoch_v2(
            global_state=initial, inputs=cache["clean"][idx], labels=train.labels[idx],
            site_id=site, round_number=1, experiment_id=config["shuffle_seed_namespace"],
            base_seed=seed, batch_size=64, learning_rate=0.001, weight_decay=0.0001,
            pos_weight=pos_weight, mu=0.0).update)
    aggregate, _ = aggregate_weighted_deltas(initial, updates)
    stored = config["label_fedavg_baseline"]["round_1_state_sha256"]
    return {"fedprox_mu0_round_1_sha256": state_sha(aggregate), "stored_FedAvg_sha256": stored,
            "exact_match": state_sha(aggregate) == stored}


def main() -> None:
    label = sys.argv[1] if len(sys.argv) > 1 else "run"
    config = yaml.safe_load((ROOT / CONFIG_RELATIVE).read_text())
    lock = json.loads((ROOT / "artifacts/FEDPROX_MU_V2.lock.json").read_text())
    baseline = config["label_fedavg_baseline"][WORST_ID]
    selections = [select_mu(load_rows(), baseline)["selected_mu"] for _ in range(2)]
    cache: dict = {}
    runs = [verify_run(label, "label", mu, "candidate", config, cache) for mu in CANDIDATES]
    runs += [verify_run(label, c, lock["selected_mu"], "transfer", config, cache)
             for c in config["transfer_order"]]
    mu0 = json.loads((OUT / "mu0_equivalence.json").read_text())
    mu0_repeat = mu0_rerun(config, cache)
    report = {
        "run_label": label, "selection_recomputed_twice": selections,
        "selection_matches_lock": all(s == lock["selected_mu"] for s in selections),
        "mu0_round_1_aggregate_matches_V2_FL_002_label": mu0["C_round_1_aggregate"][
            "fedprox_mu0_round_1_sha256"] == config["label_fedavg_baseline"][
                "round_1_state_sha256"],
        "mu0_repeat_in_fresh_process": mu0_repeat, "runs": runs,
        "status": "PASS" if (all(r["status"] == "PASS" for r in runs) and mu0_repeat["exact_match"]
                             and all(s == lock["selected_mu"] for s in selections)) else "FAIL"}
    (OUT / f"replay_verification_{label}.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"label": label, "status": report["status"], "mu_token": mu_token(
        lock["selected_mu"])}))


if __name__ == "__main__":
    main()
