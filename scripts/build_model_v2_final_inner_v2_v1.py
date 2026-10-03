#!/usr/bin/env python3
"""Build and freeze MITDB_TRAIN_FINAL_INNER_V2_V1 (C-V2-PRE006-AUTHORITY-REPAIR).

Deterministically and exhaustively selects exactly 5 of the 27 frozen MITDB TRAIN patient
groups as the FINAL_INNER_VALIDATION set for the later V2-007 official-validation finalist
runs, leaving the remaining approximately 22 groups as OPTIMISE. This is a SEPARATE, additive
role assignment from the five outer-CV-fold-specific inner splits in MITDB_TRAIN_INNER_V2_V1
(which remains untouched).

Derived ONLY from already-frozen TRAIN metadata (manifests/windows/MITDB_WINDOWS_V1.csv) --
no ECG waveform is read, no V2-004 result or any model/validation score is inspected. The
selection method (this algorithm) is frozen and committed BEFORE the selected group set is
ever generated or inspected.
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
FINAL_INNER_SIZE = 5
ALGORITHM = "EXACT_EXHAUSTIVE_MIN_SQUARED_DEVIATION_5_GROUP_COMBINATION_V1"
TIE_BREAK = "LEXICOGRAPHIC_FIRST_IN_SORTED_ENUMERATION_ORDER"


def load_full_train_population() -> list[str]:
    with OUTER_CSV.open(newline="", encoding="utf-8") as handle:
        return sorted(row["participant_group_id"] for row in csv.DictReader(handle))


def select_final_inner_validation(
    train_groups: list[str], aggregates: dict[str, dict[str, int]]
) -> tuple[tuple[str, ...], float]:
    n = len(train_groups)
    totals = {
        "windows": sum(aggregates[pg]["eligible"] for pg in train_groups),
        "positive": sum(aggregates[pg]["positive"] for pg in train_groups),
        "negative": sum(aggregates[pg]["negative"] for pg in train_groups),
    }
    targets = {
        "windows": totals["windows"] * FINAL_INNER_SIZE / n,
        "positive": totals["positive"] * FINAL_INNER_SIZE / n,
        "negative": totals["negative"] * FINAL_INNER_SIZE / n,
    }

    best_combo: tuple[str, ...] | None = None
    best_objective: float | None = None
    for combo in itertools.combinations(sorted(train_groups), FINAL_INNER_SIZE):
        inner_windows = sum(aggregates[pg]["eligible"] for pg in combo)
        inner_positive = sum(aggregates[pg]["positive"] for pg in combo)
        inner_negative = sum(aggregates[pg]["negative"] for pg in combo)
        if inner_positive == 0 or inner_negative == 0:
            continue
        remaining_positive = totals["positive"] - inner_positive
        remaining_negative = totals["negative"] - inner_negative
        if remaining_positive == 0 or remaining_negative == 0:
            continue

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
    train_groups = load_full_train_population()
    aggregates = load_train_patient_aggregates()
    assert set(train_groups) == set(aggregates), "TRAIN population mismatch vs window manifest"
    assert len(train_groups) == 27, f"expected 27 TRAIN groups, got {len(train_groups)}"

    final_inner_validation, objective = select_final_inner_validation(train_groups, aggregates)
    optimise = sorted(set(train_groups) - set(final_inner_validation))

    rows: list[dict[str, Any]] = []
    for pg in sorted(final_inner_validation):
        rows.append({"participant_group_id": pg, "role": "FINAL_INNER_VALIDATION"})
    for pg in optimise:
        rows.append({"participant_group_id": pg, "role": "OPTIMISE"})

    audit = {
        "train_group_count": len(train_groups),
        "final_inner_validation_groups": sorted(final_inner_validation),
        "final_inner_validation_count": len(final_inner_validation),
        "optimise_group_count": len(optimise),
        "objective": objective,
        "total_eligible_windows": sum(aggregates[pg]["eligible"] for pg in train_groups),
        "total_positive_windows": sum(aggregates[pg]["positive"] for pg in train_groups),
        "total_negative_windows": sum(aggregates[pg]["negative"] for pg in train_groups),
        "final_inner_validation_eligible_windows": sum(
            aggregates[pg]["eligible"] for pg in final_inner_validation
        ),
        "final_inner_validation_positive_windows": sum(
            aggregates[pg]["positive"] for pg in final_inner_validation
        ),
        "final_inner_validation_negative_windows": sum(
            aggregates[pg]["negative"] for pg in final_inner_validation
        ),
        "optimise_eligible_windows": sum(aggregates[pg]["eligible"] for pg in optimise),
        "optimise_positive_windows": sum(aggregates[pg]["positive"] for pg in optimise),
        "optimise_negative_windows": sum(aggregates[pg]["negative"] for pg in optimise),
    }
    return {"rows": rows, "audit": audit}


def main() -> None:
    result = build()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    manifest_path = OUT_DIR / "MITDB_TRAIN_FINAL_INNER_V2_V1.csv"
    with manifest_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["participant_group_id", "role"])
        writer.writeheader()
        writer.writerows(result["rows"])

    lock = {
        "manifest_id": "MITDB_TRAIN_FINAL_INNER_V2_V1",
        "status": "FROZEN_CV_MANIFEST",
        "owner_task": "C-V2-PRE006-AUTHORITY-REPAIR",
        "predecessor_outer_manifest": "MITDB_TRAIN_CV_V2_V1",
        "predecessor_outer_manifest_sha256": hash_file(OUTER_CSV),
        "distinct_from": (
            "MITDB_TRAIN_INNER_V2_V1 (historical per-outer-fold inner manifest, untouched)"
        ),
        "final_inner_validation_size": FINAL_INNER_SIZE,
        "algorithm": ALGORITHM,
        "tie_break": TIE_BREAK,
        "method_committed_before_result_generated": True,
        "audit": result["audit"],
        "manifest_path": "manifests/model_v2/cv/MITDB_TRAIN_FINAL_INNER_V2_V1.csv",
        "manifest_sha256": hash_file(manifest_path),
        "change_control": (
            "This manifest is never regenerated based on future V2 results. Any change "
            "requires a new, additive MITDB_TRAIN_FINAL_INNER_V2_V2 successor."
        ),
    }
    lock_path = OUT_DIR / "MITDB_TRAIN_FINAL_INNER_V2_V1.lock.json"
    lock_path.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps(result["audit"], indent=2))


if __name__ == "__main__":
    main()
