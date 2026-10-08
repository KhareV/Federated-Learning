# ruff: noqa: E501
"""Run NHM_SYNTH_FL_EVAL_PROTOCOL_V1 on genuine global states of a completed canonical sandbox run (RESULT step; protocol already frozen).
  python -m scripts.run_synth_fl_eval --method-commit <sha> --out reports/final_showcase/synth_fl_eval [--run-root DIR --run-id ID]
Without --run-root a fresh canonical run is executed in a new temp directory (the unmodified FederationService; same code path as the product)."""

from __future__ import annotations

import argparse
import csv
import json
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
from fastapi.testclient import TestClient

from federated.model_v2_fl import fresh_initial_state_v2
from federated.wearable_fl_runner_v1 import BASE_SEED, build_cohort
from final_showcase import evaluate as ev
from final_showcase.holdout import build_holdout_dataset, holdout_profiles
from product.federation.artifact_store import FederationArtifactStore
from product.models.candidate_artifacts import CandidateArtifactStore
from tests.capstone_federation_support import SINGLE_RUN, RunIds, make_fed_app, poll_run
from tests.capstone_product_support import BASE, USER_A

FROZEN = "reports/model_v2/v2_fl_005/federation_run.json"


def canonical_run() -> tuple[Path, str, str, str]:
    root = Path(tempfile.mkdtemp(prefix="synth-eval-run-"))
    app, _ = make_fed_app(root, run_ids=RunIds("FEDRUN-EVAL"))
    with TestClient(app) as client:
        run_id = client.post(f"{BASE}/federation/runs", json=SINGLE_RUN, headers=USER_A).json()["run_id"]
        client.post(f"{BASE}/federation/runs/{run_id}/start", headers=USER_A)
        run = poll_run(client, run_id, USER_A)
        assert run["status"] == "COMPLETED", run
        cand = client.get(f"{BASE}/models", headers=USER_A).json()["capstone_fl_candidates"][0]
    return root, run_id, cand["candidate_id"], cand["state_digest"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--method-commit", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--run-root")
    ap.add_argument("--run-id")
    ap.add_argument("--candidate-id")
    ap.add_argument("--candidate-digest")
    a = ap.parse_args()
    freeze = ev.verify_method_freeze(a.method_commit)
    protocol = json.loads(ev.PROTOCOL.read_text())
    root, run_id, cid, cdig = (Path(a.run_root), a.run_id, a.candidate_id, a.candidate_digest) if a.run_root else canonical_run()
    store = FederationArtifactStore(root / "federation")
    ev_states = protocol["evaluated_states"]
    states: dict[str, Any] = {"round_0": fresh_initial_state_v2(BASE_SEED)}
    for r in (1, 2):
        states[f"round_{r}"] = store.read_checkpoint(run_id, r)[1]
    states["round_3_candidate"] = CandidateArtifactStore(root / "candidates").load_verified(cid, cdig)
    digests = {k: ev.digest_check(k, states[k], ev_states[k]["digest"]) for k in ev.STATE_KEYS}
    _, training, _ = build_cohort()
    holdout = [build_holdout_dataset(p) for p in holdout_profiles()]
    sep = ev.check_manifest(protocol, holdout, training)
    ev.require_both_classes(holdout)
    boot = protocol["uncertainty"]
    results, preds = {}, {}
    for key in ev.STATE_KEYS:
        res = ev.evaluate_state(states[key], holdout, bootstrap=boot)
        res["training_buffer_secondary"] = {k: v for k, v in ev.evaluate_state(states[key], training).items() if k in ("pooled", "per_participant", "participant_macro_F1")}
        preds[key] = res.pop("_logits")
        results[key] = res
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    labels = np.concatenate([d.labels for d in holdout]).astype(int)
    rows = [(d.client_id, d.participant_id, int(i), int(d.right_edges_us[i]), int(d.labels[i])) for d in holdout for i in range(len(d.labels))]
    with (out / "holdout_predictions.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["holdout_id", "participant_id", "window_index", "right_edge_us", "label", *[f"logit_{k}" for k in ev.STATE_KEYS]])
        for n, row in enumerate(rows):
            w.writerow([*row, *[f"{preds[k][n]:.9g}" for k in ev.STATE_KEYS]])
    report = {"boundary_label": ev.label_banner(), "status": "COMPLETED", "protocol_sha256": ev.sha256_file(ev.PROTOCOL), "manifest_sha256": ev.sha256_file(ev.MANIFEST), "method_freeze_commit": a.method_commit,
              "method_freeze_verified": freeze, "run_id": run_id, "candidate_id": cid, "candidate_digest": cdig, "state_digests": digests, "separation": sep,
              "holdout_windows": len(labels), "results": results, "predictions_file": "holdout_predictions.csv",
              "note": "No retraining, no threshold tuning, no CAL_V2. Training-buffer metrics are secondary and are NOT generalisation."}
    (out / "synth_fl_eval_results.json").write_text(json.dumps(report, indent=1, sort_keys=True, default=float) + "\n")
    for key in ev.STATE_KEYS:
        p = results[key]["pooled"]
        print(key, {m: (round(p[m], 4) if p[m] is not None else None) for m in ("AUPRC", "AUROC", "F1", "accuracy", "precision", "recall", "specificity", "balanced_accuracy", "BCE")}, p["TP"], p["FP"], p["TN"], p["FN"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
