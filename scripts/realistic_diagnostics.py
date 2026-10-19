# ruff: noqa: E501
"""Why does the pretrained V2 score lower on the realistic synthetic cohort than on real ECG? Three diagnostics on the realistic evaluation holdouts (no training, inference only):

  1. annotation noise off: the same windows scored against the hidden truth (every true ectopic beat counts, no false artifact marks) instead of the noisy annotations;
  2. false positives by what the window contains (a large motion artifact, a smaller motion artifact, an electrode pop, a missed-annotation window, or nothing special);
  3. the decision threshold re-fitted on realistic holdouts that are NOT the scored one (leave-one-holdout-out over six independently seeded holdouts), compared with the fixed 0.5 rule.

    PYTHONPATH=src:. python -m scripts.realistic_diagnostics [--out reports/realistic/diagnostics.json]

Models: the central MODEL_V2_FINAL and the round-50 federated checkpoint of V2-FL-001. Diagnostic only: nothing here selects a model or a threshold for any run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
LARGE_MOTION_MV = 0.8                    # the generator's own "large motion artifact" size (the ones an annotator can mark as ectopy)
WINDOW_S = 10.0


def profiles_for(h: int):
    from scripts.realistic_multiseed import eval_seed
    from simulation import fl_cohort_realistic_v2 as c

    if h == 0:
        return list(c.eval_profiles())
    out = []
    for i in range(c.EVAL_COUNT):
        site, replicate = i % c.SITES, i // c.SITES
        out.append(c._profile(f"SIM_REAL_EVAL_{i:02d}", f"SIM_S_ALT{h}_{i:02d}", 7000 + 100 * h + i, site, eval_seed(h, replicate, site), evaluation=True))
    return out


def window_table(h: int) -> dict[str, np.ndarray]:
    """Per window of holdout h: input, annotated label, hidden-truth label and what the window contains."""
    from simulation import fl_cohort_realistic_v2 as c

    xs, y_ann, y_true, kind, participant, noise, has_large = [], [], [], [], [], [], []
    for p in profiles_for(h):
        ds = c.build_dataset(p)
        rendered, phys = c.rendered(p)
        truth = np.asarray(rendered.true_ectopic, dtype=float)
        large = np.asarray([a.time_s for a in rendered.artifacts if a.kind == "MOTION" and a.amplitude_mv >= LARGE_MOTION_MV], dtype=float)
        small = np.asarray([a.time_s for a in rendered.artifacts if a.kind == "MOTION" and a.amplitude_mv < LARGE_MOTION_MV], dtype=float)
        pops = np.asarray([a.time_s for a in rendered.artifacts if a.kind == "POP"], dtype=float)
        for x, ann, edge in zip(ds.inputs, ds.labels, ds.right_edges_us, strict=True):
            end = edge / 1e6
            inside = lambda t: bool(np.any((t >= end - WINDOW_S) & (t <= end))) if t.size else False  # noqa: E731
            t_true, t_large, t_small, t_pop = inside(truth), inside(large), inside(small), inside(pops)
            xs.append(x)
            y_ann.append(int(ann))
            y_true.append(int(t_true))
            participant.append(p.participant_id)
            has_large.append(t_large)
            noise.append(phys.noise_scale)
            if ann == 0 and t_true:
                kind.append("annotation missed the true ectopic beat")
            elif t_true:
                kind.append("true ectopy (annotated)")
            elif ann == 1:
                kind.append("no true ectopy, marked as ectopy (annotator error)")
            elif t_large:
                kind.append("no ectopy, large motion artifact")
            elif t_small:
                kind.append("no ectopy, smaller motion artifact")
            elif t_pop:
                kind.append("no ectopy, electrode pop")
            else:
                kind.append("no ectopy, nothing special")
    return {"x": np.stack(xs).astype(np.float32).reshape(len(xs), 1, -1), "y_ann": np.asarray(y_ann), "y_true": np.asarray(y_true), "kind": np.asarray(kind), "participant": np.asarray(participant), "noise": np.asarray(noise), "large_motion": np.asarray(has_large)}


def metrics(z: np.ndarray, y: np.ndarray, threshold: float = 0.5) -> dict[str, float]:
    p = 1 / (1 + np.exp(-np.clip(z, -60, 60)))
    pred = p >= threshold
    tp, fp, fn, tn = int((pred & (y == 1)).sum()), int((pred & (y == 0)).sum()), int((~pred & (y == 1)).sum()), int((~pred & (y == 0)).sum())
    f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0
    return {"AUROC": float(roc_auc_score(y, z)), "AUPRC": float(average_precision_score(y, z)), "prevalence": float(y.mean()), "F1": f1, "precision": tp / (tp + fp) if tp + fp else 0.0, "recall": tp / (tp + fn) if tp + fn else 0.0,
            "specificity": tn / (tn + fp) if tn + fp else 0.0, "TP": tp, "FP": fp, "TN": tn, "FN": fn, "threshold": float(threshold)}


def best_f1_threshold(z: np.ndarray, y: np.ndarray) -> float:
    p = 1 / (1 + np.exp(-np.clip(z, -60, 60)))
    grid = np.unique(np.quantile(p, np.linspace(0.02, 0.98, 97)))
    scores = [metrics(z, y, float(t))["F1"] for t in grid]
    return float(grid[int(np.argmax(scores))])


def run(out: Path) -> dict[str, Any]:
    from scripts.fl50_cohort_runs import load_fl50_state
    from studio import v2_init
    from studio.isolated_eval import isolated_logits

    central, _ = v2_init.load_v2_final()
    models = {"central MODEL_V2_FINAL": central, "V2-FL-001 round 50": load_fl50_state()}
    tables = {}
    for h in range(6):
        print(f"building holdout {h} ...", flush=True)
        tables[h] = window_table(h)
    logits = {m: {h: isolated_logits(s, tables[h]["x"]) for h in tables} for m, s in models.items()}
    result: dict[str, Any] = {"design": {"holdouts": 6, "pinned_holdout": 0, "large_motion_mv": LARGE_MOTION_MV, "diagnostic_only": True}, "annotation_noise": {}, "false_positives": {}, "threshold_refit": {}}
    t0 = tables[0]
    result["holdout0_windows"] = int(len(t0["y_ann"]))
    result["annotation_flips"] = {"missed_true_beat (label 1 -> 0)": int(((t0["y_true"] == 1) & (t0["y_ann"] == 0)).sum()), "false_mark (label 0 -> 1)": int(((t0["y_true"] == 0) & (t0["y_ann"] == 1)).sum())}
    for m in models:
        z = logits[m][0]
        result["annotation_noise"][m] = {"noisy_annotations": metrics(z, t0["y_ann"]), "hidden_truth": metrics(z, t0["y_true"])}
        kinds = {}
        pred = (1 / (1 + np.exp(-np.clip(z, -60, 60)))) >= 0.5
        for k in sorted(set(t0["kind"])):
            sel = t0["kind"] == k
            kinds[k] = {"windows": int(sel.sum()), "flagged_positive": int(pred[sel].sum()), "share_flagged": float(pred[sel].mean())}
        result["false_positives"][m] = kinds
        rows = []
        for h in range(6):
            fit_z = np.concatenate([logits[m][o] for o in range(6) if o != h])
            fit_y = np.concatenate([tables[o]["y_ann"] for o in range(6) if o != h])
            thr = best_f1_threshold(fit_z, fit_y)
            rows.append({"holdout": h, "fitted_threshold": thr, "fixed_0.5": metrics(logits[m][h], tables[h]["y_ann"]), "refit": metrics(logits[m][h], tables[h]["y_ann"], thr)})
        result["threshold_refit"][m] = {"per_holdout": rows, "mean_F1_fixed": float(np.mean([r["fixed_0.5"]["F1"] for r in rows])), "mean_F1_refit": float(np.mean([r["refit"]["F1"] for r in rows])),
                                        "mean_fitted_threshold": float(np.mean([r["fitted_threshold"] for r in rows]))}
    # what-if: a working artifact gate would drop windows that contain a large motion artifact (the pipeline's quality gate does not flag them today); scores on the remaining windows, pooled over the six holdouts and on the pinned one
    result["artifact_gate_what_if"] = {}
    for m in models:
        keep = {h: ~tables[h]["large_motion"] for h in tables}
        pooled_z = np.concatenate([logits[m][h][keep[h]] for h in tables])
        pooled_y = np.concatenate([tables[h]["y_ann"][keep[h]] for h in tables])
        result["artifact_gate_what_if"][m] = {"windows_dropped_share_pooled": float(1 - np.mean(np.concatenate([keep[h] for h in tables]))),
                                              "pinned_holdout_all_windows": metrics(logits[m][0], tables[0]["y_ann"]), "pinned_holdout_gated": metrics(logits[m][0][keep[0]], tables[0]["y_ann"][keep[0]]),
                                              "pooled_six_holdouts_gated": metrics(pooled_z, pooled_y)}
    # the false positives by noise level of the participant (terciles of the participants' noise scale), central model, fixed 0.5
    z = logits["central MODEL_V2_FINAL"][0]
    pred = (1 / (1 + np.exp(-np.clip(z, -60, 60)))) >= 0.5
    neg = t0["y_true"] == 0
    cuts = np.quantile(t0["noise"], [1 / 3, 2 / 3])
    bands = np.digitize(t0["noise"], cuts)
    result["false_positive_rate_by_noise_tercile_central"] = {f"tercile {b + 1}": {"windows_without_true_ectopy": int((neg & (bands == b)).sum()), "share_flagged": float(pred[neg & (bands == b)].mean())} for b in range(3)}
    path = ROOT / out
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=1, sort_keys=True, default=float) + "\n")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="reports/realistic/diagnostics.json")
    args = parser.parse_args(argv)
    r = run(Path(args.out))
    print(json.dumps({k: r[k] for k in ("holdout0_windows", "annotation_flips")}, indent=1))
    for m, v in r["annotation_noise"].items():
        a, b = v["noisy_annotations"], v["hidden_truth"]
        print(f"{m}: noisy labels AUROC {a['AUROC']:.3f} AUPRC {a['AUPRC']:.3f} F1 {a['F1']:.3f} | hidden truth AUROC {b['AUROC']:.3f} AUPRC {b['AUPRC']:.3f} F1 {b['F1']:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
