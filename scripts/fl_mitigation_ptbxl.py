# ruff: noqa: E501
"""Can adapting the central V2 to a synthetic cohort be made to forget less of real ECG? Diagnostic experiment (not a method selection for any run).

The PTBXL_EXTERNAL_CHECK_V1 result: 10 FedAvg rounds on a synthetic cohort lower the central V2's performance on unseen real ECG. Here the same start (central MODEL_V2_FINAL) is adapted to each synthetic cohort in three other ways and scored the same way
(PTB-XL, label rule A, folds 9-10 and 1-8, fixed 0.5, patient-cluster bootstrap) and on the cohort's own holdout:

  * FedAvg, 3 rounds (less drift);  * FedProx with the engine's frozen mu = 0.1, 10 rounds;  * FedProx with a stronger mu = 1.0, 10 rounds (the value is patched inside THIS script only; the engine's frozen mu is not changed).

    PYTHONPATH=src:. python -m scripts.fl_mitigation_ptbxl [--out reports/ptbxl/mitigation.json]

One run per cell. States are cached next to the PTB-XL window cache, so a rerun does not retrain."""

from __future__ import annotations

import argparse
import json
import tempfile
from collections import OrderedDict
from pathlib import Path
from typing import Any

import numpy as np

from scripts import ptbxl_external_check as pc

ROOT = Path(__file__).resolve().parents[1]
VARIANTS = (("FedAvg, 3 rounds", "FEDAVG", 3, None), ("FedProx mu=0.1 (frozen), 10 rounds", "FEDPROX", 10, 0.1), ("FedProx mu=1.0, 10 rounds", "FEDPROX", 10, 1.0))
COHORTS = ("ORIGINAL", "REALISTIC", "REALISTIC_NSTDB")
DEFAULT_COHORTS = ("ORIGINAL", "REALISTIC")
BASE = "MODEL_V2_FINAL (central)"


def variant_state(cohort: str, algorithm: str, rounds: int, mu: float | None) -> OrderedDict[str, np.ndarray]:
    from federated.model_adapter import deserialize_state, serialize_state
    from fl10 import runner
    from fl10.runner import load_state
    from studio import cohorts, v2_init

    tag = f"{cohort.lower()}_{algorithm.lower()}_r{rounds}" + (f"_mu{mu}" if mu is not None else "")
    path = pc.CACHE / f"mitigation_{tag}.bin"
    if path.exists():
        return OrderedDict(deserialize_state(path.read_bytes()))
    start, audit = v2_init.load_v2_final()
    datasets, manifest = cohorts.training(cohort)
    original_mu = runner.frozen_fedprox_mu
    if mu is not None and mu != original_mu():
        runner.frozen_fedprox_mu = lambda: mu                       # diagnostic only: restored below
    try:
        with tempfile.TemporaryDirectory(prefix="mitigation_") as tmp:
            report = runner.run_training(mode="H", run_id=f"MITIGATION-{tag}", out_dir=Path(tmp), datasets=datasets, manifest=manifest, rounds=rounds, require_prefix_parity=False, capture_batches=False,
                                         progress=None, git_commit="UNKNOWN", protocol_sha256="UNKNOWN", algorithm=algorithm, secagg_mode="PLAIN", initial_state=start, initialisation=audit)
            last = report["rounds"][-1]
            state = OrderedDict(load_state(Path(tmp), last["round"], last["global_state_sha256"]))
    finally:
        runner.frozen_fedprox_mu = original_mu
    pc.CACHE.mkdir(parents=True, exist_ok=True)
    path.write_bytes(serialize_state(state))
    return state


def own_holdout(cohort: str, states: dict[str, Any]) -> dict[str, Any]:
    from studio import cohorts
    from studio.isolated_eval import isolated_logits

    h = cohorts.holdout_provider(cohort)()
    x, y = h.inputs.reshape(len(h.inputs), 1, -1), np.asarray(h.labels).astype(int)
    return {name: pc.point_metrics(isolated_logits(s, x), y) for name, s in states.items()}


def run(out: Path, cohorts: tuple[str, ...] = DEFAULT_COHORTS) -> dict[str, Any]:
    from studio import v2_init
    from studio.isolated_eval import isolated_logits

    labels = pc.label_table()
    ids, x, _ = pc.build_windows(labels)
    lab = labels.loc[ids]
    central, _ = v2_init.load_v2_final()
    path = ROOT / out
    result: dict[str, Any] = json.loads(path.read_text()) if path.exists() else {"design": {"start": BASE, "variants": [v[0] for v in VARIANTS], "ptbxl_rule": "A", "threshold": 0.5, "runs_per_cell": 1,
                                                                                  "mu_note": "mu = 1.0 is patched inside this script only; the engine's frozen mu stays 0.1"}, "cohorts": {}}
    for cohort in cohorts:
        states: dict[str, Any] = {BASE: central, f"FedAvg, 10 rounds (the earlier result)": pc.adapted_state(cohort)}
        for name, algorithm, rounds, mu in VARIANTS:
            print(f"{cohort}: {name} ...", flush=True)
            states[name] = variant_state(cohort, algorithm, rounds, mu)
        logits = {name: isolated_logits(s, x[:, None, :]) for name, s in states.items()}
        block: dict[str, Any] = {"own_holdout": own_holdout(cohort, states), "ptbxl": {}}
        for set_name, folds in (("primary (folds 9-10)", pc.PRIMARY_FOLDS), ("replication (folds 1-8)", pc.REPLICATION_FOLDS)):
            keep = lab.fold.isin(folds).to_numpy()
            y = lab.label_A.to_numpy()[keep].astype(int)
            block["ptbxl"][set_name] = {"points": {m: pc.point_metrics(z[keep], y) for m, z in logits.items()}, "bootstrap": pc.cluster_bootstrap({m: z[keep] for m, z in logits.items()}, y, lab.patient_id.to_numpy()[keep], base=BASE)}
        result["cohorts"][cohort] = block
        p = block["ptbxl"]["primary (folds 9-10)"]["points"]
        for m in states:
            o = block["own_holdout"][m]
            print(f"  {m:40s} PTB-XL AUROC {p[m]['AUROC']:.3f} AUPRC {p[m]['AUPRC']:.3f} spec {p[m]['specificity']:.2f} | own holdout AUROC {o['AUROC']:.3f} AUPRC {o['AUPRC']:.3f} F1 {o['F1']:.3f}", flush=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=1, sort_keys=True, default=float) + "\n")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="reports/ptbxl/mitigation.json")
    parser.add_argument("--cohorts", default=",".join(DEFAULT_COHORTS), help="comma-separated cohorts; results are merged into an existing output file")
    args = parser.parse_args(argv)
    run(Path(args.out), tuple(args.cohorts.split(",")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
