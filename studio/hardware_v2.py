# ruff: noqa: E501
"""Pretrained-V2 federated fine-tuning on RECORDED-HARDWARE windows.

The tabular hardware demo model cannot take V2 weights, so a hardware run that starts from ``MODEL_V2_FINAL`` uses the SAME machinery as a synthetic V2 run instead:

* windows: the recorded readings are resampled onto the 360 Hz grid exactly as the experimental Monitor path does (``api.hardware_v2_experimental``: linear interpolation between real
  readings only, documented ADC scaling ASSUMPTION), and the UNCHANGED ``WearableStreamRuntime`` (PREPROC_V1) builds and quality-grades the 10 s V2 windows. Every COMPLETE window is used
  whatever the grade (the VALID-only ``is_trainable`` rule of the synthetic cohort is deliberately not enforced here); windows the gate would have rejected are counted and named
  (``gate_overridden``), incomplete ones are counted and excluded, nothing is silently dropped;
* topology: ONE recorded client (all of the recording's training windows) federated with the SEVEN canonical synthetic peers of the cohort (SIM_FL_SITE_01..07, unchanged, event-window
  labels). The peers are the unchanged ``build_cohort`` datasets, so the frozen round-1 SecAgg+ shadow applies as it does for a synthetic run (it needs the canonical cohort's largest
  client size, 93, so the recorded client contributes at most 93 windows);
* training: ``fl10.runner.run_training`` (the unchanged ``Coordinator`` + ``train_local_epoch_v2`` / FedProx trainer, optional round-1 SecAgg+ shadow) starting from the verified
  ``MODEL_V2_FINAL`` state; no second federation engine;
* scoring: the isolated V2 scorer on a held-out block of the recording, purged so that no training window overlaps a holdout window in time.

LABELS ARE SYNTHETIC on the recorded client (deterministic, balanced, seeded): recorded telemetry carries no ground truth, so nothing here has diagnostic or scientific meaning. The peers keep their
cohort's synthetic event-window labels, so the two label sources are different and are named as such. V2 was validated on
MIT-BIH 360 Hz ECG, not on this signal chain; the resampled hardware windows are EXPERIMENTAL. The run exercises the federated machinery on real recorded signal shapes."""

from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

import numpy as np

from api.hardware_v2_experimental import ASSUMPTIONS, build_windows
from federated.virtual_client_source_v1 import WINDOW_SAMPLES, LocalDataset, dataset_semantic_sha, is_trainable, normalize_windows
from fl10 import metrics as fl10_metrics
from fl10.runner import atomic_write, load_state
from final_showcase import metrics as base_metrics
from product.hardware_telemetry import MAX_TRACE
from studio import v2_init
from studio.hardware_demo import canonical_digest

ENGINE_ID = "HARDWARE_V2"
MODEL_ID = v2_init.INIT_V2_FINAL
DATASET_VERSION = "HARDWARE_V2_WINDOWS_V1"
LABEL_VERSION = "SYNTHETIC_ASSIGNED_FOR_DEMO_V1"
WINDOW_US = 10_000_000          # a V2 window is 2500 samples at 250 Hz = 10 s (timestamps are right edges)
HOLDOUT_FRACTION = 0.2
MIN_TRAIN_WINDOWS = 16          # enough for a stable local epoch (batch statistics) and a meaningful share
MIN_HOLDOUT_WINDOWS = 4
MAX_CLIENT_WINDOWS = 93          # the canonical cohort's largest client (frozen SecAgg+ shadow input rule); more recorded windows are not used
HARDWARE_CLIENT_ID = "RECORDED_DEMO_CLIENT_00"
PEER_IDS = tuple(f"SIM_FL_SITE_{i:02d}" for i in range(1, 8))
CLIENT_IDS = (HARDWARE_CLIENT_ID, *PEER_IDS)
_PEERS: dict[str, Any] = {}
_PEERS_LOCK = threading.Lock()
MAX_STORED_READINGS = MAX_TRACE  # only the newest readings of a session are kept
LABEL = "RECORDED HARDWARE · RESAMPLED · PRETRAINED V2 FINE-TUNING · SYNTHETIC ASSIGNED LABELS · NOT VALID · NOT DIAGNOSTIC"
CLAIM = "RECORDED_HARDWARE_RESAMPLED_WINDOWS_WITH_SYNTHETIC_ASSIGNED_LABELS_V2_FINE_TUNING_ENGINEERING_DEMO_ONLY_NOT_CLINICAL"
COHORT_USE = "DIAGNOSTIC HOLDOUT BLOCK OF THE RECORDING (time-purged, same sessions as training) — NOT AN INDEPENDENT TEST"


def peer_datasets() -> list[LocalDataset]:
    """The seven canonical synthetic peers (SIM_FL_SITE_01..07), built once per process by the unchanged cohort builder (about 12 s the first time)."""
    with _PEERS_LOCK:
        if "peers" not in _PEERS:
            from federated.wearable_fl_runner_v1 import build_cohort

            _PEERS["peers"] = build_cohort()[1][1:]
        return list(_PEERS["peers"])


def _complete(event: dict[str, Any]) -> bool:
    """Full 10 s window of finite samples with no missing slots. The PREPROC_V1 quality grade is NOT required: hardware V2 runs are allowed whatever the grade says (it is reported, never hidden)."""
    samples = event["ecg"]["samples"]
    return len(samples) == WINDOW_SAMPLES and event["diagnostics"]["missing_slots"] == 0 and bool(np.isfinite(np.asarray(samples, dtype=np.float64)).all())


def _session_windows(records: list[dict[str, Any]], session_id: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = sorted((r for r in records if r["session_id"] == session_id), key=lambda r: (r["ingested_at"], r["document_id"]))
    events, summary = build_windows(rows, session_id, MODEL_ID)
    usable = [e for e in events if _complete(e)]
    by_quality: dict[str, int] = {}
    reasons: dict[str, int] = {}
    gate_reasons: dict[str, int] = {}
    overridden = 0
    for event in events:
        by_quality[event["ecg_quality"]] = by_quality.get(event["ecg_quality"], 0) + 1
        if not _complete(event):
            reasons["INCOMPLETE_WINDOW"] = reasons.get("INCOMPLETE_WINDOW", 0) + 1
        elif not is_trainable(event):
            overridden += 1
            for reason in event["diagnostics"].get("quality_reasons") or [event["ecg_quality"]]:
                gate_reasons[reason] = gate_reasons.get(reason, 0) + 1
    return usable, {"gate_overridden": overridden, "gate_reasons": gate_reasons, "session_id": session_id, "readings": len(rows), "resampled_records": summary["resampled_records"], "windows": len(events), "usable": len(usable), "by_quality": by_quality, "excluded_reasons": reasons}


def split_session(usable: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Chronological holdout block at the end of the session; training windows whose time span overlaps any holdout window are purged."""
    ordered = sorted(usable, key=lambda w: w["timestamp_us"])
    if len(ordered) < 3:
        return [], []
    count = max(1, round(len(ordered) * HOLDOUT_FRACTION))
    holdout = ordered[-count:]
    first = holdout[0]["timestamp_us"]
    train = [w for w in ordered[:-count] if w["timestamp_us"] <= first - WINDOW_US]
    return train, holdout


def preview(records: list[dict[str, Any]], session_ids: list[str]) -> dict[str, Any]:
    """What a V2 run would be able to use from these sessions (nothing is trained or written)."""
    sessions, train_total, holdout_total = [], 0, 0
    for session_id in session_ids:
        usable, info = _session_windows(records, session_id)
        train, holdout = split_session(usable)
        sessions.append(info | {"train": len(train), "holdout": len(holdout)})
        train_total += len(train)
        holdout_total += len(holdout)
    ok = train_total >= MIN_TRAIN_WINDOWS and holdout_total >= MIN_HOLDOUT_WINDOWS
    return {"sessions": sessions, "train_windows": train_total, "holdout_windows": holdout_total, "min_train_windows": MIN_TRAIN_WINDOWS, "min_holdout_windows": MIN_HOLDOUT_WINDOWS, "eligible": ok,
            "reason": None if ok else _insufficient(sessions, train_total, holdout_total), "assumptions": ASSUMPTIONS}


def _insufficient(sessions: list[dict[str, Any]], train_total: int, holdout_total: int) -> str:
    reasons: dict[str, int] = {}
    for s in sessions:
        for key, value in s["excluded_reasons"].items():
            reasons[key] = reasons.get(key, 0) + value
    detail = ", ".join(f"{k} ×{v}" for k, v in sorted(reasons.items(), key=lambda kv: -kv[1])) or "none"
    windows = sum(s["windows"] for s in sessions)
    capped = any(s["readings"] >= MAX_STORED_READINGS for s in sessions)
    hint = (f" NHM keeps at most the newest {MAX_STORED_READINGS} readings of a session (about {MAX_STORED_READINGS // 20 // 60} min at 20 Hz), so select more than one session."
            if capped else (" A V2 run needs about 4 minutes of clean recording (16 training + 4 holdout 10 s windows), so record longer or select more sessions." if windows < MIN_TRAIN_WINDOWS + MIN_HOLDOUT_WINDOWS else ""))
    return (f"INSUFFICIENT_V2_WINDOWS: {train_total} training and {holdout_total} holdout windows usable (need {MIN_TRAIN_WINDOWS} and {MIN_HOLDOUT_WINDOWS}) from {windows} 10 s windows; "
            f"incomplete windows excluded: {detail}. V2 trains on every complete 10 s window whatever its grade.{hint}")


def _label(windows: list[dict[str, Any]], seed: int, scope: str) -> dict[str, int]:
    ranked = sorted(windows, key=lambda w: hashlib.sha256(f"{seed}:{scope}:{w['window_id']}".encode()).hexdigest())
    return {w["window_id"]: index % 2 for index, w in enumerate(ranked)}


def _dataset(client: str, windows: list[dict[str, Any]], labels: dict[str, int], session_ids: list[str]) -> LocalDataset:
    inputs = normalize_windows(np.asarray([w["ecg"]["samples"] for w in windows]))
    y = np.asarray([labels[w["window_id"]] for w in windows], dtype=np.float32)
    edges = [int(w["timestamp_us"]) for w in windows]
    positives = int(y.sum())
    counts = {"source_records": None, "windows_emitted": len(windows), "VALID": len(windows), "DEGRADED": 0, "UNUSABLE": 0, "trainable": len(windows), "synthetic_positive": positives,
              "synthetic_negative": len(windows) - positives, "excluded_not_valid": 0, "excluded_valid_but_incomplete": 0}
    return LocalDataset(client, client, ", ".join(session_ids), inputs, y, tuple(edges), counts, dataset_semantic_sha(inputs, y, edges))


def prepare(demo: Any, owner: str, *, session_ids: list[str], rounds: int, algorithm: str, secagg_mode: str, label_seed: int, **_: Any) -> dict[str, Any]:
    """Validate and build everything that can fail on the caller's thread. Nothing is trained."""
    if rounds not in (3, 10) or algorithm not in ("FEDAVG", "FEDPROX") or secagg_mode not in ("PLAIN", "SECAGG_SHADOW"):
        raise ValueError("unsupported hardware demo configuration")
    if not 0 <= label_seed <= 2**31 - 1:
        raise ValueError("label_seed must be 0..2147483647")
    records = demo._records(owner, session_ids)
    state, audit = v2_init.load_v2_final()                       # fails closed on any digest / layout difference
    train_all: list[dict[str, Any]] = []
    holdout_sets: list[tuple[str, list[dict[str, Any]]]] = []
    infos: list[dict[str, Any]] = []
    for session_id in session_ids:
        usable, info = _session_windows(records, session_id)
        train, holdout = split_session(usable)
        infos.append(info | {"train": len(train), "holdout": len(holdout)})
        train_all.extend(w | {"session_id": session_id} for w in train)
        holdout_sets.append((session_id, [w | {"session_id": session_id} for w in holdout]))
    holdout_total = sum(len(h) for _, h in holdout_sets)
    if len(train_all) < MIN_TRAIN_WINDOWS or holdout_total < MIN_HOLDOUT_WINDOWS:
        raise ValueError(_insufficient(infos, len(train_all), holdout_total))
    for w in train_all:
        w["window_id"] = f"{w['session_id']}:{w['window_id']}"
    for _, rows in holdout_sets:
        for w in rows:
            w["window_id"] = f"{w['session_id']}:{w['window_id']}"
    train_all.sort(key=lambda w: (session_ids.index(w["session_id"]), w["timestamp_us"]))
    used = train_all[:MAX_CLIENT_WINDOWS]          # chronological; at most the canonical cohort's largest client (see module docstring)
    train_labels = _label(used, label_seed, "TRAIN")
    holdout_flat = [w for _, rows in holdout_sets for w in rows]
    holdout_labels = _label(holdout_flat, label_seed, "HOLDOUT")
    if {holdout_labels[w["window_id"]] for w in holdout_flat} != {0, 1}:
        raise ValueError("INSUFFICIENT_V2_WINDOWS: the holdout block cannot provide both synthetic classes")
    mine = _dataset(HARDWARE_CLIENT_ID, used, train_labels, session_ids)
    peers = peer_datasets()
    datasets = [mine, *peers]                      # ONE recorded client + seven canonical synthetic peers
    holdout = [_dataset(f"HOLDOUT_{i:02d}", rows, holdout_labels, [sid]) for i, (sid, rows) in enumerate(holdout_sets) if rows]
    run_id = f"HDFLRUN-{secrets.token_hex(6).upper()}"
    from datetime import UTC, datetime

    snapshot = {"version": DATASET_VERSION, "created_at": datetime.now(UTC).isoformat(), "owner_scope": owner, "session_ids": session_ids, "record_count": len(records), "records": records}
    snapshot["snapshot_sha256"] = canonical_digest(snapshot)
    client_manifest = {d.client_id: {"window_ids": [w["window_id"] for w in used] if d is mine else [], "samples": len(d.labels), "kind": "RECORDED" if d is mine else "SYNTHETIC_PEER",
                                     "session_id": ", ".join(session_ids) if d is mine else d.session_id,
                                     "label_counts": {"0": int(d.counts["synthetic_negative"]), "1": int(d.counts["synthetic_positive"])}, "feature_sha256": d.dataset_sha256} for d in datasets}
    used_ids = {w["window_id"] for w in used}
    all_windows = used + holdout_flat
    dataset = {
        "version": DATASET_VERSION, "feature_version": "PREPROC_V1_RESAMPLED_250HZ_10S_NORMALISED", "feature_names": [], "window_seconds": WINDOW_US / 1e6, "minimum_records": None,
        "windows_total": sum(i["windows"] for i in infos), "quality_gate": "NOT_ENFORCED_FOR_HARDWARE_V2", "gate_overridden_windows": sum(i["gate_overridden"] for i in infos), "training_windows": len(used), "training_windows_available": len(train_all), "topology": "ONE_RECORDED_CLIENT_PLUS_SEVEN_SYNTHETIC_PEERS", "holdout_windows": len(holdout_flat), "excluded_windows": [{"session_id": i["session_id"], "reasons": i["excluded_reasons"], "windows": i["windows"], "usable": i["usable"]} for i in infos],
        "sessions": infos, "label_assignment": {"version": LABEL_VERSION, "status": "SYNTHETIC_ASSIGNED_FOR_DEMO", "seed": label_seed, "classes": {"0": "NORMAL_MONITORED_PATTERN", "1": "POTENTIAL_ECTOPY_ASSOCIATED_PATTERN"}},
        "input_feature_sha256": canonical_digest({w["window_id"]: hashlib.sha256(json.dumps(w["ecg"]["samples"]).encode()).hexdigest() for w in all_windows}),
        "label_sha256": canonical_digest({**{k: v for k, v in train_labels.items() if k in used_ids}, **holdout_labels}), "normalization": {"scope": "PER_WINDOW_ZSCORE", "unit": "unchanged normalize_windows"}, "assumptions": ASSUMPTIONS,
        "clients": client_manifest, "holdout_window_ids": [w["window_id"] for w in holdout_flat],
        "window_manifest": [{"window_id": w["window_id"], "session_id": w["session_id"], "timestamp_us": int(w["timestamp_us"]), "label": (train_labels | holdout_labels)[w["window_id"]], "label_provenance": "SYNTHETIC_ASSIGNED_FOR_DEMO",
                             "split": "TRAIN" if w["window_id"] in used_ids else "HOLDOUT", "client_id": HARDWARE_CLIENT_ID if w["window_id"] in used_ids else None} for w in all_windows],
    }
    model_block = {"id": MODEL_ID, "architecture": audit["architecture_id"], "released": False, "v2_initialisation": "PRETRAINED_V2_FINE_TUNING", "initialisation": MODEL_ID, "warm_start": None,
                   "base_audit": {k: audit[k] for k in ("model_id", "checkpoint_sha256", "state_sha256", "state_entries", "architecture_id", "training_target_of_checkpoint")}}
    return {"engine": ENGINE_ID, "owner": owner, "run_id": run_id, "session_ids": session_ids, "rounds": rounds, "algorithm": algorithm, "secagg_mode": secagg_mode, "label_seed": label_seed,
            "initialisation": MODEL_ID, "warm_state": None, "warm_info": model_block["base_audit"], "records": records, "snapshot": snapshot, "dataset": dataset, "initial_state": state, "v2_audit": audit,
            "datasets": datasets, "holdout": holdout, "client_ids": list(CLIENT_IDS), "examples": {d.client_id: len(d.labels) for d in datasets}, "model_block": model_block,
            "claim_boundary": "ENGINEERING DEMO; one recorded client (resampled V2 windows, synthetic assigned labels) federated with seven synthetic cohort peers (synthetic event-window labels); MODEL_V2_FINAL was not validated on this signal chain; no clinical or scientific validity"}


def _binary_metrics(logits: np.ndarray, labels: np.ndarray) -> dict[str, Any]:
    scores = 1.0 / (1.0 + np.exp(-np.clip(logits, -60, 60)))
    pred = (scores >= 0.5).astype(np.int64)
    y = labels.astype(np.int64)
    tp, tn = int(np.sum((pred == 1) & (y == 1))), int(np.sum((pred == 0) & (y == 0)))
    fp, fn = int(np.sum((pred == 1) & (y == 0))), int(np.sum((pred == 0) & (y == 1)))
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * precision * recall / (precision + recall) if precision is not None and recall is not None and precision + recall else None
    eps = 1e-12
    bce = float(-np.mean(y * np.log(scores + eps) + (1 - y) * np.log(1 - scores + eps)))
    return {"BCE": bce, "accuracy": (tp + tn) / len(y), "precision": precision, "recall": recall, "F1": f1, "confusion": {"TP": tp, "FP": fp, "TN": tn, "FN": fn}, "windows": len(y)}


def holdout_arrays(holdout: list[LocalDataset]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    inputs = np.concatenate([d.inputs for d in holdout])
    labels = np.concatenate([d.labels for d in holdout]).astype(np.int64)
    owners = np.concatenate([[d.session_id] * len(d.labels) for d in holdout])
    return inputs, labels, owners


def train(demo: Any, ctx: dict[str, Any], progress: Any = None) -> dict[str, Any]:
    """Execute the prepared run through the unchanged FL10 runner; persist the same ``run.json`` / ``dataset.json`` contract as every recorded-hardware run."""
    from fl10 import runner
    from scripts.run_fl10 import git_head, protocol_sha
    from studio.isolated_eval import isolated_logits, prepare_template

    emit = progress or (lambda _event: None)
    run_id, rounds, algorithm, secagg_mode = ctx["run_id"], ctx["rounds"], ctx["algorithm"], ctx["secagg_mode"]
    directory = demo.root / run_id
    directory.mkdir(parents=True, exist_ok=True)
    fl_dir = directory / "fl10"
    started_at = _now()
    prepare_template()
    inputs, labels, owners = holdout_arrays(ctx["holdout"])
    np.savez_compressed(directory / "holdout.npz", inputs=inputs, labels=labels, owners=owners)
    (directory / "snapshot.json").write_text(json.dumps(ctx["snapshot"], indent=2, sort_keys=True) + "\n")
    (directory / "dataset.json").write_text(json.dumps(ctx["dataset"], indent=2, sort_keys=True) + "\n")
    manifest = {d.client_id: {"participant_id": d.participant_id, "session_id": d.session_id, "dataset_sha": d.dataset_sha256} for d in ctx["datasets"]}
    committed: list[dict[str, Any]] = []
    secagg: dict[str, Any] | None = None

    sink = ctx.get("state_sink")

    def mirror(round_id: int, sha: str) -> None:
        if sink is not None:       # the unseen-cohort (generalisation) lane scores every committed V2 state; a sink problem never touches training
            try:
                sink(run_id, rounds, round_id, load_state(fl_dir, round_id, sha), sha)
            except Exception:  # noqa: BLE001
                pass

    def relay(event: dict[str, Any]) -> None:
        nonlocal secagg
        if event["event"] == "SECAGG_SHADOW_VERIFIED":
            secagg = event.get("report")
        if event["event"] == "ROUND_OPENED" and event["round"] == 1:
            mirror(0, event["base_state_sha256"])
        elif event["event"] == "ROUND_COMMITTED":
            mirror(event["round"], event["global_state_sha256"])
        emit(event)
        if event["event"] == "ROUND_COMMITTED":
            committed.append(event)
            partial = _run_record(ctx, status="RUNNING", started_at=started_at, completed_at=None, report=_partial(fl_dir), secagg=secagg)
            (directory / "run.json").write_text(json.dumps(partial, indent=2, sort_keys=True) + "\n")

    report = runner.run_training(mode="H", run_id=run_id, out_dir=fl_dir, datasets=ctx["datasets"], manifest=manifest, rounds=rounds, require_prefix_parity=False, capture_batches=algorithm == "FEDAVG",
                                 progress=relay, git_commit=git_head(), protocol_sha256=protocol_sha(), algorithm=algorithm, secagg_mode=secagg_mode,
                                 initial_state=ctx["initial_state"], initialisation=ctx["v2_audit"])
    result = _run_record(ctx, status="COMPLETED", started_at=started_at, completed_at=_now(), report=report, secagg=report.get("secagg_shadow") or secagg)
    # per-round diagnostic evaluation on the holdout block (the bundle recomputes the full metric set from the stored states)
    for row in result["rounds"]:
        z = isolated_logits(load_state(fl_dir, row["round"], row["global_state_sha256"]), inputs)
        row["evaluation"] = _binary_metrics(z, labels)
    (directory / "run.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def _now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


def _partial(fl_dir: Path) -> dict[str, Any]:
    path = fl_dir / "run_report.partial.json"
    return json.loads(path.read_text()) if path.exists() else {"rounds": [], "client_rounds": [], "batches": [], "state_progression": {}}


def _rounds_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    """FL10 round / client-round / batch rows -> the recorded-hardware round-row contract consumed by ``studio.hardware_bundle``."""
    rows: list[dict[str, Any]] = []
    for r in report["rounds"]:
        n = int(r["round"])
        clients: dict[str, Any] = {}
        for cr in (c for c in report["client_rounds"] if c["round"] == n):
            steps = [b for b in report["batches"] if b["round"] == n and b["client_id"] == cr["client_id"]]
            clients[cr["client_id"]] = {
                "examples": int(cr["examples_processed"]), "optimizer_steps": int(cr["optimizer_steps"]), "mean_loss": cr["mean_training_loss"], "final_loss": cr["final_batch_loss"] if cr["final_batch_loss"] is not None else cr["mean_training_loss"],
                "final_proximal_penalty": None, "gradient_norm": cr["gradient_norm_mean"] if cr["gradient_norm_mean"] is not None else 0.0, "state_sha256": cr["update_sha256"], "local_update_l2": cr["local_update_norm"],
                "step_losses": [b["loss"] for b in steps], "step_gradient_norms": [b["gradient_l2_norm"] for b in steps], "duration_seconds": cr["client_duration_seconds"], "payload_bytes": int(cr["update_payload_bytes"]),
            }
        rows.append({"round": n, "base_state_sha256": r["base_state_sha256"], "global_state_sha256": r["global_state_sha256"], "accepted_updates": int(r["accepted_updates"]), "rejected_updates": int(r["rejected_updates"]),
                     "aggregation_weights": r["weights"], "weighted_mean_training_loss": r["weighted_mean_training_loss"], "optimizer_steps": sum(c["optimizer_steps"] for c in clients.values()), "clients": clients,
                     "evaluation": None, "round_duration_seconds": r["round_duration_seconds"], "update_payload_bytes_total": int(r["update_payload_bytes_total"]), "aggregated_update_norm": r.get("aggregated_update_norm"),
                     "started_at": None, "finished_at": None})
    return rows


def _run_record(ctx: dict[str, Any], *, status: str, started_at: str, completed_at: str | None, report: dict[str, Any], secagg: Any) -> dict[str, Any]:
    from studio.hardware_demo import MU

    progression = {"0": ctx["v2_audit"]["state_sha256"]} | {str(r["round"]): r["global_state_sha256"] for r in report.get("rounds", [])}
    return {
        "schema_version": "HARDWARE_DEMO_FL_RUN_V1", "run_id": ctx["run_id"], "owner": ctx["owner"], "created_at": started_at, "completed_at": completed_at, "status": status,
        "source_mode": "RECORDED_HARDWARE_DEMO", "source_session_ids": ctx["session_ids"], "source_record_count": len(ctx["records"]), "snapshot_sha256": ctx["snapshot"]["snapshot_sha256"],
        "dataset": ctx["dataset"], "model": ctx["model_block"], "algorithm": ctx["algorithm"], "fedprox_mu": MU if ctx["algorithm"] == "FEDPROX" else None, "secagg_mode": ctx["secagg_mode"],
        "aggregation": "PLAIN", "secagg_shadow": secagg, "rounds_planned": ctx["rounds"], "rounds": _rounds_rows(report), "state_progression": progression, "failure": None,
        "claim_boundary": ctx["claim_boundary"], "engine": ENGINE_ID, "fl10_run_dir": "fl10", "client_ids": ctx["client_ids"],
    }


# ---- evaluation / bundle support ------------------------------------------------------------------------------------------------------
def evaluation_states(run_dir: Path, run: dict[str, Any], dataset: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Pooled / participant (= recording session) metrics and curves of every stored V2 state on the stored holdout block."""
    from studio.isolated_eval import isolated_logits

    data = np.load(run_dir / "holdout.npz")
    inputs, labels, owners = data["inputs"], data["labels"].astype(np.int64), data["owners"]
    states: dict[str, Any] = {}
    fl_dir = run_dir / run.get("fl10_run_dir", "fl10")
    digests = run["state_progression"]
    for round_id in range(0, int(run["rounds_planned"]) + 1):
        sha = digests.get(str(round_id))
        if sha is None or not (fl_dir / f"states/R{round_id:02d}.bin").exists():
            continue
        z = isolated_logits(load_state(fl_dir, round_id, sha), inputs)
        part = fl10_metrics.participant_metrics(owners, labels, z)
        states[f"R{round_id:02d}"] = {"pooled": fl10_metrics.full_metrics(labels, z), "participants": part["per_participant"], "participant_macro_F1": part["participant_macro_F1"],
                                      "participants_defined": part["participants_defined"], "participants_undefined": part["participants_undefined"], "curves": base_metrics.curves(labels, z)}
    participants = []
    for index, session in enumerate(sorted({str(o) for o in owners})):
        mask = owners == session
        participants.append({"holdout_id": f"HOLDOUT_{index:02d}", "participant_id": session, "site_condition": "RECORDED_HARDWARE_SESSION", "replicate": 0, "session_id": session,
                             "seed": int(dataset["label_assignment"]["seed"]), "dataset_sha256": dataset["input_feature_sha256"],
                             "counts": {"windows_emitted": int(mask.sum()), "trainable": int(mask.sum()), "DEGRADED": 0, "UNUSABLE": 0, "synthetic_positive": int(labels[mask].sum()), "synthetic_negative": int((labels[mask] == 0).sum())}})
    return states, participants
