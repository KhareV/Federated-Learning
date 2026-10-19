# ruff: noqa: E501
"""Starts a 10-round federated run on each synthetic cohort (original and realistic) from two models and scores every committed state on that cohort's evaluation holdout:
the centrally trained MODEL_V2_FINAL (the Studio's pretrained start) and the 50-round federated checkpoint of V2-FL-001 (round 50). Same engine, FedAvg, plain aggregation and fixed 0.5 rule as a Studio run.

    PYTHONPATH=src:. python -m scripts.fl50_cohort_runs [--rounds 10] [--out reports/realistic/fl50_cohort_runs.json]

One run per cell, no repetition: a diagnostic of two starting points, not a significance test. The holdouts are the observer's own (frozen original holdout; realistic holdout pinned by manifest)."""

from __future__ import annotations

import argparse
import json
import tempfile
from collections import OrderedDict
from pathlib import Path
from typing import Any

import numpy as np

from scripts.realistic_multiseed import cell_metrics, federated_states  # noqa: F401  (federated_states is re-implemented below to accept a start state)

ROOT = Path(__file__).resolve().parents[1]
FL50_CHECKPOINT = "checkpoints/model_v2/v2_fl_001/FL_IID_MODEL_V2_V1_round50.pt"
FL50_SHA256 = "5a8dd347622680c8243eeb0fd1a06b52b558bcdab2f9519f03256ce08f5ff7b2"
FL50_BEST_CHECKPOINT = "checkpoints/model_v2/v2_fl_001/FL_IID_MODEL_V2_V1_best.pt"          # round 38: the best-validation checkpoint (the one the frozen FL evaluation family scored)
FL50_BEST_SHA256 = "e90749ee700a2b7e55bd2aa6d36e9db32cd55e56ecd1cbc74959925c665d3ca5"


def load_checkpoint_state(relative: str, sha256: str, root: Path = ROOT) -> OrderedDict[str, np.ndarray]:
    """A federated checkpoint's state in the FL model layout, after a digest check and the library's strict layout check."""
    import hashlib

    import torch

    from studio import candidates

    path = root / relative
    if hashlib.sha256(path.read_bytes()).hexdigest() != sha256:
        raise RuntimeError(f"CHECKPOINT_DIGEST_MISMATCH:{relative}")
    payload = torch.load(path, map_location="cpu", weights_only=False)
    state = OrderedDict((k, np.array(v.detach().cpu().numpy(), copy=True, order="C")) for k, v in payload["state_dict"].items())
    candidates.verify_layout(state)
    return state


def load_fl50_state(root: Path = ROOT) -> OrderedDict[str, np.ndarray]:
    """The round-50 federated state."""
    return load_checkpoint_state(FL50_CHECKPOINT, FL50_SHA256, root)


def run_from(start: dict[str, Any], audit: dict[str, Any], cohort: str, rounds: int) -> dict[str, Any]:
    from fl10 import runner
    from fl10.runner import load_state
    from studio import cohorts
    from studio.isolated_eval import isolated_logits

    datasets, manifest = cohorts.training(cohort)
    holdout = cohorts.holdout_provider(cohort)()
    x = holdout.inputs.reshape(len(holdout.inputs), 1, -1)
    y = np.asarray(holdout.labels).astype(int)
    with tempfile.TemporaryDirectory(prefix="fl50_runs_") as tmp:
        report = runner.run_training(mode="H", run_id="FL50-COHORT-RUNS", out_dir=Path(tmp), datasets=datasets, manifest=manifest, rounds=rounds, require_prefix_parity=False, capture_batches=False,
                                     progress=None, git_commit="UNKNOWN", protocol_sha256="UNKNOWN", algorithm="FEDAVG", secagg_mode="PLAIN", initial_state=start, initialisation=audit)
        states = {0: start} | {row["round"]: load_state(Path(tmp), row["round"], row["global_state_sha256"]) for row in report["rounds"]}
        scored = {r: cell_metrics(isolated_logits(s, x), y) for r, s in sorted(states.items())}
    return {"cohort": cohort, "evaluation_cohort_id": holdout.cohort_id, "holdout_windows": int(y.size), "prevalence": float(y.mean()), "rounds": scored}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rounds", type=int, default=10)
    parser.add_argument("--out", default="reports/realistic/fl50_cohort_runs.json")
    parser.add_argument("--cohorts", default="ORIGINAL,REALISTIC", help="comma-separated cohorts to run; results are merged into an existing output file")
    args = parser.parse_args(argv)
    from studio import v2_init

    central, central_audit = v2_init.load_v2_final()
    fl50 = load_fl50_state()
    fl50_audit = {"model_id": "V2-FL-001 round 50", "kind": "RESEARCH_FEDERATED_CHECKPOINT", "family": "V2", "architecture_id": "V2_FL_MODEL_LAYOUT", "checkpoint_sha256": FL50_SHA256}
    starts = {"MODEL_V2_FINAL (central)": (central, central_audit), "V2-FL-001 round 50 (federated, 50 rounds)": (fl50, fl50_audit)}
    path = ROOT / args.out
    out: dict[str, Any] = json.loads(path.read_text()) if path.exists() else {"design": {"rounds": args.rounds, "algorithm": "FEDAVG", "aggregation": "PLAIN", "threshold": 0.5, "calibration": "NONE", "runs_per_cell": 1}, "runs": {}}
    for cohort in args.cohorts.split(","):
        for name, (state, audit) in starts.items():
            print(f"{cohort}: {args.rounds} rounds from {name} ...", flush=True)
            out["runs"][f"{cohort} | {name}"] = {"start": name} | run_from(state, audit, cohort, args.rounds)
            rounds = out["runs"][f"{cohort} | {name}"]["rounds"]
            for r in (0, args.rounds):
                m = rounds[r]
                print(f"  round {r:2d}: AUROC {m['AUROC']:.3f}  AUPRC {m['AUPRC']:.3f}  F1@0.5 {m['F1']:.3f}", flush=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1, sort_keys=True, default=float) + "\n")
    print("wrote", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
