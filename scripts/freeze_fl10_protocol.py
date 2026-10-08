# ruff: noqa: E501
"""Write NHM_FL10_SYNTHETIC_EVALUATION_V1 (protocol) and the fresh 16-participant holdout manifest. Computes NO model prediction (method-freeze step).
  python -m scripts.freeze_fl10_protocol"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from federated.wearable_fl_runner_v1 import build_cohort
from final_showcase import LANE_LABEL
from final_showcase import holdout as previous
from fl10 import EXPERIMENT_ID, LIVE_LABEL, PROTOCOL_ID, holdout, metrics
from fl10.evaluate import window_hashes
from fl10.inventory import FIGURES, METRIC_DEFINITIONS, TABLES
from simulation.fl_cohort_v1 import cohort_profiles

OUT = Path("configs/fl10")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    train_profiles = cohort_profiles()
    prev_profiles = previous.holdout_profiles()
    profiles = holdout.profiles()
    datasets = [holdout.build_dataset(p) for p in profiles]
    _, training, _ = build_cohort()
    prev_sets = [previous.build_holdout_dataset(p) for p in prev_profiles]
    seeds = [p.seed for p in profiles]
    excluded_ids = {p.participant_id for p in (*train_profiles, *prev_profiles)} | {p.session_id for p in (*train_profiles, *prev_profiles)}
    held = {p.participant_id for p in profiles} | {p.session_id for p in profiles}
    assert excluded_ids.isdisjoint(held) and len(set(seeds)) == 16
    assert not set(seeds) & {p.seed for p in (*train_profiles, *prev_profiles)}
    held_w = set().union(*(window_hashes(d) for d in datasets))
    assert not held_w & set().union(*(window_hashes(d) for d in (*training, *prev_sets)))
    entries = [holdout.manifest_entry(p, d, k) for k, (p, d) in enumerate(zip(profiles, datasets, strict=True))]
    manifest = {"cohort_id": holdout.COHORT_ID, "base_seed": holdout.BASE_SEED, "label_contract": "WEARABLE_SIM_EVENT_WINDOW_V1", "generator": "simulation.fl_cohort_v1 (unmodified) via fl10.holdout", "participants": entries,
                "excluded_training_participants": sorted(p.participant_id for p in train_profiles), "excluded_previous_holdout_participants": sorted(p.participant_id for p in prev_profiles)}
    mpath = OUT / "holdout_manifest_v1.json"
    mpath.write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    msha = hashlib.sha256(mpath.read_bytes()).hexdigest()
    protocol = {
        "protocol_id": PROTOCOL_ID, "experiment_id": EXPERIMENT_ID, "predecessor": {"id": "NHM_FINAL_SHOWCASE_001", "commit": "274323730d1c7355f688ad4c9ff01ecbfb746501"},
        "lane": "C - synthetic engineering FL (WEARABLE_SIM_EVENT_WINDOW_V1)", "boundary_label": LANE_LABEL, "live_label": LIVE_LABEL,
        "research_question": "How does increasing the number of federated communication rounds from three to ten affect optimization behaviour, ranking discrimination and fixed-threshold classification on an independent synthetic engineering-event cohort?",
        "non_clinical_boundary": "Synthetic engineering-event classification on simulated wearable windows. Not AAMI-SVF, not a diagnosis, not clinical/device validation. The scientific real-ECG FL results are separate and unchanged.",
        "training": {"clients": 8, "rounds": 10, "accepted_updates_per_round": 8, "expected_total_accepted_updates": 80, "local_epochs": 1, "aggregation": "weighted FedAvg (federated.wearable_fl_system_v1.Coordinator)",
                     "initial_state": "FL_INIT_V2 (R0 digest 6a2923ca87793fb78571b4cffad4026f8b4ce99d9dfcb3abe885e259c68a572f)", "cohort": "WEARABLE_SIM_FL_COHORT_V1 (existing eight synthetic clients)",
                     "settings": "frozen: AdamW lr 0.001 wd 0.0001 batch 64 pos_weight 1.7157717177396683 base seed 20260927", "note": "same trainable windows are revisited every round: example exposures are repeated, not independent",
                     "prefix_parity": {"R1": "40cee0654e1a05eb76f3e6a4d177be1953add71b7fcdad07c6e8d8f2d974c0a1", "R2": "6237c0b1752c58daedcbd6e9456ab349c35318d513e706bd8bec36941ee7d2ef", "R3": "3f0b7762ae7e05f21eb1709521404ed4d7968cae34f89e1797a0cbabd47c70e4",
                                       "rule": "Mode A must reproduce R0-R3 exactly or training stops; no seed or parameter changes"},
                     "modes": {"A": "canonical eight-client synthetic cohort", "B": "live-monitored SITE_00 (one monitoring session, one verified buffer reused for all ten rounds) + seven synthetic peers"},
                     "expected_example_exposures": "723 trainable windows x 10 rounds = 7230 repeated exposures (recomputed from execution evidence, not taken from this line)"},
        "holdout": {"cohort_id": holdout.COHORT_ID, "manifest_file": "configs/fl10/holdout_manifest_v1.json", "manifest_sha256": msha, "participants": [e["participant_id"] for e in entries], "participant_count": 16,
                    "design": "two independent profiles for each of the eight established site conditions", "base_seed": holdout.BASE_SEED, "seeds": seeds, "sessions": [e["session_id"] for e in entries],
                    "total_trainable_windows": sum(e["counts"]["trainable"] for e in entries), "total_positive": sum(e["counts"]["synthetic_positive"] for e in entries),
                    "excluded_windows_by_reason": {"DEGRADED": sum(e["counts"]["DEGRADED"] for e in entries), "UNUSABLE": sum(e["counts"]["UNUSABLE"] for e in entries)},
                    "never_enters_training": True, "modified_after_predictions": False},
        "separation_rules": ["no participant id, session id or seed equals any training client, previous-holdout participant or live-session identity", "no holdout window input digest equals any training, previous-holdout or live-monitored window",
                             "participant boundaries are preserved: resampling is by participant cluster"],
        "eligibility": "trainable per federated.virtual_client_source_v1.is_trainable (VALID, 2500 samples, no missing slots, finite); excluded windows are counted and reported",
        "labels": "WEARABLE_SIM_EVENT_WINDOW_V1: positive iff a scheduled synthetic engineering event lies in [t-10 s, t]", "preprocessing": "per-window z-score exactly as the training dataset builder",
        "decision_threshold": {"rule": "positive iff raw sigmoid(logit) >= 0.5", "predeclared": True, "tuned": False, "calibrated": False, "CAL_V2": "NOT APPLIED"},
        "states_evaluated": [f"R{r:02d}" for r in range(11)], "primary_comparison": {"comparator": "R03", "endpoint": "R10", "rule": "R10 is the predetermined endpoint regardless of performance; no best-round selection"},
        "descriptive": "R00 is the initial reference; R01-R09 are descriptive training-duration trajectories", "previously_exposed_holdout": "shown only in a separate historical panel labelled PREVIOUSLY EXPOSED SYNTHETIC EVALUATION; never used for decisions",
        "metrics": {"global": ["AUPRC", "AUROC", "F1", "accuracy", "precision", "recall", "specificity", "balanced_accuracy", "negative_predictive_value", "false_positive_rate", "false_negative_rate", "false_discovery_rate",
                               "false_omission_rate", "MCC", "TP", "FP", "TN", "FN", "total_predictions", "predicted_positives", "predicted_negatives", "windows", "positives", "negatives", "prevalence", "BCE", "Brier",
                               "mean_predicted_probability", "mean_score_positive_class", "mean_score_negative_class", "score_min", "score_max", "score_quantiles"],
                    "participant_level": ["AUPRC", "AUROC", "F1", "precision", "recall", "specificity", "TP", "FP", "TN", "FN", "participant_macro_F1"], "definitions": {k: {"definition": v[0], "undefined_when": v[1]} for k, v in METRIC_DEFINITIONS.items()},
                    "undefined_policy": "a metric whose denominator is zero or whose classes are missing is reported as null/UNDEFINED with a reason, never zero", "score_quantiles": list(metrics.QUANTILES),
                    "probability_histogram": {"bins": metrics.HIST_BINS, "range": [0.0, 1.0], "predeclared": True}},
        "uncertainty": {"method": "paired participant-cluster percentile bootstrap (one draw applied to both states; difference = R10 - R03)", "replicates": 2000, "seed": 20261201, "clusters": 16, "status": "NOMINAL ONLY",
                        "metrics": list(metrics.PAIRED_METRICS), "multiplicity": "none; no significance claim; undefined replicates are counted, never redrawn"},
        "interpretation_boundaries": ["improvement in ranking does not imply usable classification at the fixed threshold", "16 independent synthetic participants: all intervals are nominal", "a negative or flat result is a valid completed experiment",
                                      "no extra training run, round selection or threshold change is permitted after seeing results"],
        "figure_inventory": [{"id": i, "title": t, "group": g} for i, t, g in FIGURES], "table_inventory": [{"id": i, "title": t} for i, t in TABLES],
        "export_schema": {"figure": ["svg", "png_300dpi", "csv_source_data", "json_provenance"], "table": ["csv", "json", "md"], "unrounded_values_in_machine_readable_outputs": True},
        "forbidden": ["modifying MODEL_V2_FINAL, FL_INIT_V2, scientific checkpoints, CAL_V2, FedAvg/FedProx math", "re-freezing an accepted lock in place", "threshold optimisation", "hardware", "new clinical data", "automatic push"],
        "reproduce": ["python -m scripts.freeze_fl10_protocol", "python -m scripts.run_fl10 --mode A --out reports/fl10/runs/modeA", "python -m scripts.run_fl10 --mode B --out reports/fl10/runs/modeB",
                      "python -m scripts.evaluate_fl10 --method-commit <sha>", "python -m fl10.figures"]}
    ppath = OUT / "protocol_v1.json"
    ppath.write_text(json.dumps(protocol, indent=1, sort_keys=True) + "\n")
    print("manifest", msha)
    print("protocol", hashlib.sha256(ppath.read_bytes()).hexdigest())
    print("holdout windows", protocol["holdout"]["total_trainable_windows"], "positives", protocol["holdout"]["total_positive"])


if __name__ == "__main__":
    main()
