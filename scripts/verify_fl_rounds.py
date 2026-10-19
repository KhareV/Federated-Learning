# ruff: noqa: E501
"""Independent verification of every round of every Studio federated run: are the stored values correct?

For each run directory (``<studio root>/FL10RUN-*``) and EVERY round R0..RN it checks, with code that does not call the engine's metric functions:

  1. the state chain: the stored state file's SHA-256 equals the run report's and the evaluation record's digest; each round's base digest is the previous round's state; every float entry is finite and every
     integer bookkeeping buffer is unchanged; R0 is the declared starting model (pretrained V2, untrained V2, or the chosen stored candidate);
  2. the predictions: the stored ``predictions.csv`` matches its recorded SHA-256, carries the cohort holdout's labels exactly, and its logits equal logits RE-COMPUTED here from the stored state;
  3. the metrics: AUROC (rank statistic), AUPRC (step-wise average precision), F1, accuracy, precision, recall, specificity, balanced accuracy, BCE, Brier and the confusion counts are recomputed from those logits with
     implementations written here, and compared with the stored record; per-participant window and confusion counts are recomputed from the same file; the paired comparison is recomputed from the point values;
  3b. the same for the unseen generalisation cohort (the ``eval_g1`` lane shown in the Generalisation tab);
  4. optionally (``--rederive``) the aggregation: the eight clients are trained again from the stored base state with the engine's deterministic local trainer and the new global state is formed here as
     base + the example-weighted mean of the client deltas (float64 accumulate, cast to the state dtype); it must equal the stored state bit for bit.

    PYTHONPATH=src:. python -m scripts.verify_fl_rounds --root <studio root> [--run FL10RUN-...] [--rederive all|none|1,2,3] [--out reports/verification/fl_round_values.json]

Exit code 1 if any check fails. Run directories of live-monitored-site runs (mode B) get checks 1 to 3; checks of aggregation need the cohort datasets, which mode B replaces for one client."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Any

import numpy as np
from scipy.stats import rankdata

ROOT = Path(__file__).resolve().parents[1]
THRESHOLD = 0.5
METRIC_TOLERANCE = {"AUROC": 1e-9, "AUPRC": 1e-9, "F1": 1e-9, "accuracy": 1e-9, "precision": 1e-9, "recall": 1e-9, "specificity": 1e-9, "balanced_accuracy": 1e-9, "BCE": 1e-9, "Brier": 1e-9}
COUNTS = ("TP", "FP", "TN", "FN")


# ---- independent metric implementations -------------------------------------------------------------------------------------------------------------------------------------------
def sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.asarray(z, dtype=np.float64)))


def _ratio(n: float, d: float) -> float | None:
    """An undefined ratio (zero denominator) is None, exactly as the evaluation records store it: never zero, never NaN."""
    return None if d == 0 else n / d


def auroc(y: np.ndarray, score: np.ndarray) -> float | None:
    """Mann-Whitney rank statistic with average ranks for ties; None when only one class is present."""
    n_pos, n_neg = int(y.sum()), int(len(y) - y.sum())
    if n_pos == 0 or n_neg == 0:
        return None
    ranks = rankdata(score)
    return float((ranks[y == 1].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def average_precision(y: np.ndarray, score: np.ndarray) -> float | None:
    """Step-wise, non-interpolated average precision: sum over distinct thresholds of (R_n - R_{n-1}) * P_n; None when there is no positive."""
    if int(y.sum()) == 0:
        return None
    order = np.argsort(-score, kind="mergesort")
    s, t = score[order], y[order]
    last_of_tie = np.r_[np.flatnonzero(np.diff(s)), len(s) - 1]
    tp = np.cumsum(t)[last_of_tie].astype(np.float64)
    seen = (last_of_tie + 1).astype(np.float64)
    precision, recall = tp / seen, tp / float(y.sum())
    return float(np.sum(np.diff(np.r_[0.0, recall]) * precision))


def confusion(y: np.ndarray, p: np.ndarray) -> dict[str, int]:
    pred = p >= THRESHOLD
    return {"TP": int((pred & (y == 1)).sum()), "FP": int((pred & (y == 0)).sum()), "TN": int((~pred & (y == 0)).sum()), "FN": int((~pred & (y == 1)).sum())}


def recompute_metrics(y: np.ndarray, logits: np.ndarray) -> dict[str, float | int | None]:
    z = np.asarray(logits, dtype=np.float64)
    p = sigmoid(z)
    c = confusion(y, p)
    tp, fp, tn, fn = c["TP"], c["FP"], c["TN"], c["FN"]
    recall, specificity = _ratio(tp, tp + fn), _ratio(tn, tn + fp)
    return {**c, "AUROC": auroc(y, p), "AUPRC": average_precision(y, p), "accuracy": (tp + tn) / len(y), "precision": _ratio(tp, tp + fp), "recall": recall, "specificity": specificity,
            "balanced_accuracy": None if recall is None or specificity is None else (recall + specificity) / 2, "F1": _ratio(2 * tp, 2 * tp + fp + fn),
            "BCE": float(np.mean(np.maximum(z, 0) - z * y + np.log1p(np.exp(-np.abs(z))))), "Brier": float(np.mean((p - y) ** 2))}


def same(stored: Any, mine: float | int | None, tol: float) -> bool:
    """A stored value equals the recomputed one within tolerance; an undefined metric must be undefined on both sides."""
    if mine is None:
        return stored is None
    return stored is not None and abs(float(stored) - float(mine)) <= tol


# ---- run-level helpers --------------------------------------------------------------------------------------------------------------------------------------------------------------
def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _state(run_root: Path, r: int) -> dict[str, np.ndarray]:
    from federated.model_adapter import deserialize_state

    return dict(deserialize_state((run_root / f"states/R{r:02d}.bin").read_bytes()))


def _read_predictions(path: Path) -> tuple[np.ndarray, np.ndarray, list[str]]:
    rows = list(csv.DictReader(io.StringIO(path.read_text())))
    return np.array([int(r["label"]) for r in rows]), np.array([float(r["logit"]) for r in rows]), [r["participant_id"] for r in rows]


def expected_start_digest(meta: dict[str, Any]) -> tuple[str, str]:
    from studio import v2_init

    init = meta.get("init")
    if init == v2_init.INIT_V2_FINAL:
        return v2_init.load_v2_final()[1]["state_sha256"], "pretrained MODEL_V2_FINAL"
    if init == v2_init.INIT_FRESH:
        return v2_init.initial_state(v2_init.INIT_FRESH)[1]["state_sha256"], "untrained FL_INIT_V2"
    audit = meta.get("base_audit") or {}
    return str(audit.get("state_sha256")), f"stored candidate {audit.get('model_id')}"


def aggregate_independently(base: dict[str, np.ndarray], updates: list[tuple[int, dict[str, np.ndarray]]]) -> dict[str, np.ndarray]:
    """base + example-weighted mean of the client deltas for every floating entry (float64 accumulate, cast to the entry dtype); integer buffers unchanged."""
    total = sum(n for n, _ in updates)
    out = {}
    for key, value in base.items():
        if np.issubdtype(value.dtype, np.floating):
            acc = np.zeros(value.shape, dtype=np.float64)
            for n, delta in updates:
                acc += np.asarray(delta[key], dtype=np.float64) * n
            out[key] = np.asarray(value + np.asarray(acc / total, dtype=value.dtype), dtype=value.dtype)
        else:
            out[key] = np.array(value, copy=True)
    return out


def rederive_round(job: Path, meta: dict[str, Any], k: int, base: dict[str, np.ndarray], stored: dict[str, np.ndarray]) -> dict[str, Any]:
    from federated.model_v2_fedprox import train_local_fedprox_epoch_v2
    from federated.model_v2_fl import train_local_epoch_v2
    from federated.wearable_fl_runner_v1 import BASE_SEED, BATCH_SIZE, LEARNING_RATE, POS_WEIGHT, WEIGHT_DECAY
    from federated.wearable_fl_system_v1 import EXPERIMENT_ID
    from product.federation.client import frozen_fedprox_mu
    from studio import cohorts

    datasets, _ = cohorts.training(meta.get("cohort", cohorts.ORIGINAL))
    updates = []
    for d in sorted(datasets, key=lambda x: x.client_id):
        kwargs = dict(global_state=base, inputs=d.inputs, labels=d.labels, site_id=d.client_id, round_number=k, experiment_id=EXPERIMENT_ID, base_seed=BASE_SEED, batch_size=BATCH_SIZE,
                      learning_rate=LEARNING_RATE, weight_decay=WEIGHT_DECAY, pos_weight=POS_WEIGHT)
        if meta.get("algorithm") == "FEDPROX":
            result = train_local_fedprox_epoch_v2(mu=frozen_fedprox_mu(), **kwargs)
        else:
            result = train_local_epoch_v2(**kwargs)
        updates.append((int(result.examples_seen), dict(result.update.delta)))
    mine = aggregate_independently(base, updates)
    equal = list(mine) == list(stored) and all(np.array_equal(mine[key], stored[key]) for key in stored)
    worst = max((float(np.max(np.abs(mine[key].astype(np.float64) - stored[key].astype(np.float64)))) for key in stored if np.issubdtype(stored[key].dtype, np.floating)), default=0.0)
    return {"clients": len(updates), "examples": [n for n, _ in updates], "bit_identical": bool(equal), "max_abs_difference": worst}


def _check_lane(job: Path, lane: str, holdout: Any, r: int, state: dict[str, np.ndarray], digest: str, fail: Any) -> dict[str, Any] | None:
    """One round of one evaluation lane ("eval": the run's own cohort; "eval_g1": the unseen generalisation cohort): record, predictions, logits recomputed from the state, every metric, per-participant counts."""
    from studio.isolated_eval import isolated_logits

    x, y = holdout.inputs.reshape(len(holdout.inputs), 1, -1), np.asarray(holdout.labels).astype(int)
    owners = [str(o) for o in holdout.owners]
    tag = f"{lane} R{r}"
    record_path = job / lane / f"R{r:02d}" / "record.json"
    if not record_path.exists():
        fail(f"{tag}: no evaluation record")
        return None
    record = json.loads(record_path.read_text())
    if record.get("evaluation_status") != "COMPLETED" or record.get("global_state_digest") != digest:
        fail(f"{tag}: evaluation record not completed or bound to another state")
    predictions = job / lane / f"R{r:02d}" / "predictions.csv"
    pbytes = predictions.read_bytes()
    if _sha(pbytes) != record["prediction_artifact_reference"]["sha256"]:
        fail(f"{tag}: predictions.csv does not match its recorded SHA-256")
    labels_csv, logits_csv, owners_csv = _read_predictions(predictions)
    if not np.array_equal(labels_csv, y) or owners_csv != owners:
        fail(f"{tag}: predictions.csv labels/participants differ from the cohort holdout")
    logits = isolated_logits(state, x)
    diff = float(np.max(np.abs(logits - logits_csv)))
    if diff > 1e-6:
        fail(f"{tag}: stored logits differ from logits recomputed from the stored state ({diff:.2e})")
    mine = recompute_metrics(y, logits_csv)
    stored = record["metric_result"]
    for key, tol in METRIC_TOLERANCE.items():
        if not same(stored.get(key), mine[key], tol):
            fail(f"{tag}: {key} stored {stored.get(key)} != recomputed {mine[key]}")
    for key in COUNTS:
        if int(stored[key]) != mine[key]:
            fail(f"{tag}: {key} stored {stored[key]} != recomputed {mine[key]}")
    if int(record["windows"]) != len(y):
        fail(f"{tag}: window count differs")
    per = record.get("participant_metrics") or {}
    arr_owner = np.array(owners_csv)
    for pid, pm in per.items():
        sel = arr_owner == pid
        if not sel.any() or int(pm["windows"]) != int(sel.sum()):
            fail(f"{tag}: participant {pid} window count differs")
            continue
        pc = confusion(y[sel], sigmoid(logits_csv[sel]))
        if any(int(pm[k]) != pc[k] for k in COUNTS if k in pm):
            fail(f"{tag}: participant {pid} confusion counts differ")
    if sum(int(pm["windows"]) for pm in per.values()) != len(y):
        fail(f"{tag}: participant windows do not add up to the holdout")
    return {"max_logit_difference_vs_recomputed_from_state": diff, "metrics": {k: mine[k] for k in ("AUROC", "AUPRC", "F1", "BCE", "TP", "FP", "TN", "FN")}, "windows": int(len(y))}


def verify_run(job: Path, *, rederive: set[int] | None = None) -> dict[str, Any]:
    from federated.model_v2_fl import state_sha
    from studio import cohorts, g1_cohort

    meta = json.loads((job / "meta.json").read_text())
    rr = job / "run"
    report = json.loads((rr / "run_report.json").read_text())
    cohort, n_rounds = meta.get("cohort", cohorts.ORIGINAL), int(meta["run_length"])
    holdout, g1 = cohorts.holdout_provider(cohort)(), g1_cohort.load()
    y = np.asarray(holdout.labels).astype(int)
    owners = [str(o) for o in holdout.owners]
    by_round = {int(r["round"]): r for r in report["rounds"]}
    start_digest, start_name = expected_start_digest(meta)
    out: dict[str, Any] = {"run_id": meta["run_id"], "cohort": cohort, "init": meta.get("init"), "start": start_name, "rounds_planned": n_rounds, "algorithm": meta.get("algorithm"), "windows": int(len(y)),
                           "g1_windows": int(len(g1.labels)), "rounds": {}, "failures": []}

    def fail(msg: str) -> None:
        out["failures"].append(msg)

    prev_digest, prev_state = None, None
    for r in range(n_rounds + 1):
        state = _state(rr, r)
        digest = state_sha(state)
        row: dict[str, Any] = {"state_sha256": digest}
        if r == 0 and digest != start_digest:
            fail(f"R0: starting state {digest[:12]} is not the declared {start_name} {start_digest[:12]}")
        if r > 0:
            if by_round.get(r, {}).get("global_state_sha256") != digest:
                fail(f"R{r}: stored state digest differs from the run report")
            if by_round.get(r, {}).get("base_state_sha256") != prev_digest:
                fail(f"R{r}: the round's base digest is not the previous round's state")
        for key, value in state.items():
            if np.issubdtype(value.dtype, np.floating) and not np.isfinite(value).all():
                fail(f"R{r}: non-finite values in {key}")
            if prev_state is not None and not np.issubdtype(value.dtype, np.floating) and not np.array_equal(value, prev_state[key]):
                fail(f"R{r}: integer buffer {key} changed")
        lane = _check_lane(job, "eval", holdout, r, state, digest, fail)
        if lane is not None:
            row.update(lane)
        g1_lane = _check_lane(job, "eval_g1", g1, r, state, digest, fail) if (job / "eval_g1").exists() else None
        if g1_lane is not None:
            row["generalisation_lane"] = g1_lane
        if rederive and r in rederive and r > 0 and meta.get("mode") == "A":
            row["aggregation_rederivation"] = rederive_round(job, meta, r, prev_state, state)
            if not row["aggregation_rederivation"]["bit_identical"]:
                fail(f"R{r}: independently formed global state differs from the stored one")
        out["rounds"][str(r)] = row
        prev_digest, prev_state = digest, state
    paired_path = job / "eval" / "paired.json"
    if paired_path.exists() and all("metrics" in v for v in out["rounds"].values()):
        paired = json.loads(paired_path.read_text())
        a, b = int(paired["comparator"].lstrip("R")), int(paired["endpoint"].lstrip("R"))
        out["paired"] = {"comparator": a, "endpoint": b, "replicates": paired["replicates"]}
        za = np.array([float(r["logit"]) for r in csv.DictReader(io.StringIO((job / "eval" / f"R{a:02d}" / "predictions.csv").read_text()))])
        zb = np.array([float(r["logit"]) for r in csv.DictReader(io.StringIO((job / "eval" / f"R{b:02d}" / "predictions.csv").read_text()))])
        mine_a, mine_b = recompute_metrics(y, za), recompute_metrics(y, zb)
        for key in ("AUPRC", "AUROC", "F1", "accuracy", "BCE"):
            stored = paired["metrics"][key]
            diff = None if mine_a[key] is None or mine_b[key] is None else mine_b[key] - mine_a[key]
            for label, expect in (("A_point", mine_a[key]), ("B_point", mine_b[key]), ("difference_point", diff)):
                if not same(stored[label], expect, 1e-9):
                    fail(f"paired {key} {label}: stored {stored[label]} != recomputed {expect}")
        # the percentile intervals, with resampling code written here (same seed and draw order as documented: ONE participant-cluster draw per replicate, applied to both states)
        ids = sorted(set(owners))
        index = {i_: np.flatnonzero(np.array(owners) == i_) for i_ in ids}
        rng = np.random.default_rng(int(paired["seed"]))
        draws: dict[str, list[float]] = {k: [] for k in ("AUPRC", "AUROC", "F1")}
        for _ in range(int(paired["replicates"])):
            rows = np.concatenate([index[ids[c]] for c in rng.choice(len(ids), size=len(ids), replace=True)])
            yy = y[rows]
            if yy.min() == yy.max():
                continue
            ra, rb = recompute_metrics(yy, za[rows]), recompute_metrics(yy, zb[rows])
            for k in draws:
                if ra[k] is not None and rb[k] is not None:                    # a replicate where the metric is undefined for either state is not counted (as the engine does)
                    draws[k].append(rb[k] - ra[k])
        for k, values in draws.items():
            stored = paired["metrics"][k]["difference_interval"]
            if not values:
                if stored["lower"] is not None:
                    fail(f"paired {k}: stored difference interval exists but no replicate is defined here")
            elif stored["lower"] is None or abs(float(np.percentile(values, 2.5)) - stored["lower"]) > 1e-9 or abs(float(np.percentile(values, 97.5)) - stored["upper"]) > 1e-9:
                fail(f"paired {k}: stored difference interval differs from the one recomputed here")
        out["paired"]["intervals_recomputed"] = True
    out["ok"] = not out["failures"]
    return out


def verify_hardware_run(hardware_dir: Path, studio_dir: Path) -> dict[str, Any]:
    """The same independent verification for a pretrained / untrained / candidate-start RECORDED-HARDWARE run (V2 family): its states live in ``hardware_demo/<id>/fl10`` and its evaluation lanes in ``studio_runs/<id>``.
    A virtual job directory of links lets ``verify_run`` read it unchanged; the aggregation re-derivation is not offered (the recorded client's windows are not rebuilt here), every state, digest, prediction and metric is."""
    import tempfile

    run = json.loads((hardware_dir / "run.json").read_text())
    audit = (run.get("model") or {}).get("base_audit") or {}
    kind = audit.get("kind")
    init = "FL_INIT_V2" if kind == "UNTRAINED_INIT" else "CANDIDATE" if kind == "CANDIDATE" else "MODEL_V2_FINAL"
    meta = {"run_id": hardware_dir.name, "cohort": run.get("cohort", "ORIGINAL"), "run_length": int(run["rounds_planned"]), "init": init, "algorithm": run.get("algorithm"), "mode": "H", "base_audit": audit}
    with tempfile.TemporaryDirectory(prefix="nhm-verify-hw-") as tmp:
        job = Path(tmp) / hardware_dir.name
        job.mkdir()
        (job / "meta.json").write_text(json.dumps(meta))
        (job / "run").symlink_to(hardware_dir / "fl10")
        (job / "eval").symlink_to(studio_dir / "eval")
        if (studio_dir / "eval_g1").exists():
            (job / "eval_g1").symlink_to(studio_dir / "eval_g1")
        return verify_run(job, rederive=None)


def run_dirs(root: Path, only: str | None) -> list[Path]:
    return [d for d in sorted(root.glob("FL10RUN-*")) if (d / "meta.json").exists() and (d / "run" / "run_report.json").exists() and (only is None or d.name == only)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", required=True, help="the Studio run root (contains FL10RUN-* directories; each has meta.json, run/, eval/ and eval_g1/)")
    parser.add_argument("--run", default=None)
    parser.add_argument("--rederive", default="none", help="'all', 'none' or a comma-separated list of rounds whose aggregation is re-derived by retraining the clients")
    parser.add_argument("--out", default="reports/verification/fl_round_values.json")
    args = parser.parse_args(argv)
    rounds = None if args.rederive == "none" else (set(range(1, 1000)) if args.rederive == "all" else {int(x) for x in args.rederive.split(",")})
    results = []
    for d in run_dirs(Path(args.root), args.run):
        r = verify_run(d, rederive=rounds)
        results.append(r)
        checked = len(r["rounds"])
        derived = sum("aggregation_rederivation" in v for v in r["rounds"].values())
        print(f"{'PASS' if r['ok'] else 'FAIL'}  {r['run_id']}  {r['cohort']:16s} {r['rounds_planned']:2d} rounds from {r['start']:34s} rounds checked {checked}  aggregations re-derived {derived}", flush=True)
        for f in r["failures"]:
            print("      -", f)
    path = ROOT / args.out
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"runs": results, "all_ok": bool(results) and all(r["ok"] for r in results)}, indent=1, sort_keys=True, default=float) + "\n")
    return 0 if results and all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
