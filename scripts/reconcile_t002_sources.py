#!/usr/bin/env python3
"""Record field-level reconciliation from provisional to canonical T002 task definitions."""

from __future__ import annotations

import csv
import io
import subprocess
from pathlib import Path

from nhm.coverage import read_csv

ROOT = Path(__file__).resolve().parents[1]
PROVISIONAL_COMMIT = "c6d009a04d9f265f0bbdbeb76a474028b21f00e6"
PROVISIONAL_PATH = "manifests/task_registry_v1.csv"
OUTPUT = ROOT / "reports/t002/task_registry_reconciliation.csv"
FIELDS = (
    "task_id",
    "derived_value",
    "authoritative_plan_value",
    "field",
    "scientific_impact",
    "coverage_impact",
    "resolution",
)
COMPARE_FIELDS = ("task_name", "phase_family", "prerequisites", "gate_impact")


def provisional_rows() -> list[dict[str, str]]:
    result = subprocess.run(
        ["git", "show", f"{PROVISIONAL_COMMIT}:{PROVISIONAL_PATH}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return list(csv.DictReader(io.StringIO(result.stdout)))


def main() -> None:
    old = {row["task_id"]: row for row in provisional_rows()}
    new = {
        row["task_id"]: row for row in read_csv(ROOT / "manifests/task_registry_v1.csv")
    }
    rows = []
    for task_id in sorted(new):
        for field in COMPARE_FIELDS:
            if old[task_id][field] == new[task_id][field]:
                continue
            rows.append(
                {
                    "task_id": task_id,
                    "derived_value": old[task_id][field],
                    "authoritative_plan_value": new[task_id][field],
                    "field": field,
                    "scientific_impact": "NONE: v2.2 scientific decisions are unchanged",
                    "coverage_impact": (
                        "Task ownership and downstream references required semantic reconciliation"
                    ),
                    "resolution": "REPLACED_WITH_EXECUTION_PLAN_VALUE",
                }
            )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix(f"{OUTPUT.suffix}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(OUTPUT)
    affected_tasks = {row["task_id"] for row in rows}
    print(
        f"Task reconciliation: rows={len(rows)} affected_tasks={len(affected_tasks)}"
    )


if __name__ == "__main__":
    main()
