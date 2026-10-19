# ruff: noqa: E501
"""Seed-robust validation of the realistic synthetic cohort result, and a forgetting probe on real ECG.

    PYTHONPATH=src:. python -m scripts.realistic_multiseed [--train-seeds 5] [--holdouts 6] [--rounds 10] [--out reports/realistic/multiseed.json] [--quick] [--no-real-probe]

WHY. The headline realistic-cohort numbers came from ONE training draw and ONE pinned evaluation draw. Raw AUPRC / F1 depend on the positive prevalence of the draw (AUPRC chance level = prevalence), and
the federated gain may be partly adaptation to the simulator. This script answers, with the same generator and the same unchanged federated engine: how stable are the pretrained-V2 result, two simple
baselines and the federated result across independently seeded training cohorts and independently seeded evaluation cohorts, reported with prevalence-aware metrics (lift = AUPRC / prevalence) and intervals?

DESIGN (fixed before running; nothing is tuned on a score)
* K training cohorts: 8 realistic clients each, cohort seed ``TRAIN_BASE_SEED + 1000*k`` (k = 0 is the pinned cohort).
* H evaluation cohorts: 16 participants each; h = 0 is the pinned evaluation cohort, the others are independent draws. Participant ids are disjoint from every training cohort by construction.
* Per training cohort: fit a 6-feature amplitude logistic and a beat-timing logistic on that cohort ONLY; run FedAvg from the pretrained V2 for ``--rounds`` rounds with the unchanged runner (plain aggregation).
* Scored cells: every (training cohort k, evaluation cohort h, model) with R0 (the pretrained V2, identical for every k), EVERY federated round R01..R<final> and both baselines, at the fixed 0.5 rule. All rounds are scored because a
  federated model can dip and recover between rounds; reporting only R3 and the final round would hide that.
* Intervals: percentile bootstrap over training cohorts and evaluation cohorts (both resampled with replacement). Cells share cohorts, so these are descriptive, not significance tests.
* Forgetting probe (``--real-probe``, needs the local MIT-BIH caches): the frozen V2 and every round are scored on the real MIT-BIH VALIDATION windows, loaded through the project's own guarded loader
  (``training.train_central.load_population``: only TRAIN / VALIDATION are allowed). VALIDATION was used for V2 model selection, so the ABSOLUTE numbers are optimistic; the quantity of interest is the CHANGE
  from the frozen V2 on identical windows, with a patient-group bootstrap. INTERNAL_TEST, CALIBRATION and the external sets are never touched, and the frozen access ledger is never written.

Engineering demonstration on synthetic data plus one diagnostic on real windows; no clinical claim."""

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

ROOT = Path(__file__).resolve().parents[1]
BASELINES = ("Amplitude logistic", "Beat-timing logistic")
METRICS = ("AUROC", "AUPRC", "lift", "F1")
SAMPLE_HZ = 250.0


# ---- metrics ---------------------------------------------------------------------------------------------------------------------------------------------------------------

def cell_metrics(logits: np.ndarray, labels: np.ndarray) -> dict[str, float]:
    """AUROC, AUPRC, prevalence, lift (AUPRC / prevalence: 1 = chance) and F1 at the fixed rule sigmoid(logit) >= 0.5."""
    y = np.asarray(labels).astype(int)
    z = np.asarray(logits, dtype=np.float64)
    prevalence = float(y.mean())
    predicted = (1 / (1 + np.exp(-np.clip(z, -60, 60))) >= 0.5).astype(int)
    tp, fp, fn = int(((predicted == 1) & (y == 1)).sum()), int(((predicted == 1) & (y == 0)).sum()), int(((predicted == 0) & (y == 1)).sum())
    ap = float(average_precision_score(y, z))
    return {"AUROC": float(roc_auc_score(y, z)), "AUPRC": ap, "prevalence": prevalence, "lift": ap / prevalence if prevalence else float("nan"), "F1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0, "n": int(y.size)}


def bootstrap_ci(matrix: np.ndarray, *, replicates: int = 4000, seed: int = 20271118, level: float = 0.95) -> tuple[float, float, float]:
    """(mean, lo, hi) of the grand mean of a (training cohorts x evaluation cohorts) matrix, resampling both axes with replacement. Deterministic for a fixed seed."""
    rng = np.random.default_rng(seed)
    k, h = matrix.shape
    means = np.empty(replicates)
    for i in range(replicates):
        means[i] = matrix[np.ix_(rng.integers(0, k, k), rng.integers(0, h, h))].mean()
    lo, hi = np.quantile(means, [(1 - level) / 2, 1 - (1 - level) / 2])
    return float(matrix.mean()), float(lo), float(hi)


def group_bootstrap_delta(labels: np.ndarray, groups: np.ndarray, base: np.ndarray, other: np.ndarray, *, replicates: int = 2000, seed: int = 20271118) -> dict[str, float]:
    """Change in AUROC / AUPRC of ``other`` minus ``base`` on identical windows, bootstrapping patient groups (the independent units)."""
    rng = np.random.default_rng(seed)
    ids = sorted(set(groups.tolist()))
    by = {g: np.flatnonzero(groups == g) for g in ids}

    def delta(index: np.ndarray) -> tuple[float, float] | None:
        y = labels[index]
        if len(set(y.tolist())) < 2:
            return None
        return float(roc_auc_score(y, other[index]) - roc_auc_score(y, base[index])), float(average_precision_score(y, other[index]) - average_precision_score(y, base[index]))

    point = delta(np.arange(len(labels)))
    draws = []
    for _ in range(replicates):
        d = delta(np.concatenate([by[ids[i]] for i in rng.integers(0, len(ids), len(ids))]))
        if d is not None:
            draws.append(d)
    arr = np.asarray(draws)
    out: dict[str, float] = {"groups": len(ids), "windows": len(labels), "valid_replicates": len(arr)}
    for j, name in enumerate(("AUROC", "AUPRC")):
        out[f"delta_{name}"] = point[j] if point else float("nan")
        out[f"delta_{name}_lo"], out[f"delta_{name}_hi"] = (float(np.quantile(arr[:, j], 0.025)), float(np.quantile(arr[:, j], 0.975))) if len(arr) else (float("nan"), float("nan"))
    return out


def summarise(cells: list[dict[str, Any]], train_seeds: list[int], holdouts: list[int]) -> dict[str, Any]:
    """Per model and metric: grand mean with a two-way bootstrap interval, the spread over training cohorts, and the prevalence range of the evaluation cohorts."""
    out: dict[str, Any] = {}
    for model in dict.fromkeys(c["model"] for c in cells):                  # models in first-seen order
        rows = [c for c in cells if c["model"] == model]
        block: dict[str, Any] = {}
        for metric in METRICS:
            grid = np.full((len(train_seeds), len(holdouts)), np.nan)
            for c in rows:
                grid[train_seeds.index(c["train_seed"]), holdouts.index(c["holdout"])] = c[metric]
            mean, lo, hi = bootstrap_ci(grid)
            block[metric] = {"mean": mean, "ci95": [lo, hi], "sd_over_training_cohorts": float(np.std(np.nanmean(grid, axis=1))), "min_cell": float(np.nanmin(grid)), "max_cell": float(np.nanmax(grid))}
        out[model] = block
    return out


def paired_differences(cells: list[dict[str, Any]], train_seeds: list[int], holdouts: list[int], a: str, b: str) -> dict[str, Any]:
    """Mean difference a - b per metric over cells (same cohorts), the two-way bootstrap interval, and how often a beats b."""
    res: dict[str, Any] = {}
    for metric in METRICS:
        grid = np.full((len(train_seeds), len(holdouts)), np.nan)
        for ka, ks in enumerate(train_seeds):
            for kh, h in enumerate(holdouts):
                va = next(c[metric] for c in cells if c["model"] == a and c["train_seed"] == ks and c["holdout"] == h)
                vb = next(c[metric] for c in cells if c["model"] == b and c["train_seed"] == ks and c["holdout"] == h)
                grid[ka, kh] = va - vb
        mean, lo, hi = bootstrap_ci(grid)
        res[metric] = {"mean_difference": mean, "ci95": [lo, hi], "fraction_of_cells_a_better": float((grid > 0).mean())}
    return res


# ---- data and baselines ---------------------------------------------------------------------------------------------------------------------------------------------------

def _flat(dataset: Any) -> np.ndarray:
    return dataset.inputs.reshape(len(dataset.inputs), -1)


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


def fit_baselines(train: list[Any]) -> dict[str, Any]:
    x = np.concatenate([_flat(d) for d in train])
    y = np.concatenate([d.labels for d in train]).astype(int)
    fitted = {}
    for name, features in (("Amplitude logistic", amplitude_features), ("Beat-timing logistic", timing_features)):
        a = features(x)
        mean, spread = a.mean(0), a.std(0) + 1e-9
        model = LogisticRegression(max_iter=3000).fit((a - mean) / spread, y)
        fitted[name] = (features, mean, spread, model)
    return fitted


def baseline_logits(fitted: tuple[Any, np.ndarray, np.ndarray, Any], x: np.ndarray) -> np.ndarray:
    features, mean, spread, model = fitted
    p = np.clip(model.predict_proba((features(x) - mean) / spread)[:, 1], 1e-9, 1 - 1e-9)
    return np.log(p / (1 - p))


def train_seed(k: int, client: int) -> int:
    from simulation import fl_cohort_realistic_v2 as c

    return c.TRAIN_BASE_SEED + 1000 * k + client


def eval_seed(h: int, replicate: int, site: int) -> int:
    """h = 0 reproduces the pinned evaluation cohort's seeds; every other h has its own disjoint range (replicates at +100, sites at +0..7)."""
    from simulation import fl_cohort_realistic_v2 as c

    return c.EVAL_BASE_SEED + 1000 * h + 100 * replicate + site


def train_cohort(k: int):
    from simulation import fl_cohort_realistic_v2 as c
    from simulation import fl_cohort_v1 as original

    profiles = [c._profile(original.client_id(i), f"SIM_S_RFL_K{k}_{i:02d}", 5000 + 100 * k + i, i, train_seed(k, i), evaluation=False) for i in range(c.TRAIN_COUNT)] if k else list(c.train_profiles())
    return [c.build_dataset(p) for p in profiles]


def evaluation_cohort(h: int):
    from simulation import fl_cohort_realistic_v2 as c

    if h == 0:
        datasets = [c.build_dataset(p) for p in c.eval_profiles()]
    else:
        datasets = []
        for i in range(c.EVAL_COUNT):
            site, replicate = i % c.SITES, i // c.SITES
            datasets.append(c.build_dataset(c._profile(f"SIM_REAL_EVAL_{i:02d}", f"SIM_S_ALT{h}_{i:02d}", 7000 + 100 * h + i, site, eval_seed(h, replicate, site), evaluation=True)))
    inputs = np.concatenate([d.inputs for d in datasets])
    return inputs.reshape(len(inputs), 1, -1), np.concatenate([d.labels for d in datasets]).astype(int)


def real_validation_windows():
    """The real MIT-BIH VALIDATION windows through the project's guarded loader, z-scored exactly as the model's own pipeline does; None when the local caches are absent."""
    try:
        from preprocessing.windowing import normalize_window_zscore
        from training.train_central import load_population

        population = load_population("VALIDATION")
    except (OSError, RuntimeError, ValueError, KeyError) as error:
        print(f"real-ECG probe skipped: {type(error).__name__}: {str(error)[:120]}")
        return None
    x = np.stack([normalize_window_zscore(w) for w in population.waveforms]).astype(np.float32)
    return x.reshape(len(x), 1, -1), population.labels.astype(int), population.participant_group_ids


def federated_states(train: list[Any], rounds: int, keep: tuple[int, ...], workdir: Path) -> dict[int, Any]:
    from fl10 import runner
    from fl10.runner import load_state
    from studio import v2_init

    state, audit = v2_init.load_v2_final()
    manifest = {d.client_id: {"participant_id": d.participant_id, "session_id": d.session_id, "dataset_sha": d.dataset_sha256} for d in train}
    report = runner.run_training(mode="H", run_id="REALISTIC-MULTISEED", out_dir=workdir, datasets=train, manifest=manifest, rounds=rounds, require_prefix_parity=False, capture_batches=False, progress=None,
                                 git_commit="UNKNOWN", protocol_sha256="UNKNOWN", algorithm="FEDAVG", secagg_mode="PLAIN", initial_state=state, initialisation=audit)
    states = {0: state}
    for row in report["rounds"]:
        if row["round"] in keep:
            states[row["round"]] = load_state(workdir, row["round"], row["global_state_sha256"])
    return states


def run(train_seeds: int, holdouts: int, rounds: int, real_probe: bool, out: Path) -> dict[str, Any]:
    from studio.isolated_eval import isolated_logits

    seeds = list(range(train_seeds))
    hold = list(range(holdouts))
    print(f"building {holdouts} evaluation cohorts ...", flush=True)
    evaluation = {h: evaluation_cohort(h) for h in hold}
    real = real_validation_windows() if real_probe else None
    cells: list[dict[str, Any]] = []
    probe_rows: list[dict[str, Any]] = []
    final = rounds
    keep = tuple(range(1, rounds + 1))
    final_name = f"Federated R{final:02d}"
    for k in seeds:
        print(f"training cohort {k + 1}/{train_seeds}: building, fitting baselines, {rounds}-round federated run ...", flush=True)
        train = train_cohort(k)
        baselines = fit_baselines(train)
        with tempfile.TemporaryDirectory(prefix=f"multiseed_{k}_") as tmp:
            states = federated_states(train, rounds, keep, Path(tmp))
        named = {"V2 R0": states[0]} | {f"Federated R{r:02d}": states[r] for r in keep if r in states}
        for h in hold:
            x, y = evaluation[h]
            flat = x.reshape(len(x), -1)
            scores = {name: isolated_logits(state, x) for name, state in named.items()} | {name: baseline_logits(fit, flat) for name, fit in baselines.items()}
            for model, z in scores.items():
                cells.append({"train_seed": k, "holdout": h, "model": model, **cell_metrics(z, y)})
        if real is not None:
            rx, ry, rg = real
            base = isolated_logits(states[0], rx)
            for round_id in keep:
                if round_id in states:
                    probe_rows.append({"train_seed": k, "model": f"Federated R{round_id:02d}", "round": round_id, **group_bootstrap_delta(ry, rg, base, isolated_logits(states[round_id], rx))})
        print(f"  done ({len(cells)} cells)", flush=True)
    result: dict[str, Any] = {
        "design": {"training_cohorts": train_seeds, "evaluation_cohorts": holdouts, "rounds": rounds, "algorithm": "FEDAVG", "aggregation": "PLAIN", "start": "MODEL_V2_FINAL", "threshold": 0.5, "calibration": "NONE",
                   "claim_boundary": "SYNTHETIC_REALISTIC_ENGINEERING_DEMONSTRATION_PLUS_REAL_ECG_DIAGNOSTIC_NOT_CLINICAL"},
        "evaluation_cohort_prevalence": [float(evaluation[h][1].mean()) for h in hold],
        "summary": summarise(cells, seeds, hold),
        "final_round_model": final_name,
        "paired": {f"{final_name} minus V2 R0": paired_differences(cells, seeds, hold, final_name, "V2 R0"), f"{final_name} minus Beat-timing logistic": paired_differences(cells, seeds, hold, final_name, "Beat-timing logistic"),
                   "V2 R0 minus Beat-timing logistic": paired_differences(cells, seeds, hold, "V2 R0", "Beat-timing logistic")},
        "real_ecg_forgetting_probe": {"status": "RUN" if real is not None else "SKIPPED_LOCAL_CACHES_ABSENT", "partition": "MIT-BIH VALIDATION (EVALUATE_ONLY; V2 model selection used it, so absolute numbers are optimistic)",
                                      "windows": len(real[1]) if real is not None else None, "rows": probe_rows}, "cells": cells}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")
    return result


def print_summary(result: dict[str, Any]) -> None:
    d = result["design"]
    print(f"\n{d['training_cohorts']} training cohorts x {d['evaluation_cohorts']} evaluation cohorts, {d['rounds']} rounds; prevalence of the evaluation cohorts: {[round(p, 3) for p in result['evaluation_cohort_prevalence']]}")
    for model, block in result["summary"].items():
        print(f"{model:22s} " + "  ".join(f"{m} {block[m]['mean']:.3f} [{block[m]['ci95'][0]:.3f}, {block[m]['ci95'][1]:.3f}]" for m in METRICS))
    for name, res in result["paired"].items():
        print(f"{name}: " + "  ".join(f"{m} {res[m]['mean_difference']:+.3f} [{res[m]['ci95'][0]:+.3f}, {res[m]['ci95'][1]:+.3f}] better in {res[m]['fraction_of_cells_a_better']:.0%}" for m in METRICS))
    probe = result["real_ecg_forgetting_probe"]
    print(f"real-ECG probe: {probe['status']}")
    for model in dict.fromkeys(r["model"] for r in probe["rows"]):
        rows = [r for r in probe["rows"] if r["model"] == model]
        print(f"  {model}: mean change from the frozen V2 over {len(rows)} training cohorts: dAUROC {np.mean([r['delta_AUROC'] for r in rows]):+.4f} (worst {min(r['delta_AUROC'] for r in rows):+.4f})  dAUPRC {np.mean([r['delta_AUPRC'] for r in rows]):+.4f} (worst {min(r['delta_AUPRC'] for r in rows):+.4f})")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--train-seeds", type=int, default=5)
    parser.add_argument("--holdouts", type=int, default=6)
    parser.add_argument("--rounds", type=int, default=10)
    parser.add_argument("--out", default="reports/realistic/multiseed.json")
    parser.add_argument("--quick", action="store_true", help="smoke configuration: 1 training cohort, 2 evaluation cohorts, 2 rounds")
    parser.add_argument("--no-real-probe", action="store_true")
    args = parser.parse_args(argv)
    if args.quick:
        args.train_seeds, args.holdouts, args.rounds = 1, 2, 2
    result = run(args.train_seeds, args.holdouts, args.rounds, not args.no_real_probe, Path(args.out))
    print_summary(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
