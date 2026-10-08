# ruff: noqa: E501
"""Independent evaluation of R0-R10 on the frozen fresh 16-participant holdout (NHM_FL10_SYNTHETIC_EVALUATION_V1). Evaluation only: no gradient step, no selection."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import numpy as np

from federated.virtual_client_source_v1 import LocalDataset, dataset_semantic_sha
from final_showcase import metrics as base_metrics
from final_showcase.evaluate import logits_for
from fl10 import holdout, metrics
from fl10.runner import atomic_write, load_state

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = Path("configs/fl10/protocol_v1.json")
MANIFEST = Path("configs/fl10/holdout_manifest_v1.json")
STATES = [f"R{r:02d}" for r in range(11)]


class Fl10EvalError(RuntimeError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}:{detail}")
        self.code, self.detail = code, detail


def sha256_file(path: Path) -> str:
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def verify_method_freeze(commit: str) -> dict[str, str]:
    out = {}
    for path in (PROTOCOL, MANIFEST):
        committed = subprocess.run(["git", "show", f"{commit}:{path}"], cwd=ROOT, capture_output=True, check=True).stdout
        if hashlib.sha256(committed).hexdigest() != sha256_file(path):
            raise Fl10EvalError("PROTOCOL_CHANGED_AFTER_METHOD_FREEZE", str(path))
        out[str(path)] = sha256_file(path)
    if subprocess.run(["git", "merge-base", "--is-ancestor", commit, "HEAD"], cwd=ROOT).returncode != 0:
        raise Fl10EvalError("METHOD_COMMIT_NOT_ANCESTOR")
    return out


def window_hashes(d: LocalDataset) -> set[str]:
    return {hashlib.sha256(np.ascontiguousarray(w).tobytes()).hexdigest() for w in d.inputs}


def separation(holdout_sets: list[LocalDataset], excluded: dict[str, list[LocalDataset]]) -> dict[str, Any]:
    """Zero-overlap proof against every excluded population (participants, sessions, window inputs) and the declared seeds."""
    held_parts, held_sessions = {d.participant_id for d in holdout_sets}, {d.session_id for d in holdout_sets}
    held_windows = set().union(*(window_hashes(d) for d in holdout_sets))
    out: dict[str, Any] = {}
    for name, sets in excluded.items():
        parts, sessions = {d.participant_id for d in sets}, {d.session_id for d in sets}
        win = set().union(*(window_hashes(d) for d in sets)) if sets else set()
        row = {"participant_overlap": len(held_parts & parts), "session_overlap": len(held_sessions & sessions), "window_input_overlap": len(held_windows & win), "excluded_windows": len(win)}
        out[name] = row
        if row["participant_overlap"] or row["session_overlap"] or row["window_input_overlap"]:
            raise Fl10EvalError("EVALUATION_OVERLAP", f"{name}:{row}")
    return out


def check_manifest(protocol: dict[str, Any], datasets: list[LocalDataset]) -> list[dict[str, Any]]:
    if sha256_file(MANIFEST) != protocol["holdout"]["manifest_sha256"]:
        raise Fl10EvalError("HOLDOUT_MANIFEST_HASH_MISMATCH")
    manifest = json.loads((ROOT / MANIFEST).read_text())
    entries = manifest["participants"]
    if len(entries) != len(datasets) != holdout.COUNT:
        raise Fl10EvalError("HOLDOUT_SIZE_MISMATCH")
    for entry, d in zip(entries, datasets, strict=True):
        if dataset_semantic_sha(d.inputs, d.labels, d.right_edges_us) != entry["dataset_sha256"] or d.counts != entry["counts"] or d.participant_id != entry["participant_id"]:
            raise Fl10EvalError("HOLDOUT_DATASET_DIFFERS_FROM_MANIFEST", entry["holdout_id"])
    return entries


def require_both_classes(datasets: list[LocalDataset]) -> None:
    labels = np.concatenate([d.labels for d in datasets])
    if len(set(labels.astype(int).tolist())) < 2:
        raise Fl10EvalError("MISSING_CLASS_IN_HOLDOUT")


def evaluate_states(states: dict[str, dict[str, np.ndarray]], datasets: list[LocalDataset], *, replicates: int, seed: int, comparator: str = "R03", endpoint: str = "R10") -> dict[str, Any]:
    inputs = np.concatenate([d.inputs for d in datasets])
    labels = np.concatenate([d.labels for d in datasets]).astype(int)
    owners = np.concatenate([[d.participant_id] * len(d.labels) for d in datasets])
    logits = {name: logits_for(state, inputs) for name, state in states.items()}
    for name, z in logits.items():
        if not np.isfinite(z).all():
            raise Fl10EvalError("NONFINITE_LOGITS", name)
    result: dict[str, Any] = {"states": {}, "windows": int(labels.size)}
    for name, z in logits.items():
        pooled = metrics.full_metrics(labels, z)
        part = metrics.participant_metrics(owners, labels, z)
        result["states"][name] = {"pooled": pooled, "participants": part["per_participant"], "participant_macro_F1": part["participant_macro_F1"], "participants_defined": part["participants_defined"],
                                  "participants_undefined": part["participants_undefined"], "curves": base_metrics.curves(labels, z)}
    if comparator in logits and endpoint in logits:
        result["paired"] = {"comparator": comparator, "endpoint": endpoint, **metrics.paired_cluster_bootstrap(owners, labels, logits[comparator], logits[endpoint], replicates=replicates, seed=seed)}
    result["_logits"], result["_labels"], result["_owners"] = logits, labels, owners
    return result


def write_outputs(out_dir: Path, result: dict[str, Any], datasets: list[LocalDataset], extra: dict[str, Any]) -> dict[str, str]:
    logits = result.pop("_logits")
    result.pop("_labels")
    result.pop("_owners")
    names = list(logits)
    rows = []
    n = 0
    for d in datasets:
        for i in range(len(d.labels)):
            rows.append([d.client_id, d.participant_id, i, int(d.right_edges_us[i]), int(d.labels[i]), *[f"{logits[s][n]:.9g}" for s in names]])
            n += 1
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "holdout_predictions.csv").open("w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["holdout_id", "participant_id", "window_index", "right_edge_us", "label", *[f"logit_{s}" for s in names]])
        w.writerows(rows)
    with (out_dir / "participant_metrics.csv").open("w", newline="") as fh:
        cols = ["state", "participant_id", "windows", "positives", "negatives", "AUPRC", "AUROC", "F1", "precision", "recall", "specificity", "balanced_accuracy", "accuracy", "TP", "FP", "TN", "FN", "BCE", "Brier"]
        w = csv.writer(fh, lineterminator="\n")
        w.writerow([*cols, "undefined_reasons"])
        for s, block in result["states"].items():
            for pid, m in block["participants"].items():
                w.writerow([s, pid, *[("" if m[c] is None else m[c]) for c in cols[2:]], ";".join(f"{k}:{v}" for k, v in m["undefined"].items())])
    body = {**extra, **result}
    atomic_write(out_dir / "evaluation_results.json", (json.dumps(body, indent=1, sort_keys=True, default=float) + "\n").encode())
    return {"evaluation_results.json": sha256_path(out_dir / "evaluation_results.json"), "holdout_predictions.csv": sha256_path(out_dir / "holdout_predictions.csv"), "participant_metrics.csv": sha256_path(out_dir / "participant_metrics.csv")}


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evaluate_run(run_dir: Path, out_dir: Path, *, method_commit: str, training_datasets: list[LocalDataset], extra_excluded: dict[str, list[LocalDataset]] | None = None) -> dict[str, Any]:
    """Evaluate every committed state of a COMPLETED run. The protocol bytes must equal the method-freeze commit; the run's own digests are verified before use."""
    freeze = verify_method_freeze(method_commit)
    protocol = json.loads((ROOT / PROTOCOL).read_text())
    report = json.loads((run_dir / "run_report.json").read_text())
    if report["status"] != "COMPLETED" or report["rounds_committed"] != 10:
        raise Fl10EvalError("RUN_NOT_A_COMPLETED_TEN_ROUND_RUN", report["status"])
    datasets = [holdout.build_dataset(p) for p in holdout.profiles()]
    entries = check_manifest(protocol, datasets)
    from final_showcase.holdout import build_holdout_dataset, holdout_profiles

    excluded = {"training_cohort_8_clients": training_datasets, "previous_exposed_holdout_8_participants": [build_holdout_dataset(p) for p in holdout_profiles()], **(extra_excluded or {})}
    sep = separation(datasets, excluded)
    require_both_classes(datasets)
    prog = report["state_progression"]
    states = {f"R{r:02d}": load_state(run_dir, r, prog[str(r)]["sha256"]) for r in range(11)}
    boot = protocol["uncertainty"]
    result = evaluate_states(states, datasets, replicates=boot["replicates"], seed=boot["seed"])
    extra = {"protocol_id": protocol["protocol_id"], "protocol_sha256": sha256_file(PROTOCOL), "holdout_manifest_sha256": sha256_file(MANIFEST), "method_freeze_commit": method_commit, "method_freeze_verified": freeze,
             "run_id": report["run_id"], "mode": report["mode"], "state_digests": {s: prog[str(int(s[1:]))]["sha256"] for s in states}, "separation": sep, "holdout_participants": entries,
             "final_candidate_digest": report["candidate"]["state_sha256"], "threshold": metrics.THRESHOLD, "calibration": "NONE", "round_selection": "NONE - R10 is the predeclared endpoint"}
    hashes = write_outputs(out_dir, result, datasets, extra)
    return {"hashes": hashes, "result": result, "extra": extra}
