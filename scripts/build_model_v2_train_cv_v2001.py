#!/usr/bin/env python3
"""Build and freeze MITDB_TRAIN_CV_V2_V1 (V2-001, Section 10).

Deterministic 5-outer-fold (6/6/5/5/5) patient-disjoint split of the 27 frozen TRAIN patient
groups, derived ONLY from already-frozen TRAIN metadata (manifests/windows/MITDB_WINDOWS_V1.csv
eligible/label columns) -- no ECG waveform is read to build these folds.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
WINDOW_MANIFEST = ROOT / "manifests/windows/MITDB_WINDOWS_V1.csv"
OUT_DIR = ROOT / "manifests/model_v2/cv"
REPORT_DIR = ROOT / "reports/model_v2/v2_001"

FOLD_CAPACITIES = [6, 6, 5, 5, 5]


def load_train_patient_aggregates() -> dict[str, dict[str, int]]:
    aggregates: dict[str, dict[str, int]] = {}
    with WINDOW_MANIFEST.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["partition"] != "TRAIN" or row["core_eligible"] != "TRUE":
                continue
            pg = row["participant_group_id"]
            entry = aggregates.setdefault(pg, {"eligible": 0, "positive": 0, "negative": 0})
            entry["eligible"] += 1
            if int(row["label"]) == 1:
                entry["positive"] += 1
            else:
                entry["negative"] += 1
    return aggregates


def _objective(
    fold_state: list[dict[str, int]],
    targets: dict[str, float],
    fold_capacities: list[int],
) -> float:
    total = 0.0
    for j, state in enumerate(fold_state):
        total += ((state["groups"] - fold_capacities[j]) / fold_capacities[j]) ** 2
        total += ((state["eligible"] - targets["windows"]) / targets["windows"]) ** 2
        total += ((state["positive"] - targets["positive"]) / targets["positive"]) ** 2
        total += ((state["negative"] - targets["negative"]) / targets["negative"]) ** 2
    return total


def greedy_assign(
    aggregates: dict[str, dict[str, int]],
) -> tuple[dict[str, int], float]:
    n_folds = len(FOLD_CAPACITIES)
    totals = {
        "windows": sum(a["eligible"] for a in aggregates.values()),
        "positive": sum(a["positive"] for a in aggregates.values()),
        "negative": sum(a["negative"] for a in aggregates.values()),
    }
    targets = {
        "windows": totals["windows"] / n_folds,
        "positive": totals["positive"] / n_folds,
        "negative": totals["negative"] / n_folds,
    }

    def sort_key(pg: str) -> tuple[float, int, str]:
        a = aggregates[pg]
        ratio = max(
            a["eligible"] / targets["windows"],
            a["positive"] / targets["positive"],
            a["negative"] / targets["negative"],
        )
        return (-ratio, -a["eligible"], pg)

    order = sorted(aggregates, key=sort_key)

    fold_state = [
        {"groups": 0, "eligible": 0, "positive": 0, "negative": 0} for _ in range(n_folds)
    ]
    assignment: dict[str, int] = {}

    for pg in order:
        a = aggregates[pg]
        best_fold: int | None = None
        best_objective: float | None = None
        for j in range(n_folds):
            if fold_state[j]["groups"] >= FOLD_CAPACITIES[j]:
                continue
            trial = [dict(state) for state in fold_state]
            trial[j]["groups"] += 1
            trial[j]["eligible"] += a["eligible"]
            trial[j]["positive"] += a["positive"]
            trial[j]["negative"] += a["negative"]
            candidate_objective = _objective(trial, targets, FOLD_CAPACITIES)
            if best_objective is None or candidate_objective < best_objective - 1e-15:
                best_objective = candidate_objective
                best_fold = j
        assert best_fold is not None, f"no fold capacity available for {pg}"
        assignment[pg] = best_fold
        fold_state[best_fold]["groups"] += 1
        fold_state[best_fold]["eligible"] += a["eligible"]
        fold_state[best_fold]["positive"] += a["positive"]
        fold_state[best_fold]["negative"] += a["negative"]

    final_objective = _objective(fold_state, targets, FOLD_CAPACITIES)
    return assignment, final_objective


def swap_refine(
    aggregates: dict[str, dict[str, int]], assignment: dict[str, int]
) -> tuple[dict[str, int], float]:
    n_folds = len(FOLD_CAPACITIES)
    totals = {
        "windows": sum(a["eligible"] for a in aggregates.values()),
        "positive": sum(a["positive"] for a in aggregates.values()),
        "negative": sum(a["negative"] for a in aggregates.values()),
    }
    targets = {
        "windows": totals["windows"] / n_folds,
        "positive": totals["positive"] / n_folds,
        "negative": totals["negative"] / n_folds,
    }

    def fold_state_from(assignment: dict[str, int]) -> list[dict[str, int]]:
        state = [{"groups": 0, "eligible": 0, "positive": 0, "negative": 0} for _ in range(n_folds)]
        for pg, j in assignment.items():
            state[j]["groups"] += 1
            state[j]["eligible"] += aggregates[pg]["eligible"]
            state[j]["positive"] += aggregates[pg]["positive"]
            state[j]["negative"] += aggregates[pg]["negative"]
        return state

    current_objective = _objective(fold_state_from(assignment), targets, FOLD_CAPACITIES)

    improved = True
    while improved:
        improved = False
        best_pair: tuple[str, str] | None = None
        best_new_objective = current_objective
        patients = sorted(assignment)
        for i, p1 in enumerate(patients):
            for p2 in patients[i + 1 :]:
                if assignment[p1] == assignment[p2]:
                    continue
                trial = dict(assignment)
                trial[p1], trial[p2] = trial[p2], trial[p1]
                trial_objective = _objective(fold_state_from(trial), targets, FOLD_CAPACITIES)
                if trial_objective < best_new_objective - 1e-12:
                    best_new_objective = trial_objective
                    best_pair = (p1, p2)
        if best_pair is not None:
            p1, p2 = best_pair
            assignment[p1], assignment[p2] = assignment[p2], assignment[p1]
            current_objective = best_new_objective
            improved = True

    return assignment, current_objective


def build() -> dict[str, Any]:
    aggregates = load_train_patient_aggregates()
    assert len(aggregates) == 27, f"expected 27 TRAIN patient groups, got {len(aggregates)}"

    assignment, initial_objective = greedy_assign(aggregates)
    assignment, final_objective = swap_refine(aggregates, dict(assignment))

    fold_rows = []
    for pg in sorted(assignment):
        fold_rows.append(
            {
                "participant_group_id": pg,
                "outer_fold": assignment[pg],
                "eligible_windows": aggregates[pg]["eligible"],
                "positive_windows": aggregates[pg]["positive"],
                "negative_windows": aggregates[pg]["negative"],
            }
        )

    fold_summary = []
    for j in range(len(FOLD_CAPACITIES)):
        members = [r for r in fold_rows if r["outer_fold"] == j]
        fold_summary.append(
            {
                "fold": j,
                "capacity": FOLD_CAPACITIES[j],
                "patient_groups": len(members),
                "eligible_windows": sum(m["eligible_windows"] for m in members),
                "positive_windows": sum(m["positive_windows"] for m in members),
                "negative_windows": sum(m["negative_windows"] for m in members),
                "members": sorted(m["participant_group_id"] for m in members),
            }
        )

    return {
        "fold_rows": fold_rows,
        "fold_summary": fold_summary,
        "initial_objective": initial_objective,
        "final_objective": final_objective,
        "aggregates": aggregates,
    }


def main() -> None:
    result = build()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    manifest_path = OUT_DIR / "MITDB_TRAIN_CV_V2_V1.csv"
    with manifest_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "participant_group_id",
                "outer_fold",
                "eligible_windows",
                "positive_windows",
                "negative_windows",
            ],
        )
        writer.writeheader()
        writer.writerows(result["fold_rows"])

    total_eligible = sum(r["eligible_windows"] for r in result["fold_rows"])
    total_positive = sum(r["positive_windows"] for r in result["fold_rows"])
    total_negative = sum(r["negative_windows"] for r in result["fold_rows"])

    lock = {
        "manifest_id": "MITDB_TRAIN_CV_V2_V1",
        "status": "FROZEN_CV_MANIFEST",
        "owner_task": "V2-001",
        "source_manifest": "manifests/windows/MITDB_WINDOWS_V1.csv",
        "source_manifest_sha256": hash_file(WINDOW_MANIFEST),
        "partition": "TRAIN",
        "fold_capacities": FOLD_CAPACITIES,
        "algorithm": "EXACT_GREEDY_MIN_SQUARED_DEVIATION_WITH_PAIR_SWAP_REFINEMENT_V1",
        "initial_objective": result["initial_objective"],
        "final_objective": result["final_objective"],
        "fold_summary": result["fold_summary"],
        "total_patient_groups": len(result["fold_rows"]),
        "total_eligible_windows": total_eligible,
        "total_positive_windows": total_positive,
        "total_negative_windows": total_negative,
        "manifest_path": "manifests/model_v2/cv/MITDB_TRAIN_CV_V2_V1.csv",
        "manifest_sha256": hash_file(manifest_path),
        "change_control": (
            "This manifest is never regenerated based on future V2 results. Any change "
            "requires a new, additive MITDB_TRAIN_CV_V2_V2 successor."
        ),
    }
    lock_path = OUT_DIR / "MITDB_TRAIN_CV_V2_V1.lock.json"
    lock_path.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "fold_summary": result["fold_summary"],
                "initial_objective": result["initial_objective"],
                "final_objective": result["final_objective"],
                "total_eligible": total_eligible,
                "total_positive": total_positive,
                "total_negative": total_negative,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
