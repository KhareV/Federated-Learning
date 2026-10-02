#!/usr/bin/env python3
"""T035-REPRO / R26.2: schema, ID-pattern, referential-integrity, and hash audit of
manifests/experiment_registry_v1.csv. Does not execute or score any experiment -- predeclared
experiment status (PLANNED/COMPLETE/...) is each implementing task's own concern, never
mutated here."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT_REGISTRY = ROOT / "manifests/experiment_registry_v1.csv"
TASK_REGISTRY = ROOT / "manifests/task_registry_v1.csv"
GATE_REGISTRY = ROOT / "manifests/gate_registry_v1.csv"

EXPERIMENT_ID_PATTERN = re.compile(r"^E\d{2}$")


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    experiments = _rows(EXPERIMENT_REGISTRY)
    task_ids = {row["task_id"] for row in _rows(TASK_REGISTRY)}
    gate_ids = {row["gate_id"] for row in _rows(GATE_REGISTRY)}

    problems: list[str] = []
    ids_seen: set[str] = set()
    for row in experiments:
        experiment_id = row["experiment_id"]
        if not EXPERIMENT_ID_PATTERN.match(experiment_id):
            problems.append(f"{experiment_id}: ID_PATTERN_VIOLATION")
        if experiment_id in ids_seen:
            problems.append(f"{experiment_id}: DUPLICATE_ID")
        ids_seen.add(experiment_id)

        implementing_task = row["implementing_task"]
        if implementing_task not in task_ids:
            problems.append(
                f"{experiment_id}: UNKNOWN_IMPLEMENTING_TASK:{implementing_task}"
            )

        for gate in row["prerequisite_gates"].split(";"):
            gate = gate.strip()
            if gate and gate not in gate_ids:
                problems.append(f"{experiment_id}: UNKNOWN_PREREQUISITE_GATE:{gate}")

        for required in ("research_question", "planned_evidence", "status"):
            if not row.get(required, "").strip():
                problems.append(f"{experiment_id}: MISSING_REQUIRED_FIELD:{required}")

    report = {
        "checkpoint": "T035",
        "requirement": "R26.2",
        "registry_path": "manifests/experiment_registry_v1.csv",
        "registry_sha256": hash_file(EXPERIMENT_REGISTRY),
        "experiment_count": len(experiments),
        "experiment_ids": sorted(ids_seen),
        "problems": problems,
        "status": "PASS" if not problems else "FAIL",
    }

    out_dir = ROOT / "reports/experiments"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "registry_audit.json"
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
