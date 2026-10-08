# ruff: noqa: E501
"""Writes the NHM_SYNTH_FL_EVAL_PROTOCOL_V1 protocol + holdout manifest. Computes NO model prediction (method-freeze step).
  python -m scripts.freeze_synth_fl_eval_protocol"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from final_showcase import LANE_LABEL
from final_showcase.holdout import (
    HOLDOUT_BASE_SEED,
    HOLDOUT_COHORT_ID,
    build_holdout_dataset,
    holdout_profiles,
    manifest_entry,
)
from simulation.fl_cohort_v1 import cohort_profiles

OUT = Path("configs/final_showcase")


def main() -> None:
    train = cohort_profiles()
    entries = [manifest_entry(p, build_holdout_dataset(p), i) for i, p in enumerate(holdout_profiles())]
    training_ids = {p.participant_id for p in train} | {p.session_id for p in train}
    held_ids = {e["participant_id"] for e in entries} | {e["session_id"] for e in entries}
    assert training_ids.isdisjoint(held_ids)
    assert not {p.seed for p in train} & {e["seed"] for e in entries}
    manifest = {"cohort_id": HOLDOUT_COHORT_ID, "base_seed": HOLDOUT_BASE_SEED, "label_contract": "WEARABLE_SIM_EVENT_WINDOW_V1",
                "generator": "simulation.fl_cohort_v1 (unmodified) via final_showcase.holdout", "participants": entries,
                "training_participants_excluded": sorted(p.participant_id for p in train), "training_seeds_excluded": sorted(p.seed for p in train)}
    (OUT / "synth_fl_eval_holdout_manifest_v1.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    manifest_sha = hashlib.sha256((OUT / "synth_fl_eval_holdout_manifest_v1.json").read_bytes()).hexdigest()
    protocol = {
        "protocol_id": "NHM_SYNTH_FL_EVAL_PROTOCOL_V1", "lane": "C — synthetic engineering FL (WEARABLE_SIM_EVENT_WINDOW_V1)", "boundary_label": LANE_LABEL,
        "non_clinical_boundary": "Synthetic engineering-event classification on simulated wearable windows. Not AAMI-SVF, not a diagnosis, not a clinical or device validation, not an efficacy claim for MODEL_V2_FINAL.",
        "target": "synthetic engineering event within the preceding 10 s of a QUALITY_V1-VALID 2500-sample window (label provider SyntheticEventLabelProvider)",
        "model": {"architecture": "MODEL_V2_FINAL parameters/state layout as used by FL (federated.model_v2_fl)", "round0": "FL_INIT_V2 = fresh_initial_state_v2(20260927)", "calibration": "NONE — CAL_V2 is not applied"},
        "evaluated_states": {"round_0": {"digest": "6a2923ca87793fb78571b4cffad4026f8b4ce99d9dfcb3abe885e259c68a572f", "source": "wearable_fl_runner_v1.new_session()"},
                             "round_1": {"digest": "40cee0654e1a05eb76f3e6a4d177be1953add71b7fcdad07c6e8d8f2d974c0a1", "source": "canonical run round-1 checkpoint"},
                             "round_2": {"digest": "6237c0b1752c58daedcbd6e9456ab349c35318d513e706bd8bec36941ee7d2ef", "source": "canonical run round-2 checkpoint"},
                             "round_3_candidate": {"digest": "3f0b7762ae7e05f21eb1709521404ed4d7968cae34f89e1797a0cbabd47c70e4", "source": "canonical sandbox candidate"}},
        "digest_authority": "reports/model_v2/v2_fl_005/federation_run.json (frozen). Any state whose recomputed digest differs aborts the evaluation (no substitution).",
        "live_linked_candidate": "evaluated separately, on the SAME frozen holdout, only if its own run digest/candidate digest are recorded; never merged with the canonical rows",
        "training_cohort": {"cohort_id": "WEARABLE_SIM_FL_COHORT_V1", "base_seed": 20260927, "clients": 8, "rounds": 3, "algorithm": "FEDAVG", "local": "AdamW lr 0.001 wd 0.0001 batch 64, 1 epoch, pos_weight 1.7157717177396683"},
        "holdout": {"manifest_file": "configs/final_showcase/synth_fl_eval_holdout_manifest_v1.json", "manifest_sha256": manifest_sha, "cohort_id": HOLDOUT_COHORT_ID,
                    "base_seed": HOLDOUT_BASE_SEED, "participants": [e["participant_id"] for e in entries], "windows_per_participant": 93,
                    "total_trainable_windows": sum(e["counts"]["trainable"] for e in entries), "mirrors": "eight frozen site conditions (faults, context, coverage, heart-rate convention); events re-drawn"},
        "separation_rules": ["no holdout participant_id equals a training participant_id", "no holdout session_id equals a training session_id", "no holdout seed equals a training seed",
                             "no holdout window input digest equals any training window input digest", "holdout windows never enter any LocalTrainingBuffer or optimizer step"],
        "eligibility": "a window is evaluated iff trainable per federated.virtual_client_source_v1.is_trainable (VALID, 2500 samples, no missing slots, finite); DEGRADED/UNUSABLE windows are excluded exactly as in training",
        "labels": "WEARABLE_SIM_EVENT_WINDOW_V1 positive iff a scheduled synthetic event lies in [t-10 s, t]", "preprocessing": "per-window z-score exactly as the training dataset builder (normalize_windows)",
        "decision_threshold": {"rule": "positive iff raw sigmoid(logit) >= 0.5", "predeclared": True, "tuned": False, "calibrated": False},
        "metrics": ["AUPRC", "AUROC", "F1", "accuracy", "precision", "recall", "specificity", "balanced_accuracy", "TP", "FP", "TN", "FN", "false_positive_rate", "false_negative_rate",
                    "negative_predictive_value", "windows", "positives", "negatives", "prevalence", "BCE", "participant_macro_F1"],
        "metric_definitions": {"AUPRC": "sklearn average_precision_score (non-interpolated)", "AUROC": "sklearn roc_auc_score", "F1": "2TP/(2TP+FP+FN)", "BCE": "mean unweighted binary cross-entropy from logits",
                               "participant_macro_F1": "mean of per-participant F1 over participants with defined F1; undefined count reported"},
        "undefined_policy": "a metric whose denominator is zero or whose classes are missing is reported as null with an explicit reason (UNDEFINED); never replaced by 0",
        "views": ["pooled", "per participant/site", "round evolution 0→3", "initial vs final", "secondary: training-buffer windows (labelled training-data metrics, not generalisation)"],
        "uncertainty": {"method": "participant-cluster percentile bootstrap", "replicates": 2000, "seed": 20261101, "clusters": 8, "status": "NOMINAL ONLY — 8 clusters; interval is unstable and is not a significance claim"},
        "forbidden": ["retraining", "threshold optimisation", "CAL_V2", "holdout-informed selection or cherry-picking", "restricted clinical datasets", "hardware"],
        "reproduce": ["python -m scripts.freeze_synth_fl_eval_protocol  # regenerates this protocol + manifest byte-identically",
                      "python -m scripts.run_synth_fl_eval --out reports/final_showcase/synth_fl_eval"],
        "outcome_policy": "all outcomes are reported as measured, including poor ones",
    }
    (OUT / "synth_fl_eval_protocol_v1.json").write_text(json.dumps(protocol, indent=1, sort_keys=True) + "\n")
    print("manifest", manifest_sha)
    print("protocol", hashlib.sha256((OUT / "synth_fl_eval_protocol_v1.json").read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
