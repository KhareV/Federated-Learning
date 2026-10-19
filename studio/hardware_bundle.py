# ruff: noqa: E501
"""STUDIO_LIVE_BUNDLE_V1-compatible bundle for a RECORDED-HARDWARE federation run.

The Studio figure/table/overview builders consume one numeric bundle. This module assembles that same schema from a hardware demo run's own artifacts
(``run.json``, ``dataset.json`` and the per-round checkpoints), so a hardware run renders through exactly the same code and the same Live page as a synthetic run.

* Metrics are computed by the SAME functions the synthetic evaluator uses (``fl10.metrics.full_metrics`` / ``participant_metrics`` / ``final_showcase.metrics.curves``);
  nothing is re-implemented and nothing is typed here.
* Scoring is a deterministic re-evaluation of the stored checkpoints on the stored holdout features (the holdout never enters training).
* Fields that do not exist for a hardware run are reported as absent (None / empty), never invented. The data is recorded telemetry features with SYNTHETIC ASSIGNED
  labels: no clinical or diagnostic meaning."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from final_showcase import metrics as base_metrics
from fl10 import metrics as fl10_metrics
from studio.hardware_demo import CLIENT_IDS, FEATURES, MODEL_ID, WINDOW_SECONDS

SCHEMA = "STUDIO_LIVE_BUNDLE_V1"
ENGINE = "HARDWARE_DEMO"
MODE = "H"
SYNTHETIC_LABEL = "RECORDED HARDWARE WINDOWS · SYNTHETIC ASSIGNED LABELS · NOT CLINICAL · NOT DIAGNOSTIC"
COHORT_USE = "DIAGNOSTIC HOLDOUT OF RECORDED WINDOWS (window-level split, same recording sessions as training) — NOT AN INDEPENDENT TEST"
CLAIM = "RECORDED_HARDWARE_FEATURES_WITH_SYNTHETIC_ASSIGNED_LABELS_ENGINEERING_DEMO_ONLY_NOT_CLINICAL"
UNAVAILABLE_FOR_HARDWARE = "NOT APPLICABLE TO RECORDED-HARDWARE RUNS"
V2_LABEL = "RECORDED HARDWARE WINDOWS · RESAMPLED · PRETRAINED V2 FINE-TUNING · SYNTHETIC ASSIGNED LABELS · NOT VALID · NOT DIAGNOSTIC"
V2_LABEL_UNTRAINED = "RECORDED HARDWARE WINDOWS · RESAMPLED · UNTRAINED V2 NETWORK TRAINED FROM SCRATCH · SYNTHETIC ASSIGNED LABELS · NOT VALID · NOT DIAGNOSTIC"
V2_COHORT_USE = "DIAGNOSTIC HOLDOUT BLOCK OF THE RECORDING (time-purged, same sessions as training) — NOT AN INDEPENDENT TEST"


def _state_key(round_id: int) -> str:
    return f"R{round_id:02d}"


def _load_state(path: Path) -> dict[str, np.ndarray]:
    raw = json.loads(path.read_text())
    return {k: np.asarray(v, dtype=np.float64) for k, v in raw.items()}


def _logits(state: dict[str, np.ndarray], x: np.ndarray) -> np.ndarray:
    weight = next(v for k, v in state.items() if k.endswith("weight"))
    bias = next(v for k, v in state.items() if k.endswith("bias"))
    return (x @ weight.reshape(-1, x.shape[1]).T).reshape(-1) + float(bias.reshape(-1)[0])


def evaluation_states(run_dir: Path, run: dict[str, Any], dataset: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Per-state pooled/participant metrics + curves on the stored holdout; plus the holdout participant (session) composition."""
    if run["model"]["id"] == "MODEL_V2_FINAL":       # pretrained V2 fine-tuning on resampled recorded windows: V2 scorer, stored holdout block
        from studio import hardware_v2

        return hardware_v2.evaluation_states(run_dir, run, dataset)
    manifest = [w for w in dataset["window_manifest"] if w["split"] == "HOLDOUT"]
    x = np.asarray([w["normalized_features"] for w in manifest], dtype=np.float64)
    y = np.asarray([w["label"] for w in manifest], dtype=np.int64)
    owners = np.asarray([w["session_id"] for w in manifest])
    states: dict[str, Any] = {}
    for round_id in range(0, int(run["rounds_planned"]) + 1):
        path = run_dir / "checkpoints" / f"R{round_id:02d}.json"
        if not path.exists():
            continue
        z = _logits(_load_state(path), x)
        pooled = fl10_metrics.full_metrics(y, z)
        part = fl10_metrics.participant_metrics(owners, y, z)
        states[_state_key(round_id)] = {
            "pooled": pooled, "participants": part["per_participant"], "participant_macro_F1": part["participant_macro_F1"],
            "participants_defined": part["participants_defined"], "participants_undefined": part["participants_undefined"],
            "curves": base_metrics.curves(y, z),
        }
    participants = []
    for index, session in enumerate(sorted({str(o) for o in owners})):
        rows = [w for w in manifest if w["session_id"] == session]
        participants.append({
            "holdout_id": f"HOLDOUT_{index:02d}", "participant_id": session, "site_condition": "RECORDED_HARDWARE_SESSION", "replicate": 0,
            "session_id": session, "seed": int(run["dataset"]["label_assignment"]["seed"]), "dataset_sha256": run["dataset"]["input_feature_sha256"],
            "counts": {"windows_emitted": len(rows), "trainable": len(rows), "DEGRADED": 0, "UNUSABLE": 0,
                       "synthetic_positive": int(sum(w["label"] == 1 for w in rows)), "synthetic_negative": int(sum(w["label"] == 0 for w in rows))},
        })
    return states, participants


def build_hardware_bundle(run_dir: Path, run: dict[str, Any], dataset: dict[str, Any], *, evaluation_status: str = "COMPLETED") -> dict[str, Any]:
    n = int(run["rounds_planned"])
    status = run.get("status", "COMPLETED")
    v2 = run["model"]["id"] == "MODEL_V2_FINAL"
    untrained = v2 and (run["model"].get("base_audit") or {}).get("kind") == "UNTRAINED_INIT"
    states, holdout = evaluation_states(run_dir, run, dataset)
    digests = {_state_key(int(k)): v for k, v in run["state_progression"].items()}
    progression = {k: {"sha256": v, "finite": True} for k, v in run["state_progression"].items()}
    client_rounds: list[dict[str, Any]] = []
    batches: list[dict[str, Any]] = []
    updates: list[dict[str, Any]] = []
    rounds: list[dict[str, Any]] = []
    cumulative_updates = cumulative_bytes = cumulative_exposures = 0
    for row in run["rounds"]:
        r = int(row["round"])
        examples_total = sum(int(c["examples"]) for c in row["clients"].values())
        for client in (run.get("client_ids") or CLIENT_IDS):
            diag = row["clients"][client]
            client_rounds.append({
                "run_id": run["run_id"], "round": r, "client_id": client, "acceptance_status": "ACCEPTED",
                "examples_processed": int(diag["examples"]), "optimizer_steps": int(diag["optimizer_steps"]),
                "mean_training_loss": diag["mean_loss"], "final_training_loss": diag["final_loss"],
                "local_update_norm": diag.get("local_update_l2"), "gradient_norm_mean": float(np.mean(diag["step_gradient_norms"])) if diag.get("step_gradient_norms") else diag["gradient_norm"],
                "aggregation_weight": row["aggregation_weights"][client], "client_duration_seconds": diag.get("duration_seconds"),
                "update_sha256": diag["state_sha256"], "proximal_penalty": diag.get("final_proximal_penalty"),
            })
            updates.append({"round": r, "client_id": client, "update_sha256": diag["state_sha256"]})
            for step, (loss, grad) in enumerate(zip(diag.get("step_losses", []), diag.get("step_gradient_norms", []), strict=False), start=1):
                batches.append({"run_id": run["run_id"], "round": r, "client_id": client, "batch_index": step, "batch_size": int(diag["examples"]), "loss": loss, "gradient_l2_norm": grad})
        cumulative_updates += int(row["accepted_updates"])
        cumulative_exposures += examples_total
        cumulative_bytes += int(row.get("update_payload_bytes_total") or 0)
        rounds.append({
            "round": r, "expected_clients": 8, "received_updates": 8, "accepted_updates": int(row["accepted_updates"]), "rejected_updates": int(row["rejected_updates"]),
            "rejections": [], "total_accepted_example_weight": examples_total, "weighted_mean_training_loss": row["weighted_mean_training_loss"],
            "aggregated_update_norm": row.get("aggregated_update_norm"), "update_payload_bytes_total": row.get("update_payload_bytes_total"), "round_duration_seconds": row.get("round_duration_seconds"),
            "cumulative_accepted_updates": cumulative_updates, "cumulative_example_exposures": cumulative_exposures, "cumulative_payload_bytes": cumulative_bytes,
            "base_state_sha256": row["base_state_sha256"], "global_state_sha256": row["global_state_sha256"], "aggregation_state": "COMMITTED",
            "candidate_status": "FINAL ENGINEERING STATE (not promoted, not deployed)" if r == n else "INTERMEDIATE GLOBAL STATE",
            "state_info": {"finite": True}, "parity": {}, "state_artifact": f"checkpoints/R{r:02d}.json",
        })
    started = run.get("created_at")
    finished = run.get("completed_at")
    run_block = {
        "run_id": run["run_id"], "mode": MODE, "status": status, "planned_rounds": n, "rounds_committed": len(rounds), "started_at": started, "finished_at": finished,
        "settings": ({"local_objective": "BCE (+ FedProx proximal term)" if run["algorithm"] == "FEDPROX" else "BCE", "optimizer_label": "AdamW (reset every local epoch), one local epoch", "local_phrase": "for one local epoch",
                      "monitoring_text": "recorded telemetry session(s) -> resampled onto the V2 source grid -> PREPROC_V1 10 s windows (VALID only) -> ONE recorded client, federated with seven canonical synthetic peers",
                      "model": "MODEL_V2_FINAL", "features": [], "window_seconds": 10.0} if v2 else
                     {"local_objective": "BCE (+ FedProx proximal term)" if run["algorithm"] == "FEDPROX" else "BCE", "optimizer_label": "SGD, full-batch, 2 local steps", "local_phrase": "for two full-batch local steps",
                      "monitoring_text": "recorded telemetry session(s) -> 1 s windows -> 8 logical clients (contiguous blocks)",
                      "model": MODEL_ID, "features": list(FEATURES), "window_seconds": WINDOW_SECONDS}),
        "accepted_updates_total": cumulative_updates, "example_exposures_total": cumulative_exposures,
        "unique_training_windows": int(run["dataset"]["training_windows"]),
        "candidate": {"candidate_id": None, "promoted": False, "deployed": False, "label": "RECORDED-HARDWARE DEMO MODEL (not a candidate)"},
        "coordinator_identity": "FL10_COORDINATOR (unchanged, recorded-hardware V2 fine-tuning)" if v2 else "HARDWARE_DEMO_FEDAVG_COORDINATOR_V1", "prefix_equals_frozen_reference": {},
        "federation_engine": "FL10 runner + genuine V2 local optimiser (recorded-hardware windows)" if v2 else "HARDWARE_DEMO_SINGLE_PROCESS",
        "failure": None, "algorithm": run["algorithm"], "secagg_mode": run["secagg_mode"], "fedprox_mu": run.get("fedprox_mu"),
        "secagg_shadow": run.get("secagg_shadow"), "total_seconds": sum(float(r.get("round_duration_seconds") or 0.0) for r in run["rounds"]),
        "initialisation": {"model_id": run["model"]["initialisation"], "warm_start": run["model"].get("warm_start"), **({"base_audit": run["model"].get("base_audit")} if v2 else {})},
    }
    cohort = [
        {"client_id": client, "participant_id": client, "session_id": info.get("session_id") or ", ".join(run["source_session_ids"]), "dataset_sha256": info["feature_sha256"],
         "counts": {"windows_emitted": info["samples"], "trainable": info["samples"], "DEGRADED": 0, "UNUSABLE": 0,
                    "synthetic_positive": info["label_counts"]["1"], "synthetic_negative": info["label_counts"]["0"]}}
        for client, info in dataset["clients"].items()
    ]
    return {
        "schema_version": SCHEMA, "source_label": "RECORDED HARDWARE SESSION DATA (this account)", "run_id": run["run_id"], "run_length": n, "planned_rounds": n,
        "engine": ENGINE, "mode": MODE, "replay_of": None, "synthetic_label": (V2_LABEL_UNTRAINED if untrained else V2_LABEL) if v2 else SYNTHETIC_LABEL, "live_label": None,
        "protocol": {
            "id": "HARDWARE_DEMO_PROTOCOL_V1", "evaluation_protocol_id": "HARDWARE_DEMO_DIAGNOSTIC_EVAL_V1", "sha256": run["snapshot_sha256"], "holdout_manifest_sha256": run["dataset"]["label_sha256"],
            "uncertainty": None, "threshold": 0.5, "metric_definitions": {}, "probability_histogram": {"bins": fl10_metrics.HIST_BINS},
            "interpretation_boundaries": ([
                "Windows are real recorded telemetry resampled from ~20 Hz to 360 Hz (linear interpolation between real readings) under an UNVERIFIED ADC scaling assumption; MODEL_V2_FINAL was validated on MIT-BIH ECG, not on this signal chain.",
                "The recorded client's labels are deterministic and SYNTHETIC (assigned for the demonstration); the seven peers are the canonical synthetic cohort with their own synthetic event-window labels. The metrics measure agreement with the assigned labels on the recorded holdout only.",
                "The holdout is a time-purged block of the same recording sessions, so it is a diagnostic, not independent evidence.",
                "There is no clinical, diagnostic or scientific claim.",
            ] if v2 else [
                "Features are real recorded telemetry; labels are deterministic and SYNTHETIC (assigned for the demonstration).",
                "The holdout is a window-level split of the same recording sessions, so it is a diagnostic, not independent evidence.",
                "There is no clinical, diagnostic or scientific claim, and no transfer from MODEL_V2_FINAL.",
            ]),
            "research_question": (("Engineering demonstration: does federated training of an untrained V2-architecture network from scratch (FedAvg / FedProx, optional round-1 SecAgg+ shadow) run end to end on recorded hardware windows?" if untrained else "Engineering demonstration: does federated fine-tuning of the pretrained V2 model (FedAvg / FedProx, optional round-1 SecAgg+ shadow) run end to end on recorded hardware windows?") if v2 else
                                  "Engineering demonstration: does the federated optimisation path (FedAvg / FedProx, optional round-1 SecAgg+ shadow) run end to end on recorded telemetry windows?"),
            "primary_comparison": None,
        },
        "run": run_block, "state_progression": progression, "rounds": rounds, "client_rounds": client_rounds, "batches": batches, "updates": updates,
        "training_cohort": cohort, "monitoring_link": None,
        "evaluation": {
            "states": states, "status": {k: evaluation_status for k in states}, "failures": {}, "state_digests": digests, "windows": int(run["dataset"]["holdout_windows"]),
            "holdout_participants": holdout,
            "separation": {"train_vs_holdout_windows": {"participant_overlap": None, "session_overlap": None, "window_input_overlap": 0}},
            "separation_source": "WINDOW_IDS_DISJOINT_BY_CONSTRUCTION", "window_level_split": True, "threshold": 0.5, "calibration": "NONE",
            "round_selection": "NONE - no round, threshold or candidate is selected from diagnostic evaluation", "paired": None,
            "paired_not_applicable": "Paired participant-cluster intervals need several independent participants; recorded hardware sessions are not independent clusters.",
            "comparator": f"R{0:02d}", "endpoint": f"R{n:02d}", "cohort_use": V2_COHORT_USE if v2 else COHORT_USE, "cohort_use_detail": V2_COHORT_USE if v2 else COHORT_USE, "cohort_id": "RECORDED_HARDWARE_HOLDOUT",
            "protocol_sha256": run["snapshot_sha256"], "holdout_manifest_sha256": run["dataset"]["label_sha256"], "method_freeze_commit": None,
        },
        "historical_exposed": {"label": UNAVAILABLE_FOR_HARDWARE, "caveat": UNAVAILABLE_FOR_HARDWARE, "source": "none", "sha256": "", "states": {}},
        "scientific_bridge": {"comparability_rows": [], "verdict": "NOT_COMPARABLE", "limitations": ["Recorded-hardware demo metrics are not comparable to any scientific or synthetic-cohort result."],
                              "route": "/app/observatory/outcomes", "note": ("Recorded-hardware V2 runs fine-tune on resampled windows with synthetic assigned labels; they are not comparable to the real-ECG scientific results." if v2 else "Recorded-hardware demo runs use synthetic assigned labels and a tabular feature model; they are not comparable to the real-ECG scientific results.")},
        "revision": 1,
    }
