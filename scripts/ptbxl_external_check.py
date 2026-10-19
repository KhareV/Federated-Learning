# ruff: noqa: E501
"""PTBXL_EXTERNAL_CHECK_V1: frozen NHM models scored on real PTB-XL ECG that no model was trained, selected, calibrated or evaluated on. The protocol (labels, population, preprocessing, models,
statistics) is `docs/ptbxl/PTBXL_EXTERNAL_CHECK_V1.md`, written before any score existed; its SHA-256 is recorded in the output.

    PYTHONPATH=src:. python -m scripts.ptbxl_external_check [--out reports/ptbxl/external_check_v1.json] [--skip-adapted] [--limit N]

Extension outside the locked AAMI_SVF_WINDOW_V1 scope (PTB-XL has no beat annotations): record-level target PTBXL_PREMATURE_BEAT_RECORD_V1. Nothing is trained on PTB-XL, no threshold or model is selected from it."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from collections import OrderedDict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.signal import firwin, lfilter
from sklearn.metrics import average_precision_score, roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/ptbxl"
CACHE = ROOT / "data/processed/ptbxl_external_v1"
PROTOCOL = ROOT / "docs/ptbxl/PTBXL_EXTERNAL_CHECK_V1.md"
SOURCE_RATE, TARGET_RATE, RECORD_SAMPLES, WINDOW_SAMPLES = 500, 250, 5000, 2500
PREROLL_SOURCE_SAMPLES = 1000
DECIMATOR_TAPS, DECIMATOR_CUTOFF_HZ, DECIMATOR_BETA = 101, 100.0, 5.0
ECTOPY_CODES = ("PVC", "PAC", "PRC(S)", "BIGU", "TRIGU")
BOOTSTRAP_SEED, BOOTSTRAP_REPLICATES = 20271118, 2000
PRIMARY_FOLDS, REPLICATION_FOLDS = (9, 10), tuple(range(1, 9))


# ---- labels --------------------------------------------------------------------------------------------------------------------------------------------------------------------------
def label_table(database: Path = RAW / "ptbxl_database.csv") -> pd.DataFrame:
    """One row per record: the label sources and the three predeclared rules (A union, B agreement, C statements only). -1 means excluded under that rule."""
    d = pd.read_csv(database, index_col="ecg_id")
    codes = d.scp_codes.apply(ast.literal_eval)
    out = pd.DataFrame(index=d.index)
    out["patient_id"], out["fold"] = d.patient_id.astype(int), d.strat_fold.astype(int)
    out["code_pos"] = codes.apply(lambda c: any(k in c for k in ECTOPY_CODES))
    out["eb_pos"] = d.extra_beats.notna()
    out["paced"] = codes.apply(lambda c: "PACE" in c) | d.pacemaker.notna()
    out["norm_sr"] = codes.apply(lambda c: "NORM" in c and "SR" in c)
    out["afib"] = codes.apply(lambda c: "AFIB" in c)
    out["burst_noise"], out["static_noise"], out["baseline_drift"] = d.burst_noise.notna(), d.static_noise.notna(), d.baseline_drift.notna()
    out["extra_beat_count"] = d.extra_beats.apply(_extra_beat_bucket)
    out["label_A"] = np.where(out.code_pos | out.eb_pos, 1, 0)
    out["label_B"] = np.where(out.code_pos & out.eb_pos, 1, np.where(~out.code_pos & ~out.eb_pos, 0, -1))
    out["label_C"] = np.where(out.code_pos, 1, 0)
    return out


def _extra_beat_bucket(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    m = re.search(r"(\d+)", value)
    return "unspecified" if not m else ("3+" if int(m.group(1)) >= 3 else m.group(1))


# ---- preprocessing (PREPROC_V1_PTBXL_EXT) ---------------------------------------------------------------------------------------------------------------------------------------
def causal_decimate_by_two(x: np.ndarray) -> np.ndarray:
    """500 -> 250 Hz: a forward-only Kaiser FIR low-pass, then every second sample. Output sample n depends only on source samples <= 2n (causal)."""
    h = firwin(DECIMATOR_TAPS, DECIMATOR_CUTOFF_HZ, window=("kaiser", DECIMATOR_BETA), fs=SOURCE_RATE)
    return lfilter(h, 1.0, np.asarray(x, dtype=np.float64))[::2]


def window_for_record(signal_500: np.ndarray) -> np.ndarray | None:
    """The z-scored [2500] window of one 5,000-sample 500 Hz record, or None when the record cannot form a valid window."""
    from preprocessing.ecg import StatefulECGFilter
    from preprocessing.windowing import normalize_window_zscore

    x = np.asarray(signal_500, dtype=np.float64)
    if x.size != RECORD_SAMPLES or not np.isfinite(x).all() or float(np.std(x)) < 1e-6:
        return None
    padded = np.concatenate([np.full(PREROLL_SOURCE_SAMPLES, x[0]), x])                  # causal pre-roll: hold of the first sample, discarded below
    decimated = causal_decimate_by_two(padded)
    filt = StatefulECGFilter()
    filt.reset(segment_id=0)
    filtered = np.asarray(filt.process(decimated), dtype=np.float64)
    window = filtered[-WINDOW_SAMPLES:]
    if window.size != WINDOW_SAMPLES or not np.isfinite(window).all() or float(np.std(window)) < 1e-9:
        return None
    return normalize_window_zscore(window).astype(np.float32)


def build_windows(labels: pd.DataFrame, limit: int | None = None) -> tuple[np.ndarray, np.ndarray, dict[str, int]]:
    """Windows for every non-paced record (cached on disk); returns (ecg_ids, x [N,2500], exclusion counts)."""
    import wfdb

    CACHE.mkdir(parents=True, exist_ok=True)
    cache = CACHE / ("windows.npz" if limit is None else f"windows_limit{limit}.npz")
    if cache.exists():
        z = np.load(cache, allow_pickle=False)
        return z["ids"], z["x"], json.loads(str(z["exclusions"]))
    database = pd.read_csv(RAW / "ptbxl_database.csv", index_col="ecg_id")
    ids, xs = [], []
    exclusions = {"paced": 0, "no_lead_II": 0, "bad_window": 0}
    todo = [i for i in labels.index if not labels.at[i, "paced"]]
    exclusions["paced"] = int(labels.paced.sum())
    for n, ecg_id in enumerate(todo[:limit] if limit else todo):
        record = wfdb.rdrecord(str(RAW / database.at[ecg_id, "filename_hr"]))
        names = list(record.sig_name)
        if "II" not in names:
            exclusions["no_lead_II"] += 1
            continue
        window = window_for_record(record.p_signal[:, names.index("II")])
        if window is None:
            exclusions["bad_window"] += 1
            continue
        ids.append(ecg_id)
        xs.append(window)
        if n % 2000 == 0:
            print(f"  windows {n}/{len(todo)}", flush=True)
    ids_a, x_a = np.asarray(ids, dtype=np.int64), np.stack(xs).astype(np.float32)
    np.savez_compressed(cache, ids=ids_a, x=x_a, exclusions=json.dumps(exclusions))
    return ids_a, x_a, exclusions


# ---- models --------------------------------------------------------------------------------------------------------------------------------------------------------------------
def v1_logits(x: np.ndarray) -> np.ndarray:
    import torch

    from models.model_freeze import load_frozen_model_v1

    model, _ = load_frozen_model_v1(ROOT)
    out = []
    with torch.no_grad():
        for s in range(0, len(x), 256):
            out.append(model(torch.from_numpy(np.ascontiguousarray(x[s:s + 256][:, None, :]))).cpu().numpy()[:, 0])
    return np.concatenate(out).astype(np.float64)


def adapted_state(cohort: str, rounds: int = 10) -> OrderedDict[str, np.ndarray]:
    """Central V2 after `rounds` federated rounds on a synthetic cohort (the Studio engine); cached so a rerun does not retrain."""
    import tempfile

    from federated.model_adapter import deserialize_state, serialize_state
    from fl10 import runner
    from fl10.runner import load_state
    from studio import cohorts, v2_init

    path = CACHE / f"adapted_{cohort.lower()}_r{rounds}.bin"
    if path.exists():
        return OrderedDict(deserialize_state(path.read_bytes()))
    start, audit = v2_init.load_v2_final()
    datasets, manifest = cohorts.training(cohort)
    with tempfile.TemporaryDirectory(prefix="ptbxl_adapt_") as tmp:
        report = runner.run_training(mode="H", run_id=f"PTBXL-ADAPT-{cohort}", out_dir=Path(tmp), datasets=datasets, manifest=manifest, rounds=rounds, require_prefix_parity=False, capture_batches=False,
                                     progress=None, git_commit="UNKNOWN", protocol_sha256="UNKNOWN", algorithm="FEDAVG", secagg_mode="PLAIN", initial_state=start, initialisation=audit)
        last = report["rounds"][-1]
        state = OrderedDict(load_state(Path(tmp), last["round"], last["global_state_sha256"]))
    path.write_bytes(serialize_state(state))
    return state


def all_logits(x: np.ndarray, include_adapted: bool) -> dict[str, np.ndarray]:
    from scripts.fl50_cohort_runs import FL50_BEST_CHECKPOINT, FL50_BEST_SHA256, load_checkpoint_state, load_fl50_state
    from studio import v2_init
    from studio.isolated_eval import isolated_logits

    x3 = x[:, None, :]
    central, _ = v2_init.load_v2_final()
    out = {"MODEL_V1 (central, frozen)": v1_logits(x), "MODEL_V2_FINAL (central)": isolated_logits(central, x3), "V2-FL-001 round 50 (federated)": isolated_logits(load_fl50_state(), x3),
           "V2-FL-001 round 38 (best-validation)": isolated_logits(load_checkpoint_state(FL50_BEST_CHECKPOINT, FL50_BEST_SHA256), x3)}
    if include_adapted:
        for cohort, name in (("ORIGINAL", "central V2 + 10 rounds on the original synthetic cohort"), ("REALISTIC", "central V2 + 10 rounds on the realistic synthetic cohort")):
            print(f"  adapting central V2 on the {cohort} cohort ...", flush=True)
            out[name] = isolated_logits(adapted_state(cohort), x3)
    return out


# ---- statistics ----------------------------------------------------------------------------------------------------------------------------------------------------------------
def point_metrics(z: np.ndarray, y: np.ndarray) -> dict[str, float]:
    from scripts.realistic_diagnostics import metrics

    m = metrics(z, y)
    m["lift"] = m["AUPRC"] / m["prevalence"] if m["prevalence"] else float("nan")
    return m


def cluster_bootstrap(logits: dict[str, np.ndarray], y: np.ndarray, groups: np.ndarray, reps: int = BOOTSTRAP_REPLICATES, seed: int = BOOTSTRAP_SEED, base: str = "MODEL_V2_FINAL (central)") -> dict[str, Any]:
    """Patient-cluster percentile bootstrap: patients resampled with replacement, all their records kept, each metric recomputed on the pooled replicate; the same replicates serve every model (paired)."""
    rng = np.random.default_rng(seed)
    uniq, inverse = np.unique(groups, return_inverse=True)
    by_group = [np.flatnonzero(inverse == g) for g in range(len(uniq))]
    pred = {m: (1 / (1 + np.exp(-np.clip(z, -60, 60)))) >= 0.5 for m, z in logits.items()}
    draws: dict[str, dict[str, list[float]]] = {m: {"AUROC": [], "AUPRC": [], "F1": []} for m in logits}
    invalid = 0
    for _ in range(reps):
        idx = np.concatenate([by_group[g] for g in rng.integers(0, len(uniq), len(uniq))])
        yy = y[idx]
        if yy.min() == yy.max():
            invalid += 1
            continue
        for m, z in logits.items():
            p = pred[m][idx]
            tp, fp, fn = int((p & (yy == 1)).sum()), int((p & (yy == 0)).sum()), int((~p & (yy == 1)).sum())
            draws[m]["AUROC"].append(float(roc_auc_score(yy, z[idx])))
            draws[m]["AUPRC"].append(float(average_precision_score(yy, z[idx])))
            draws[m]["F1"].append(2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0)
    ci = lambda a: [float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5))]  # noqa: E731
    out: dict[str, Any] = {"patients": int(len(uniq)), "replicates": reps - invalid, "invalid_replicates": invalid, "models": {}, "paired_vs_central_V2": {}}
    for m in logits:
        out["models"][m] = {k: {"ci95": ci(v)} for k, v in draws[m].items()}
    for m in logits:
        if m == base:
            continue
        out["paired_vs_central_V2"][m] = {k: {"delta_mean": float(np.mean(np.asarray(draws[m][k]) - np.asarray(draws[base][k]))), "ci95": ci(np.asarray(draws[m][k]) - np.asarray(draws[base][k])),
                                              "share_better": float(np.mean(np.asarray(draws[m][k]) > np.asarray(draws[base][k])))} for k in ("AUROC", "AUPRC")}
    return out


# ---- run ----------------------------------------------------------------------------------------------------------------------------------------------------------------------
def run(out: Path, include_adapted: bool, limit: int | None) -> dict[str, Any]:
    labels = label_table()
    print("building PTB-XL windows ...", flush=True)
    ids, x, exclusions = build_windows(labels, limit)
    lab = labels.loc[ids]
    print(f"{len(ids)} windows; exclusions {exclusions}", flush=True)
    logits = all_logits(x, include_adapted)
    result: dict[str, Any] = {"protocol": {"file": str(PROTOCOL.relative_to(ROOT)), "sha256": hashlib.sha256(PROTOCOL.read_bytes()).hexdigest()}, "target": "PTBXL_PREMATURE_BEAT_RECORD_V1", "records_scored": int(len(ids)),
                              "exclusions": exclusions, "threshold": 0.5, "calibration": "NONE", "models": list(logits), "sets": {}}
    sets = {"primary (folds 9-10)": lab.fold.isin(PRIMARY_FOLDS).to_numpy(), "replication (folds 1-8)": lab.fold.isin(REPLICATION_FOLDS).to_numpy()}
    for set_name, in_set in sets.items():
        block: dict[str, Any] = {}
        for rule in ("A", "B", "C"):
            keep = in_set & (lab[f"label_{rule}"].to_numpy() >= 0)
            y = lab[f"label_{rule}"].to_numpy()[keep].astype(int)
            block[f"rule {rule}"] = {"records": int(keep.sum()), "positives": int(y.sum()), "patients": int(lab.patient_id.to_numpy()[keep].size and len(np.unique(lab.patient_id.to_numpy()[keep]))),
                                     "models": {m: point_metrics(z[keep], y) for m, z in logits.items()}}
        clean = in_set & ((lab.label_A.to_numpy() == 1) | lab.norm_sr.to_numpy())              # rule A positives, negatives restricted to NORM with SR
        yc = lab.label_A.to_numpy()[clean].astype(int)
        block["rule A, clean negatives (NORM + SR)"] = {"records": int(clean.sum()), "positives": int(yc.sum()), "models": {m: point_metrics(z[clean], yc) for m, z in logits.items()}}
        keep_a = in_set
        block["bootstrap rule A"] = cluster_bootstrap({m: z[keep_a] for m, z in logits.items()}, lab.label_A.to_numpy()[keep_a].astype(int), lab.patient_id.to_numpy()[keep_a])
        result["sets"][set_name] = block
    # descriptive error analysis, central V2, rule A, primary set
    z = logits["MODEL_V2_FINAL (central)"]
    flagged = (1 / (1 + np.exp(-np.clip(z, -60, 60)))) >= 0.5
    prim = sets["primary (folds 9-10)"]
    neg, pos = prim & (lab.label_A.to_numpy() == 0), prim & (lab.label_A.to_numpy() == 1)
    share = lambda mask: {"records": int(mask.sum()), "share_flagged": float(flagged[mask].mean()) if mask.any() else None}  # noqa: E731
    result["error_analysis_central_V2_rule_A_primary"] = {
        "negatives": share(neg), "negatives with burst_noise": share(neg & lab.burst_noise.to_numpy()), "negatives with static_noise": share(neg & lab.static_noise.to_numpy()),
        "negatives with baseline_drift": share(neg & lab.baseline_drift.to_numpy()), "negatives with AFIB": share(neg & lab.afib.to_numpy()), "negatives NORM+SR": share(neg & lab.norm_sr.to_numpy()),
        "positives": share(pos), **{f"positives with {b} extra beat(s)": share(pos & (lab.extra_beat_count.to_numpy() == b)) for b in ("1", "2", "3+", "unspecified")},
        "positives by source": {"SCP statement and extra_beats": share(pos & lab.code_pos.to_numpy() & lab.eb_pos.to_numpy()), "SCP statement only": share(pos & lab.code_pos.to_numpy() & ~lab.eb_pos.to_numpy()), "extra_beats only": share(pos & ~lab.code_pos.to_numpy() & lab.eb_pos.to_numpy())}}
    result["sanity"] = {"windows_finite": bool(np.isfinite(x).all()), "window_std_mean": float(x.std(axis=1).mean()), "label_source_agreement": {
        "both": int((labels.code_pos & labels.eb_pos).sum()), "SCP statement only": int((labels.code_pos & ~labels.eb_pos).sum()), "extra_beats only": int((~labels.code_pos & labels.eb_pos).sum())},
        "mean_logit_NORM_SR_negatives_vs_positives_central_V2": [float(z[(lab.label_A.to_numpy() == 0) & lab.norm_sr.to_numpy()].mean()), float(z[lab.label_A.to_numpy() == 1].mean())]}
    path = ROOT / out
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=1, sort_keys=True, default=float) + "\n")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="reports/ptbxl/external_check_v1.json")
    parser.add_argument("--skip-adapted", action="store_true", help="skip the two synthetic-adapted models (each needs a 10-round federated run the first time)")
    parser.add_argument("--limit", type=int, default=None, help="smoke test on the first N non-paced records")
    args = parser.parse_args(argv)
    r = run(Path(args.out), not args.skip_adapted, args.limit)
    for set_name, block in r["sets"].items():
        a = block["rule A"]
        print(f"\n{set_name}: rule A, {a['records']} records, {a['positives']} positives")
        for m, v in a["models"].items():
            print(f"  {m:62s} AUROC {v['AUROC']:.3f}  AUPRC {v['AUPRC']:.3f} (lift {v['lift']:.2f})  F1@0.5 {v['F1']:.3f}  sens {v['recall']:.2f} spec {v['specificity']:.2f}")
    print("\nsanity:", json.dumps(r["sanity"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
