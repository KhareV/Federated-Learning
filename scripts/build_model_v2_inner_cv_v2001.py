#!/usr/bin/env python3
"""Build and freeze MITDB_TRAIN_INNER_V2_V1 (V2-001, Section 11).

For each of the 5 outer folds of MITDB_TRAIN_CV_V2_V1, deterministically and exhaustively
selects exactly 4 of the remaining outer-training patient groups as the inner-validation set,
leaving the rest as the optimisation subset. Derived ONLY from already-frozen TRAIN metadata
(manifests/windows/MITDB_WINDOWS_V1.csv) -- no ECG waveform is read.
"""

from __future__ import annotations

import csv
import itertools
import json
from pathlib import Path
from typing import Any

from nhm.hashing import hash_file
from scripts.build_model_v2_train_cv_v2001 import load_train_patient_aggregates

ROOT = Path(__file__).resolve().parents[1]
OUTER_CSV = ROOT / "manifests/model_v2/cv/MITDB_TRAIN_CV_V2_V1.csv"
OUT_DIR = ROOT / "manifests/model_v2/cv"
INNER_SIZE = 4


def load_outer_assignment() -> dict[str, int]:
    assignment: dict[str, int] = {}
    with OUTER_CSV.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            assignment[row["participant_group_id"]] = int(row["outer_fold"])
    return assignment


def select_inner_validation(
    outer_train_patients: list[str], aggregates: dict[str, dict[str, int]]
) -> tuple[tuple[str, ...], float]:
    n = len(outer_train_patients)
    totals = {
        "windows": sum(aggregates[pg]["eligible"] for pg in outer_train_patients),
        "positive": sum(aggregates[pg]["positive"] for pg in outer_train_patients),
        "negative": sum(aggregates[pg]["negative"] for pg in outer_train_patients),
    }
    targets = {
        "windows": totals["windows"] * INNER_SIZE / n,
        "positive": totals["positive"] * INNER_SIZE / n,
        "negative": totals["negative"] * INNER_SIZE / n,
    }

    best_combo: tuple[str, ...] | None = None
    best_objective: float | None = None
    for combo in itertools.combinations(sorted(outer_train_patients), INNER_SIZE):
        inner_windows = sum(aggregates[pg]["eligible"] for pg in combo)
        inner_positive = sum(aggregates[pg]["positive"] for pg in combo)
        inner_negative = sum(aggregates[pg]["negative"] for pg in combo)
        if inner_positive == 0 or inner_negative == 0:
            continue
        remaining = set(outer_train_patients) - set(combo)
        remaining_positive = totals["positive"] - inner_positive
        remaining_negative = totals["negative"] - inner_negative
        if remaining_positive == 0 or remaining_negative == 0:
            continue
        del remaining

        objective = (
            ((inner_windows - targets["windows"]) / targets["windows"]) ** 2
            + ((inner_positive - targets["positive"]) / targets["positive"]) ** 2
            + ((inner_negative - targets["negative"]) / targets["negative"]) ** 2
        )
        if best_objective is None or objective < best_objective - 1e-15:
            best_objective = objective
            best_combo = combo

    assert best_combo is not None and best_objective is not None
    return best_combo, best_objective


def build() -> dict[str, Any]:
    outer_assignment = load_outer_assignment()
    aggregates = load_train_patient_aggregates()
    assert set(outer_assignment) == set(aggregates)

    outer_folds = sorted(set(outer_assignment.values()))
    rows: list[dict[str, Any]] = []
    fold_audit: list[dict[str, Any]] = []

    for fold in outer_folds:
        outer_test = sorted(pg for pg, f in outer_assignment.items() if f == fold)
        outer_train = sorted(pg for pg, f in outer_assignment.items() if f != fold)

        inner_validation, objective = select_inner_validation(outer_train, aggregates)
        optimise = sorted(set(outer_train) - set(inner_validation))

        for pg in outer_test:
            rows.append({"outer_fold": fold, "participant_group_id": pg, "role": "OUTER_TEST"})
        for pg in sorted(inner_validation):
            rows.append(
                {"outer_fold": fold, "participant_group_id": pg, "role": "INNER_VALIDATION"}
            )
        for pg in optimise:
            rows.append({"outer_fold": fold, "participant_group_id": pg, "role": "OPTIMISE"})

        fold_audit.append(
            {
                "outer_fold": fold,
                "outer_train_group_count": len(outer_train),
                "inner_validation_groups": sorted(inner_validation),
                "optimise_group_count": len(optimise),
                "objective": objective,
                "inner_eligible_windows": sum(
                    aggregates[pg]["eligible"] for pg in inner_validation
                ),
                "inner_positive_windows": sum(
                    aggregates[pg]["positive"] for pg in inner_validation
                ),
                "inner_negative_windows": sum(
                    aggregates[pg]["negative"] for pg in inner_validation
                ),
            }
        )

    return {"rows": rows, "fold_audit": fold_audit}


def main() -> None:
    result = build()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    manifest_path = OUT_DIR / "MITDB_TRAIN_INNER_V2_V1.csv"
    with manifest_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["outer_fold", "participant_group_id", "role"]
        )
        writer.writeheader()
        writer.writerows(result["rows"])

    lock = {
        "manifest_id": "MITDB_TRAIN_INNER_V2_V1",
        "status": "FROZEN_CV_MANIFEST",
        "owner_task": "V2-001",
        "predecessor_outer_manifest": "MITDB_TRAIN_CV_V2_V1",
        "predecessor_outer_manifest_sha256": hash_file(OUTER_CSV),
        "inner_validation_size": INNER_SIZE,
        "algorithm": "EXACT_EXHAUSTIVE_MIN_SQUARED_DEVIATION_4_GROUP_COMBINATION_V1",
        "fold_audit": result["fold_audit"],
        "manifest_path": "manifests/model_v2/cv/MITDB_TRAIN_INNER_V2_V1.csv",
        "manifest_sha256": hash_file(manifest_path),
        "change_control": (
            "This manifest is never regenerated based on future V2 results. Any change "
            "requires a new, additive MITDB_TRAIN_INNER_V2_V2 successor."
        ),
    }
    lock_path = OUT_DIR / "MITDB_TRAIN_INNER_V2_V1.lock.json"
    lock_path.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps(result["fold_audit"], indent=2))


if __name__ == "__main__":
    main()
