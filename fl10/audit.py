# ruff: noqa: E501
"""Read-only integrity audit helpers for FL10 (nothing here trains, tunes or re-evaluates a model)."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score

from fl10.evaluate import ROOT, STATES


def seed_overlap(holdout_seeds: list[int], excluded_seeds: list[int]) -> list[int]:
    return sorted(set(holdout_seeds) & set(excluded_seeds))


def reconcile(eval_dir: Path) -> dict[str, Any]:
    """Recompute confusion counts / AUPRC / AUROC / Brier from the committed prediction table and compare with the stored results (all 11 states)."""
    results = json.loads((eval_dir / "evaluation_results.json").read_text())
    rows = list(csv.DictReader((eval_dir / "holdout_predictions.csv").open()))
    y = np.array([int(r["label"]) for r in rows])
    out: dict[str, Any] = {"windows": len(rows), "states": {}}
    for s in STATES:
        z = np.array([float(r[f"logit_{s}"]) for r in rows])
        p = 1 / (1 + np.exp(-z))
        pred = (p >= 0.5).astype(int)
        tp, fp = int(((y == 1) & (pred == 1)).sum()), int(((y == 0) & (pred == 1)).sum())
        tn, fn = int(((y == 0) & (pred == 0)).sum()), int(((y == 1) & (pred == 0)).sum())
        st = results["states"][s]["pooled"]
        part = results["states"][s]["participants"]
        out["states"][s] = {"confusion_equals_stored": [tp, fp, tn, fn] == [st["TP"], st["FP"], st["TN"], st["FN"]], "rows_reconcile": tp + fn == st["positives"] and tn + fp == st["negatives"] and tp + fp + tn + fn == len(rows),
                            "ranking_equals_stored": abs(average_precision_score(y, p) - st["AUPRC"]) < 1e-9 and abs(roc_auc_score(y, p) - st["AUROC"]) < 1e-9, "brier_equals_stored": abs(float(np.mean((p - y) ** 2)) - st["Brier"]) < 1e-7,
                            "participants_sum_to_pooled": [sum(v[m] for v in part.values()) for m in ("TP", "FP", "TN", "FN")] == [tp, fp, tn, fn]}
    out["all_ok"] = all(all(v.values()) for v in out["states"].values())
    return out


def baseline_unchanged(baseline_path: Path = Path("reports/fl10/baseline_hashes.json")) -> dict[str, list[str]]:
    """Every lock and protected file recorded before the experiment must still be byte-identical (historical locks are never edited)."""
    base = json.loads((ROOT / baseline_path).read_text())
    changed = [p for group in ("locks", "protected_files") for p, d in base[group].items() if hashlib.sha256((ROOT / p).read_bytes()).hexdigest() != d]
    return {"changed": changed}
