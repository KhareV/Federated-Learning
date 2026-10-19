# ruff: noqa: E501
"""Adds the 50-round federated V2 checkpoints (experiment V2-FL-001) to the Studio candidate library of one owner, so they can be chosen as the starting model of later runs.

    PYTHONPATH=src:. python -m scripts.register_research_candidates --owner <clerk user id> [--library DIR]

Two candidates: round 50 (the final state of the 50-round run) and round 38 (the best-validation checkpoint, which is the one the frozen FL evaluation family scored). Both were federated from a random start
on eight simulated whole-patient sites of REAL MIT-BIH training patients: there is no synthetic cohort behind them (cohort REAL_ECG). Their library scores are measured here on the real MIT-BIH VALIDATION
windows (the partition the round-38 choice was made on, so round 38 is optimistic there). Idempotent. A candidate is an engineering artefact: not promoted, not deployed, never used for monitoring."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.fl50_cohort_runs import FL50_BEST_CHECKPOINT, FL50_BEST_SHA256, FL50_CHECKPOINT, FL50_SHA256, load_checkpoint_state

ROOT = Path(__file__).resolve().parents[1]
RESULT = "reports/model_v2/v2_fl_001/fl_iid_model_v2_result.json"
EVALUATION_COHORT_ID = "MITBIH_OFFICIAL_VALIDATION (7 patient groups, 2,880 real windows; V2-FL-001 model selection used it)"

ENTRIES = (
    {"candidate_id": "RESEARCH_FL_V2_FL001_R50", "round": 50, "path": FL50_CHECKPOINT, "sha": FL50_SHA256, "role": "final state of the 50-round run"},
    {"candidate_id": "RESEARCH_FL_V2_FL001_R38_BEST", "round": 38, "path": FL50_BEST_CHECKPOINT, "sha": FL50_BEST_SHA256, "role": "best-validation checkpoint (round 38); the one the frozen FL evaluation family scored"},
)


def metrics_on_real_validation(state: Any) -> dict[str, Any]:
    from scripts.realistic_multiseed import cell_metrics, real_validation_windows
    from studio.isolated_eval import isolated_logits

    real = real_validation_windows()
    if real is None:
        raise RuntimeError("REAL_VALIDATION_WINDOWS_UNAVAILABLE")
    x, y, _ = real
    m = cell_metrics(isolated_logits(state, x), y)
    return {"AUPRC": m["AUPRC"], "AUROC": m["AUROC"], "F1": m["F1"], "windows": int(len(y))}


def register_all(owner: str, library_root: Path, root: Path = ROOT) -> list[dict[str, Any]]:
    from studio.candidates import REAL_ECG, RESEARCH_KIND, CandidateLibrary

    record = json.loads((root / RESULT).read_text())
    library = CandidateLibrary(library_root)
    out = []
    for e in ENTRIES:
        state = load_checkpoint_state(e["path"], e["sha"], root)
        out.append(library.register(
            owner=owner, candidate_id=e["candidate_id"], source_run_id="V2-FL-001", source_kind=RESEARCH_KIND, cohort=REAL_ECG, evaluation_cohort_id=EVALUATION_COHORT_ID, run_length=50, round_id=e["round"],
            algorithm="FEDAVG", secagg_mode="PLAIN", metrics=metrics_on_real_validation(state), state=state,
            base_model={"model_id": record["initialization_id"], "kind": "RANDOM_INITIALISATION", "label": "FL_INIT_V2 (V2 architecture, random weights; the central checkpoint was NOT used)"},
            source_detail={"experiment_id": record["experiment_id"], "role": e["role"], "checkpoint": e["path"], "checkpoint_sha256": e["sha"], "client_manifest_id": record["client_manifest_id"],
                           "client_manifest_sha256": record["client_manifest_sha256"], "config_sha256": record["config_sha256"], "development_validation_AUPRC": record["best_validation"]["AUPRC"] if e["round"] == 38 else record["round_50_validation_AUPRC"],
                           "note": "Federated on real MIT-BIH training patients in eight simulated sites. Scores here are on the official MIT-BIH VALIDATION partition, which V2-FL-001 used to pick its best round, so round 38 is optimistic. No calibration, no promotion."}))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--owner", required=True, help="the Clerk user id that owns the library entries (the account that will use them)")
    parser.add_argument("--library", default=None, help="library directory (default: the Studio's stable library, data/studio_candidates)")
    args = parser.parse_args(argv)
    from studio.candidates import default_root

    entries = register_all(args.owner, Path(args.library) if args.library else default_root())
    for e in entries:
        m = e["metrics"] or {}
        print(f"{e['candidate_id']}: round {e['round_id']}  AUPRC {m.get('AUPRC', float('nan')):.3f}  AUROC {m.get('AUROC', float('nan')):.3f}  F1 {m.get('F1', float('nan')):.3f}  state {e['state_sha256'][:16]}…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
