#!/usr/bin/env python3
"""Fresh-process verification of the four V2-FL-002 results: manifest reconstruction against the
frozen hashes, round-1 replay from FL_INIT_V2 (identical global-state SHA), best-round
recomputation from the saved round log, checkpoint reload and exact VALIDATION-prediction replay.
Usage: python -m scripts.verify_v2_fl_002_replay <run_label>"""

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
from federated.model_v2_fl import (
    fresh_initial_state_v2,
    fresh_model_v2,
    set_determinism,
    state_sha,
    train_local_epoch_v2,
)
from federated.model_v2_non_iid_runner import (
    CONFIG_RELATIVE,
    ORDER,
    guarded_noise_bank,
    guarded_population,
)
from federated.non_iid_runner import load_sites
from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_fl_002"


def verify_condition(label: str, condition: str, config: dict) -> dict:
    cond = config["conditions"][condition]
    result = json.loads((OUT / f"{condition}_result.json").read_text())
    with (OUT / f"{condition}_round_log.csv").open(newline="") as handle:
        rounds = list(csv.DictReader(handle))
    manifest_path = ROOT / "manifests/clients" / f"{cond['manifest']}.csv"
    sites = load_sites(manifest_path)
    seed = int(config["initialization"]["seed"])
    set_determinism(seed)
    tag = f"replay_{label}_{condition}"
    train = guarded_population(ROOT, "TRAIN", tag)
    validation = guarded_population(ROOT, "VALIDATION", tag)
    clean = normalized_population(train)
    inputs = clean
    if cond["feature_noise"]:
        group_to_site = {g: s for s, groups in sites.items() for g in groups}
        site_for_example = {str(e): group_to_site[str(g)] for e, g in zip(
            train.example_ids, train.participant_group_ids, strict=True)}
        inputs, _ = transform_population(np.asarray(train.waveforms, dtype=np.float64),
                                         train.example_ids, site_for_example,
                                         guarded_noise_bank(ROOT, tag))
    pos_weight = float(np.sum(train.labels == 0) / np.sum(train.labels == 1))
    initial = fresh_initial_state_v2(seed)
    updates = []
    for site in SITE_IDS:
        idx = np.flatnonzero(np.isin(train.participant_group_ids, sites[site]))
        updates.append(train_local_epoch_v2(
            global_state=initial, inputs=inputs[idx], labels=train.labels[idx], site_id=site,
            round_number=1, experiment_id=config["shuffle_seed_namespace"], base_seed=seed,
            batch_size=64, learning_rate=0.001, weight_decay=0.0001, pos_weight=pos_weight
        ).update)
    replay_state, _ = aggregate_weighted_deltas(initial, updates)
    round1_ok = state_sha(replay_state) == rounds[1]["global_state_sha256"]
    payload = torch.load(ROOT / result["best_checkpoint"], map_location="cpu",
                         weights_only=False)
    model = fresh_model_v2()
    restore_state(model, {k: v.numpy().copy() for k, v in payload["state_dict"].items()})
    _, logits, probs = evaluate_model(
        model, normalized_population(validation), validation.labels,
        validation.participant_group_ids, pos_weight=pos_weight, partition="VALIDATION")
    with (OUT / f"{condition}_validation_predictions.csv").open(newline="") as handle:
        stored = list(csv.DictReader(handle))
    exact = len(stored) == len(logits) and all(
        r["raw_logit"] == format(float(x), ".17g")
        and r["raw_sigmoid_probability"] == format(float(p), ".17g")
        for r, x, p in zip(stored, logits, probs, strict=True))
    data = {
        "condition": condition, "round_0_state_sha256_is_FL_INIT_V2": rounds[0][
            "global_state_sha256"] == config["initialization"]["round_0_state_sha256"],
        "round_1_replay_sha256": state_sha(replay_state),
        "round_1_stored_sha256": rounds[1]["global_state_sha256"], "round_1_identical": round1_ok,
        "best_round_recomputed": choose_best_round(rounds),
        "best_round_recorded": result["best_round"],
        "best_checkpoint_round": int(payload["round"]),
        "best_checkpoint_sha_matches": hash_file(ROOT / result["best_checkpoint"]) == result[
            "best_checkpoint_sha256"],
        "round_50_checkpoint_sha_matches": hash_file(ROOT / result["round_50_checkpoint"])
        == result["round_50_checkpoint_sha256"],
        "manifest_sha_matches_frozen": hash_file(manifest_path) == cond["manifest_sha256"],
        "validation_predictions_replayed_identically": bool(exact)}
    data["status"] = "PASS" if (
        data["round_0_state_sha256_is_FL_INIT_V2"] and round1_ok
        and data["best_round_recomputed"] == data["best_round_recorded"]
        == data["best_checkpoint_round"] and data["best_checkpoint_sha_matches"]
        and data["round_50_checkpoint_sha_matches"] and data["manifest_sha_matches_frozen"]
        and exact) else "FAIL"
    return data


def main() -> None:
    label = sys.argv[1] if len(sys.argv) > 1 else "run"
    config = yaml.safe_load((ROOT / CONFIG_RELATIVE).read_text())
    results = [verify_condition(label, c, config) for c in ORDER]
    report = {"run_label": label, "conditions": results,
              "status": "PASS" if all(r["status"] == "PASS" for r in results) else "FAIL"}
    (OUT / f"replay_verification_{label}.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"label": label, "status": report["status"]}))


if __name__ == "__main__":
    main()
