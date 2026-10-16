"""Recorded MongoDB telemetry to genuine toy federated learning.

This is an engineering demonstration with deterministic synthetic labels.  It is
deliberately separate from MODEL_V2_FINAL, AAMI-SVF, and the scientific evaluation
lanes.
"""

from __future__ import annotations

import hashlib
import json
import math
import secrets
import threading
import time
from collections import OrderedDict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import nn

from studio.hardware_demo_secagg import run_shadow

MODEL_ID = "HARDWARE_DEMO_MODEL_V1"
DATASET_VERSION = "HARDWARE_DEMO_DATASET_V1"
FEATURE_VERSION = "HARDWARE_DEMO_FEATURES_V1"
LABEL_VERSION = "SYNTHETIC_ASSIGNED_FOR_DEMO_V1"
CLIENT_IDS = tuple(f"RECORDED_DEMO_CLIENT_{i:02d}" for i in range(8))
FEATURES = (
    "ecg_mean", "ecg_std", "ecg_min", "ecg_max", "ecg_diff_abs_mean", "ecg_diff_std",
    "bpm_mean", "spo2_mean", "bpm_missing_fraction", "spo2_missing_fraction",
    "record_count", "window_duration_seconds",
)
WINDOW_SECONDS = 1.0
MIN_RECORDS = 10
MU = 0.1
LEARNING_RATE = 0.05
LOCAL_EPOCHS = 2


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _features(records: list[dict[str, Any]]) -> list[float]:
    ecg = np.asarray([r["ecg"] for r in records], dtype=np.float64)
    bpm = np.asarray([r["bpm"] for r in records if r["bpm"] is not None], dtype=np.float64)
    spo2 = np.asarray([r["spo2"] for r in records if r["spo2"] is not None], dtype=np.float64)
    stamps = [datetime.fromisoformat(r["ingested_at"]) for r in records]
    diff = np.diff(ecg)
    return [
        float(ecg.mean()), float(ecg.std()), float(ecg.min()), float(ecg.max()),
        float(np.abs(diff).mean()) if len(diff) else 0.0,
        float(diff.std()) if len(diff) else 0.0,
        float(bpm.mean()) if len(bpm) else 0.0,
        float(spo2.mean()) if len(spo2) else 0.0,
        1.0 - len(bpm) / len(records), 1.0 - len(spo2) / len(records),
        float(len(records)), float((max(stamps) - min(stamps)).total_seconds()),
    ]


def build_windows(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    windows: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    by_session: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_session.setdefault(record["session_id"], []).append(record)
    for session_id, rows in sorted(by_session.items()):
        rows.sort(key=lambda r: (r["ingested_at"], r["document_id"]))
        start = datetime.fromisoformat(rows[0]["ingested_at"])
        groups: dict[int, list[dict[str, Any]]] = {}
        for row in rows:
            index = int((datetime.fromisoformat(row["ingested_at"]) - start).total_seconds() // WINDOW_SECONDS)
            groups.setdefault(index, []).append(row)
        for index, group in sorted(groups.items()):
            window_id = f"{session_id}:W{index:05d}"
            if len(group) < MIN_RECORDS:
                excluded.append({"window_id": window_id, "reason": "FEWER_THAN_10_RECORDS", "record_count": len(group)})
                continue
            windows.append({
                "window_id": window_id,
                "session_id": session_id,
                "first_document_id": group[0]["document_id"],
                "last_document_id": group[-1]["document_id"],
                "started_at": group[0]["ingested_at"],
                "ended_at": group[-1]["ingested_at"],
                "record_count": len(group),
                "features": _features(group),
            })
    return windows, excluded


def assign_labels_and_split(windows: list[dict[str, Any]], seed: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if len(windows) < 20:
        raise ValueError("INSUFFICIENT_DATA: at least 20 eligible one-second windows are required")
    ranked = sorted(windows, key=lambda w: hashlib.sha256(f"{seed}:{w['window_id']}".encode()).hexdigest())
    labelled = []
    for index, window in enumerate(ranked):
        labelled.append({**window, "label": index % 2, "label_provenance": "SYNTHETIC_ASSIGNED_FOR_DEMO"})
    holdout_ids: set[str] = set()
    for label in (0, 1):
        members = [w for w in labelled if w["label"] == label]
        holdout_ids.update(w["window_id"] for w in members[: max(1, len(members) // 5)])
    train = sorted((w for w in labelled if w["window_id"] not in holdout_ids), key=lambda w: (w["started_at"], w["window_id"]))
    holdout = sorted((w for w in labelled if w["window_id"] in holdout_ids), key=lambda w: (w["started_at"], w["window_id"]))
    if len(train) < 16 or {w["label"] for w in holdout} != {0, 1}:
        raise ValueError("INSUFFICIENT_DATA: split cannot provide eight clients and a two-class holdout")
    return train, holdout


def partition_clients(train: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    parts = {client: [] for client in CLIENT_IDS}
    for index, window in enumerate(train):
        # Contiguous, near-equal chronological blocks: each window belongs once.
        client_index = min(len(CLIENT_IDS) - 1, index * len(CLIENT_IDS) // len(train))
        parts[CLIENT_IDS[client_index]].append(window)
    if any(not rows for rows in parts.values()):
        raise ValueError("INSUFFICIENT_DATA: every logical client needs at least one window")
    return parts


def _state(model: nn.Module) -> OrderedDict[str, np.ndarray]:
    return OrderedDict((k, v.detach().cpu().numpy().copy()) for k, v in model.state_dict().items())


def _restore(model: nn.Module, state: dict[str, np.ndarray]) -> None:
    model.load_state_dict(OrderedDict((k, torch.from_numpy(np.asarray(v).copy())) for k, v in state.items()), strict=True)


def _state_digest(state: dict[str, np.ndarray]) -> str:
    h = hashlib.sha256()
    for key, value in state.items():
        a = np.ascontiguousarray(value)
        h.update(key.encode() + b"\0" + str(a.dtype).encode() + b"\0" + str(a.shape).encode() + b"\0" + a.tobytes())
    return h.hexdigest()


def _model(seed: int) -> nn.Module:
    torch.manual_seed(seed)
    return nn.Sequential(nn.Linear(len(FEATURES), 1))


def _local_train(global_state: dict[str, np.ndarray], x: np.ndarray, y: np.ndarray, *, algorithm: str, seed: int, mu: float = MU) -> tuple[OrderedDict[str, np.ndarray], dict[str, Any]]:
    torch.manual_seed(seed)
    model = _model(seed)
    _restore(model, global_state)
    global_parameters = {name: value.detach().clone() for name, value in model.named_parameters()}
    optimizer = torch.optim.SGD(model.parameters(), lr=LEARNING_RATE)
    criterion = nn.BCEWithLogitsLoss()
    tx, ty = torch.from_numpy(x.astype(np.float32)), torch.from_numpy(y.astype(np.float32)).reshape(-1, 1)
    losses: list[float] = []
    proximal: list[float] = []
    gradient_norms: list[float] = []
    for _ in range(LOCAL_EPOCHS):
        optimizer.zero_grad(set_to_none=True)
        base = criterion(model(tx), ty)
        penalty = 0.5 * sum(torch.sum((p - global_parameters[name]) ** 2) for name, p in model.named_parameters())
        loss = base if algorithm == "FEDAVG" or mu == 0.0 else base + mu * penalty
        loss.backward()
        gradient_norms.append(math.sqrt(sum(float(torch.sum(p.grad**2)) for p in model.parameters() if p.grad is not None)))
        optimizer.step()
        losses.append(float(loss.detach()))
        proximal.append(float(penalty.detach()))
    local = _state(model)
    delta = math.sqrt(sum(float(np.sum((local[k].astype(np.float64) - global_state[k].astype(np.float64)) ** 2)) for k in local))
    return local, {
        "examples": len(y), "optimizer_steps": LOCAL_EPOCHS, "mean_loss": float(np.mean(losses)),
        "final_loss": losses[-1], "final_proximal_penalty": proximal[-1],
        "gradient_norm": gradient_norms[-1], "state_sha256": _state_digest(local),
        "weights_changed": _state_digest(local) != _state_digest(global_state),
        "step_losses": losses, "step_gradient_norms": gradient_norms, "local_update_l2": delta,
        "payload_bytes": int(sum(np.asarray(v).nbytes for v in local.values())),
    }


def _aggregate(states: dict[str, dict[str, np.ndarray]], examples: dict[str, int]) -> OrderedDict[str, np.ndarray]:
    total = sum(examples.values())
    first = next(iter(states.values()))
    return OrderedDict(
        (
            key,
            (sum(np.asarray(states[c][key], dtype=np.float64) * examples[c] for c in states) / total).astype(first[key].dtype),
        )
        for key in first
    )


def _metrics(state: dict[str, np.ndarray], x: np.ndarray, y: np.ndarray) -> dict[str, Any]:
    model = _model(0)
    _restore(model, state)
    with torch.no_grad():
        logits = model(torch.from_numpy(x.astype(np.float32))).reshape(-1)
        loss = float(nn.BCEWithLogitsLoss()(logits, torch.from_numpy(y.astype(np.float32))))
        scores = torch.sigmoid(logits).numpy()
    pred = (scores >= 0.5).astype(np.int64)
    tp, tn = int(np.sum((pred == 1) & (y == 1))), int(np.sum((pred == 0) & (y == 0)))
    fp, fn = int(np.sum((pred == 1) & (y == 0))), int(np.sum((pred == 0) & (y == 1)))
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * precision * recall / (precision + recall) if precision is not None and recall is not None and precision + recall else None
    return {"BCE": loss, "accuracy": (tp + tn) / len(y), "precision": precision, "recall": recall, "F1": f1, "confusion": {"TP": tp, "FP": fp, "TN": tn, "FN": fn}, "windows": len(y)}


class HardwareDemoService:
    def __init__(self, store: Any, root: Path):
        self.store = store
        self.root = Path(root) / "hardware_demo"
        self.root.mkdir(parents=True, exist_ok=True)
        self._run_lock = threading.Lock()

    def eligible_sessions(self, owner: str) -> list[dict[str, Any]]:
        with self.store._lock:
            rows = self.store._connection.execute(
                "SELECT s.id,s.started_at,s.stopped_at,s.record_count,COUNT(t.document_id) trace_count "
                "FROM hardware_sessions s LEFT JOIN hardware_trace t ON t.session_id=s.id "
                "WHERE s.owner=? AND s.status IN ('STOPPED','INTERRUPTED') GROUP BY s.id ORDER BY s.started_at DESC", (owner,)
            ).fetchall()
        return [dict(row) | {"eligible": int(row["trace_count"]) >= MIN_RECORDS * 20} for row in rows]

    def _records(self, owner: str, session_ids: list[str]) -> list[dict[str, Any]]:
        if not session_ids or len(session_ids) != len(set(session_ids)):
            raise ValueError("session_ids must be a non-empty unique list")
        records: list[dict[str, Any]] = []
        with self.store._lock:
            for session_id in session_ids:
                row = self.store._connection.execute("SELECT owner,status FROM hardware_sessions WHERE id=?", (session_id,)).fetchone()
                if row is None:
                    raise LookupError("unknown hardware session")
                if row["owner"] != owner:
                    raise PermissionError("hardware session belongs to another user")
                if row["status"] not in ("STOPPED", "INTERRUPTED"):
                    raise ValueError("only stopped hardware sessions are eligible")
                trace = self.store._connection.execute(
                    "SELECT document_id,ingested_at,ecg,bpm,spo2,collection FROM hardware_trace WHERE session_id=? ORDER BY ordinal", (session_id,)
                ).fetchall()
                records.extend(dict(item) | {"session_id": session_id} for item in trace)
        return records

    def list_runs(self, owner: str) -> list[dict[str, Any]]:
        result = []
        for path in self.root.glob("HDFLRUN-*/run.json"):
            data = json.loads(path.read_text())
            if data["owner"] == owner:
                result.append(data)
        return sorted(result, key=lambda item: item["created_at"], reverse=True)

    def get(self, owner: str, run_id: str) -> dict[str, Any]:
        path = self.root / run_id / "run.json"
        if not path.exists():
            raise LookupError("unknown hardware demo run")
        data = json.loads(path.read_text())
        if data["owner"] != owner:
            raise PermissionError("hardware demo run belongs to another user")
        return data

    def run(self, owner: str, *, session_ids: list[str], rounds: int, algorithm: str, secagg_mode: str, label_seed: int,
            initialisation: str = "FRESH_SEEDED", warm_start_run_id: str | None = None) -> dict[str, Any]:
        if not self._run_lock.acquire(blocking=False):
            raise RuntimeError("HARDWARE_DEMO_RUN_ALREADY_ACTIVE")
        try:
            return self._run(owner, session_ids=session_ids, rounds=rounds, algorithm=algorithm, secagg_mode=secagg_mode, label_seed=label_seed,
                             initialisation=initialisation, warm_start_run_id=warm_start_run_id)
        finally:
            self._run_lock.release()

    def _warm_start_state(self, owner: str, run_id: str | None) -> tuple[OrderedDict[str, np.ndarray], dict[str, Any]]:
        """Final global weights of an earlier recorded-hardware run of the SAME owner and model."""
        if not run_id:
            raise ValueError("WARM_START requires warm_start_run_id")
        previous = self.get(owner, run_id)  # LookupError / PermissionError: owner-scoped
        if previous.get("status") != "COMPLETED":
            raise ValueError("warm start source run is not completed")
        if previous.get("model", {}).get("id") != MODEL_ID:
            raise ValueError("warm start source is not a HARDWARE_DEMO_MODEL_V1 run")
        checkpoint = self.root / run_id / "checkpoints" / f"R{int(previous['rounds_planned']):02d}.json"
        raw = json.loads(checkpoint.read_text())
        reference = _state(_model(0))
        state: OrderedDict[str, np.ndarray] = OrderedDict()
        for key, value in reference.items():
            loaded = np.asarray(raw.get(key), dtype=np.float32)
            if loaded.shape != value.shape or not np.isfinite(loaded).all():
                raise ValueError("warm start checkpoint does not match HARDWARE_DEMO_MODEL_V1")
            state[key] = loaded
        return state, {"source_run_id": run_id, "source_round": int(previous["rounds_planned"]),
                       "source_state_sha256": _state_digest(state), "source_algorithm": previous.get("algorithm")}

    def prepare(self, owner: str, *, session_ids: list[str], rounds: int, algorithm: str, secagg_mode: str, label_seed: int,
                initialisation: str = "FRESH_SEEDED", warm_start_run_id: str | None = None) -> dict[str, Any]:
        """Validate and build everything that can fail on the caller's thread (data, windows, split, warm start). Nothing is trained."""
        if initialisation == "MODEL_V2_FINAL":       # pretrained V2 fine-tuning on resampled recorded windows: a different model family, built by studio.hardware_v2
            from studio import hardware_v2

            return hardware_v2.prepare(self, owner, session_ids=session_ids, rounds=rounds, algorithm=algorithm, secagg_mode=secagg_mode, label_seed=label_seed)
        if initialisation not in ("FRESH_SEEDED", "WARM_START"):
            raise ValueError("unsupported starting model for HARDWARE_DEMO_MODEL_V1")
        warm_state, warm_info = (None, None)
        if initialisation == "WARM_START":
            warm_state, warm_info = self._warm_start_state(owner, warm_start_run_id)
        if rounds not in (3, 10) or algorithm not in ("FEDAVG", "FEDPROX") or secagg_mode not in ("PLAIN", "SECAGG_SHADOW"):
            raise ValueError("unsupported hardware demo configuration")
        if not 0 <= label_seed <= 2**31 - 1:
            raise ValueError("label_seed must be 0..2147483647")
        records = self._records(owner, session_ids)
        run_id = f"HDFLRUN-{secrets.token_hex(6).upper()}"
        snapshot = {"version": DATASET_VERSION, "created_at": _iso_now(), "owner_scope": owner, "session_ids": session_ids, "record_count": len(records), "records": records}
        snapshot["snapshot_sha256"] = canonical_digest(snapshot)
        windows, excluded = build_windows(records)
        train, holdout = assign_labels_and_split(windows, label_seed)
        clients = partition_clients(train)
        train_matrix = np.asarray([w["features"] for w in train], dtype=np.float64)
        mean, std = train_matrix.mean(axis=0), train_matrix.std(axis=0)
        std[std == 0] = 1.0
        normalized = {w["window_id"]: ((np.asarray(w["features"]) - mean) / std).tolist() for w in windows}
        feature_digest = canonical_digest({w["window_id"]: w["features"] for w in windows})
        label_digest = canonical_digest({w["window_id"]: w["label"] for w in train + holdout})
        client_manifest = {
            client: {"window_ids": [w["window_id"] for w in rows], "samples": len(rows),
                     "label_counts": {str(label): sum(w["label"] == label for w in rows) for label in (0, 1)},
                     "feature_sha256": canonical_digest({w["window_id"]: normalized[w["window_id"]] for w in rows})}
            for client, rows in clients.items()
        }
        client_by_window = {w["window_id"]: client for client, rows in clients.items() for w in rows}
        labelled_by_window = {w["window_id"]: w for w in train + holdout}
        dataset = {
            "version": DATASET_VERSION, "feature_version": FEATURE_VERSION, "feature_names": FEATURES,
            "window_seconds": WINDOW_SECONDS, "minimum_records": MIN_RECORDS, "windows_total": len(windows),
            "training_windows": len(train), "holdout_windows": len(holdout), "excluded_windows": excluded,
            "label_assignment": {"version": LABEL_VERSION, "status": "SYNTHETIC_ASSIGNED_FOR_DEMO", "seed": label_seed, "classes": {"0": "DEMO_CLASS_A", "1": "DEMO_CLASS_B"}},
            "input_feature_sha256": feature_digest, "label_sha256": label_digest,
            "normalization": {"mean": mean.tolist(), "std": std.tolist(), "fit_scope": "TRAIN_ONLY"},
            "clients": client_manifest, "holdout_window_ids": [w["window_id"] for w in holdout],
            "window_manifest": [
                {"window_id": w["window_id"], "session_id": w["session_id"], "first_document_id": w["first_document_id"], "last_document_id": w["last_document_id"],
                 "record_count": w["record_count"], "features": w["features"], "normalized_features": normalized[w["window_id"]],
                 "label": labelled_by_window[w["window_id"]]["label"], "label_provenance": "SYNTHETIC_ASSIGNED_FOR_DEMO",
                 "split": "TRAIN" if w["window_id"] in client_by_window else "HOLDOUT", "client_id": client_by_window.get(w["window_id"])}
                for w in sorted(windows, key=lambda item: (item["started_at"], item["window_id"]))
            ],
        }
        return {"owner": owner, "run_id": run_id, "session_ids": session_ids, "rounds": rounds, "algorithm": algorithm, "secagg_mode": secagg_mode,
                "label_seed": label_seed, "initialisation": initialisation, "warm_state": warm_state, "warm_info": warm_info, "records": records,
                "snapshot": snapshot, "dataset": dataset, "train": train, "holdout": holdout, "clients": clients, "normalized": normalized,
                "examples": {c: len(clients[c]) for c in CLIENT_IDS}}

    def _run(self, owner: str, **config: Any) -> dict[str, Any]:
        return self.train(self.prepare(owner, **config))

    def train(self, ctx: dict[str, Any], progress: Any = None) -> dict[str, Any]:
        """Execute the prepared run. ``progress`` receives the same event vocabulary as the FL10 runner (ROUND_OPENED, CLIENT_TRAINING_STARTED/FINISHED,
        UPDATES_ACCEPTED, SECAGG_SHADOW_VERIFIED, ROUND_COMMITTED) at the moment each step really happened."""
        if ctx.get("engine") == "HARDWARE_V2":
            from studio import hardware_v2

            return hardware_v2.train(self, ctx, progress)
        emit = progress or (lambda _event: None)
        owner, run_id, session_ids, rounds = ctx["owner"], ctx["run_id"], ctx["session_ids"], ctx["rounds"]
        algorithm, secagg_mode, label_seed = ctx["algorithm"], ctx["secagg_mode"], ctx["label_seed"]
        initialisation, warm_state, warm_info = ctx["initialisation"], ctx["warm_state"], ctx["warm_info"]
        records, snapshot, dataset = ctx["records"], ctx["snapshot"], ctx["dataset"]
        train, holdout, clients, normalized = ctx["train"], ctx["holdout"], ctx["clients"], ctx["normalized"]
        directory = self.root / run_id
        directory.mkdir(parents=True, exist_ok=True)
        started_at = _iso_now()
        torch.use_deterministic_algorithms(True)
        model = _model(label_seed)
        global_state = warm_state if warm_state is not None else _state(model)
        progression = {"0": _state_digest(global_state)}
        (directory / "checkpoints").mkdir(exist_ok=True)
        (directory / "snapshot.json").write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n")
        (directory / "dataset.json").write_text(json.dumps(dataset, indent=2, sort_keys=True) + "\n")
        (directory / "checkpoints" / "R00.json").write_text(json.dumps({k: v.tolist() for k, v in global_state.items()}, sort_keys=True) + "\n")
        round_rows: list[dict[str, Any]] = []
        secagg = None
        for round_id in range(1, rounds + 1):
            round_t0 = time.perf_counter()
            round_started = _iso_now()
            emit({"event": "ROUND_OPENED", "round": round_id, "base_state_sha256": _state_digest(global_state)})
            local_states: dict[str, OrderedDict[str, np.ndarray]] = {}
            diagnostics: dict[str, dict[str, Any]] = {}
            examples: dict[str, int] = {}
            for client_index, client in enumerate(CLIENT_IDS):
                rows = clients[client]
                x = np.asarray([normalized[w["window_id"]] for w in rows], dtype=np.float32)
                y = np.asarray([w["label"] for w in rows], dtype=np.int64)
                emit({"event": "CLIENT_TRAINING_STARTED", "round": round_id, "client_id": client})
                t0 = time.perf_counter()
                local, diag = _local_train(global_state, x, y, algorithm=algorithm, seed=label_seed + round_id * 100 + client_index)
                diag["duration_seconds"] = time.perf_counter() - t0
                local_states[client], diagnostics[client], examples[client] = local, diag, len(rows)
                emit({"event": "CLIENT_TRAINING_FINISHED", "round": round_id, "client_id": client, "mean_loss": diag["mean_loss"], "examples": len(rows), "update_sha256": diag["state_sha256"]})
            emit({"event": "UPDATES_ACCEPTED", "round": round_id, "accepted_clients": list(CLIENT_IDS), "accepted_updates": len(CLIENT_IDS)})
            if round_id == 1 and secagg_mode == "SECAGG_SHADOW":
                secagg = run_shadow({c: [np.asarray(v) for v in local_states[c].values()] for c in CLIENT_IDS}, examples)
                if secagg.get("status") == "PASS":
                    emit({"event": "SECAGG_SHADOW_VERIFIED", "round": 1})
            committed = _aggregate(local_states, examples)
            if not all(np.isfinite(value).all() for value in committed.values()):
                raise RuntimeError("nonfinite aggregate")
            before, after = _state_digest(global_state), _state_digest(committed)
            if before == after:
                raise RuntimeError("optimizer produced no global state change")
            global_state = committed
            progression[str(round_id)] = after
            hx = np.asarray([normalized[w["window_id"]] for w in holdout], dtype=np.float32)
            hy = np.asarray([w["label"] for w in holdout], dtype=np.int64)
            round_rows.append({
                "round": round_id, "base_state_sha256": before, "global_state_sha256": after,
                "accepted_updates": 8, "rejected_updates": 0, "aggregation_weights": {c: examples[c] / sum(examples.values()) for c in CLIENT_IDS},
                "weighted_mean_training_loss": sum(diagnostics[c]["mean_loss"] * examples[c] for c in CLIENT_IDS) / sum(examples.values()),
                "optimizer_steps": sum(diagnostics[c]["optimizer_steps"] for c in CLIENT_IDS),
                "clients": diagnostics, "evaluation": _metrics(global_state, hx, hy),
                "started_at": round_started, "finished_at": _iso_now(), "round_duration_seconds": time.perf_counter() - round_t0,
                "update_payload_bytes_total": sum(diagnostics[c]["payload_bytes"] for c in CLIENT_IDS),
            })
            (directory / "checkpoints" / f"R{round_id:02d}.json").write_text(json.dumps({k: v.tolist() for k, v in global_state.items()}, sort_keys=True) + "\n")
            partial = self._result(ctx, status="RUNNING", started_at=started_at, completed_at=None, secagg=secagg, round_rows=round_rows, progression=progression)
            (directory / "run.json").write_text(json.dumps(partial, indent=2, sort_keys=True) + "\n")
            emit({"event": "ROUND_COMMITTED", "round": round_id, "global_state_sha256": after})
        result = self._result(ctx, status="COMPLETED", started_at=started_at, completed_at=_iso_now(), secagg=secagg, round_rows=round_rows, progression=progression)
        (directory / "run.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        return result

    @staticmethod
    def _result(ctx: dict[str, Any], *, status: str, started_at: str, completed_at: str | None, secagg: Any, round_rows: list[dict[str, Any]],
                progression: dict[str, str], failure: dict[str, str] | None = None) -> dict[str, Any]:
        return {
            "schema_version": "HARDWARE_DEMO_FL_RUN_V1", "run_id": ctx["run_id"], "owner": ctx["owner"],
            "created_at": started_at, "completed_at": completed_at, "status": status,
            "source_mode": "RECORDED_HARDWARE_DEMO", "source_session_ids": ctx["session_ids"],
            "source_record_count": len(ctx["records"]), "snapshot_sha256": ctx["snapshot"]["snapshot_sha256"],
            "dataset": ctx["dataset"], "model": ctx.get("model_block") or {"id": MODEL_ID, "architecture": f"Linear({len(FEATURES)},1)", "released": False, "v2_initialisation": "NOT_APPLICABLE",
                                                                           "initialisation": ctx["initialisation"], "warm_start": ctx["warm_info"]},
            "algorithm": ctx["algorithm"], "fedprox_mu": MU if ctx["algorithm"] == "FEDPROX" else None, "secagg_mode": ctx["secagg_mode"],
            "aggregation": "PLAIN", "secagg_shadow": secagg, "rounds_planned": ctx["rounds"],
            "rounds": round_rows, "state_progression": progression, "failure": failure,
            "claim_boundary": ctx.get("claim_boundary") or "TOY ENGINEERING DEMO; recorded telemetry features with synthetic assigned labels; no clinical or scientific validity",
        }
