# ruff: noqa: E501
"""Reproduces the realistic-cohort comparison on the 16-participant realistic evaluation cohort, all at the fixed rule sigmoid(logit) >= 0.5:

* prevalence, and two logistic baselines fitted on the 8-client training cohort only (6 amplitude features; R-peak timing features),
* the pretrained V2 with no training, and
* a 10-round FedAvg run from the pretrained V2 on the 8 realistic clients.

    PYTHONPATH=src:. python -m scripts.realistic_cohort_experiment [--out PATH]

Engineering demonstration on synthetic data; nothing here is a clinical claim."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
from scipy.signal import find_peaks
from scipy.stats import kurtosis
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score

from fl10 import runner
from fl10.runner import load_state
from simulation import fl_cohort_realistic_v2 as cohort
from studio import v2_init
from studio.isolated_eval import isolated_logits

SAMPLE_HZ = 250.0


def amplitude_features(x: np.ndarray) -> np.ndarray:
    step = np.diff(x, axis=1)
    return np.column_stack([np.abs(x).max(1), x.max(1) - x.min(1), kurtosis(x, axis=1), np.abs(step).max(1), (np.abs(x) > 3).mean(1), np.abs(x).argmax(1) / x.shape[1]])


def timing_features(x: np.ndarray) -> np.ndarray:
    rows = []
    for window in x:
        peak = float(np.max(np.abs(window)))
        found, _ = find_peaks(np.abs(window), height=0.5 * peak if peak > 0 else 1.0, distance=int(0.30 * SAMPLE_HZ))
        rr = np.diff(found) / SAMPLE_HZ
        if len(rr) < 3:
            rows.append([1.0, 1.0, 0.0, 0.0, float(len(found))])
            continue
        median = float(np.median(rr))
        rows.append([rr.min() / median, rr.max() / median, float((rr < 0.8 * median).sum()), float(np.std(rr) / median), float(len(found))])
    return np.asarray(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="reports/realistic/realistic_cohort_experiment.json")
    target = Path(parser.parse_args().out)

    train = [cohort.build_dataset(p) for p in cohort.train_profiles()]
    evaluation = [cohort.build_dataset(p) for p in cohort.eval_profiles()]
    flat = lambda d: d.inputs.reshape(len(d.inputs), -1)  # noqa: E731
    x_train, y_train = np.concatenate([flat(d) for d in train]), np.concatenate([d.labels for d in train]).astype(int)
    x_eval, y_eval = np.concatenate([flat(d) for d in evaluation]), np.concatenate([d.labels for d in evaluation]).astype(int)
    owners = np.concatenate([[d.participant_id] * len(d.labels) for d in evaluation])
    inputs = x_eval.reshape(len(x_eval), 1, -1) if evaluation[0].inputs.ndim == 3 else x_eval
    print(f"train {len(y_train)} windows ({y_train.sum()} positive) | evaluation {len(y_eval)} windows ({y_eval.sum()} positive, prevalence {y_eval.mean():.3f})")

    results: dict[str, Any] = {"prevalence": float(y_eval.mean()), "always_positive_F1": float(2 * y_eval.mean() / (1 + y_eval.mean()))}

    def score(name: str, logits: np.ndarray) -> None:
        probability = 1 / (1 + np.exp(-np.clip(logits, -60, 60)))
        predicted = (probability >= 0.5).astype(int)
        tp, fp = int(((predicted == 1) & (y_eval == 1)).sum()), int(((predicted == 1) & (y_eval == 0)).sum())
        fn, tn = int(((predicted == 0) & (y_eval == 1)).sum()), int(((predicted == 0) & (y_eval == 0)).sum())
        f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0
        per = [roc_auc_score(y_eval[owners == pid], logits[owners == pid]) for pid in sorted(set(owners)) if len(set(y_eval[owners == pid])) == 2]
        row = {"AUROC": float(roc_auc_score(y_eval, logits)), "AUPRC": float(average_precision_score(y_eval, logits)), "F1": f1, "TP": tp, "FP": fp, "TN": tn, "FN": fn, "mean_per_participant_AUROC": float(np.mean(per)), "participants_scored": len(per)}
        results[name] = row
        print(f"{name:42s} AUROC {row['AUROC']:.3f}  AUPRC {row['AUPRC']:.3f}  F1 {f1:.3f}  TP/FP/TN/FN {tp}/{fp}/{tn}/{fn}  per-participant AUROC {row['mean_per_participant_AUROC']:.3f} (n={len(per)})")

    for name, features in (("logistic: 6 amplitude features", amplitude_features), ("logistic: R-peak timing features", timing_features)):  # type: tuple[str, Callable[[np.ndarray], np.ndarray]]
        a, b = features(x_train), features(x_eval)
        mean, spread = a.mean(0), a.std(0) + 1e-9
        p = LogisticRegression(max_iter=3000).fit((a - mean) / spread, y_train).predict_proba((b - mean) / spread)[:, 1]
        score(name, np.log(p / (1 - p + 1e-12) + 1e-12))

    state, audit = v2_init.load_v2_final()
    score("pretrained V2 (R00, no training)", isolated_logits(state, inputs))
    out = Path(tempfile.mkdtemp(prefix="realistic_fl_"))
    manifest = {d.client_id: {"participant_id": d.participant_id, "session_id": d.session_id, "dataset_sha": d.dataset_sha256} for d in train}
    report = runner.run_training(
        mode="H", run_id="REALISTIC-FL-EXPERIMENT", out_dir=out, datasets=train, manifest=manifest, rounds=10, require_prefix_parity=False, capture_batches=False, progress=None,
        git_commit="UNKNOWN", protocol_sha256="UNKNOWN", algorithm="FEDAVG", secagg_mode="PLAIN", initial_state=state, initialisation=audit,
    )
    for row in report["rounds"]:
        if row["round"] in (1, 3, 5, 10):
            score(f"FedAvg from pretrained V2, R{row['round']:02d}", isolated_logits(load_state(out, row["round"], row["global_state_sha256"]), inputs))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(results, indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
