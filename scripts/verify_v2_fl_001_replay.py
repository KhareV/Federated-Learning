#!/usr/bin/env python3
"""Fresh-process verification of the V2-FL-001 result: (1) FL_INIT_V2 reproduces the recorded
round-0 SHA, (2) the best round recomputed from round_log.csv equals the selected round, (3) the
best checkpoint reproduces the stored VALIDATION predictions exactly, (4) checkpoint hash. Usage:
python -m scripts.verify_v2_fl_001_replay <run_label>"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np
import torch

from federated.evaluation import evaluate_model
from federated.fedavg_runner import choose_best_round, normalized_population
from federated.model_adapter import restore_state
from federated.model_v2_fedavg_runner import guarded_population
from federated.model_v2_fl import fresh_initial_state_v2, fresh_model_v2, state_sha
from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_fl_001"


def main() -> None:
    label = sys.argv[1] if len(sys.argv) > 1 else "run"
    result = json.loads((OUT / "fl_iid_model_v2_result.json").read_text())
    with (OUT / "round_log.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    recomputed = choose_best_round(rows)
    best_path = ROOT / result["best_checkpoint"]
    payload = torch.load(best_path, map_location="cpu", weights_only=False)
    model = fresh_model_v2()
    restore_state(model, {k: v.numpy().copy() for k, v in payload["state_dict"].items()})
    validation = guarded_population(ROOT, "VALIDATION")  # firewall: VALIDATION only
    inputs = normalized_population(validation)
    pos_weight = float(result["best_validation"]["negatives"]) / float(
        result["best_validation"]["positives"])
    _, logits, probs = evaluate_model(model, inputs, validation.labels,
                                      validation.participant_group_ids,
                                      pos_weight=pos_weight, partition="VALIDATION")
    with (OUT / "validation_predictions_best_round.csv").open(newline="") as handle:
        stored = list(csv.DictReader(handle))
    exact = all(r["raw_logit"] == format(float(x), ".17g")
                and r["raw_sigmoid_probability"] == format(float(p), ".17g")
                for r, x, p in zip(stored, logits, probs, strict=True)) and len(stored) == len(logits)  # noqa: E501
    init_sha = state_sha(fresh_initial_state_v2(20260927))
    data = {
        "run_label": label, "best_round_recomputed": recomputed,
        "best_round_recorded": result["best_round"],
        "best_round_matches": recomputed == result["best_round"],
        "best_checkpoint_sha256": hash_file(best_path),
        "best_checkpoint_sha_matches_result": hash_file(best_path) == result[
            "best_checkpoint_sha256"],
        "validation_predictions_replayed_identically": bool(exact),
        "validation_windows": int(logits.size),
        "init_sha256_reproduced": init_sha == result["round_0_state_sha256"],
        "max_abs_probability_delta": float(np.max(np.abs(
            probs - np.array([float(r["raw_sigmoid_probability"]) for r in stored])))),
        "status": "PASS" if (recomputed == result["best_round"] and exact
                             and init_sha == result["round_0_state_sha256"]
                             and hash_file(best_path) == result["best_checkpoint_sha256"])
        else "FAIL"}
    (OUT / f"replay_verification_{label}.json").write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"label": label, "status": data["status"]}))


if __name__ == "__main__":
    main()
