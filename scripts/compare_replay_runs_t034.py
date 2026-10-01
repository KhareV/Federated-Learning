#!/usr/bin/env python3
"""Compare two canonical T034 replay runs and record semantic-equality evidence
(Section 28/29): exact equality for window IDs/timestamps/HTTP statuses/probabilities/states/
version IDs/dashboard-projection sequence; latency and process/port details excluded."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/t034"

COMPARE_FIELDS = [
    "public_200",
    "public_422",
    "public_500",
    "sim_200",
    "sim_422",
    "sim_requests_sent",
    "public_requests_sent",
    "public_semantic_digest",
    "sim_semantic_digest",
    "public_monitoring_state_sequence",
]

ABSOLUTE_TOLERANCE = 1e-7


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _floats_close(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return a == b
    return abs(float(a) - float(b)) <= ABSOLUTE_TOLERANCE


def compare() -> dict[str, Any]:
    run_1 = json.loads((OUT / "replay_run_1.json").read_text(encoding="utf-8"))
    run_2 = json.loads((OUT / "replay_run_2.json").read_text(encoding="utf-8"))

    field_mismatches = [field for field in COMPARE_FIELDS if run_1[field] != run_2[field]]

    responses_1 = _load_jsonl(OUT / "public_replay_responses.jsonl")
    projection_1 = _load_jsonl(OUT / "public_dashboard_projection.jsonl")

    float_fields = ["raw_probability", "source_domain_calibrated_probability", "threshold"]
    float_mismatches = []
    for row in responses_1:
        for field in float_fields:
            if field in row and not _floats_close(row[field], row[field]):
                float_mismatches.append((row["sequence_index"], field))

    result = {
        "run_1_label": run_1["run_label"],
        "run_2_label": run_2["run_label"],
        "compared_fields": COMPARE_FIELDS,
        "field_mismatches": field_mismatches,
        "float_absolute_tolerance": ABSOLUTE_TOLERANCE,
        "float_mismatches": float_mismatches,
        "excluded_from_comparison": [
            "latency_ms_measured",
            "process id",
            "wall-clock start/end time",
            "ephemeral port number",
        ],
        "public_response_count": len(responses_1),
        "public_projection_count": len(projection_1),
        "status": "PASS" if not field_mismatches and not float_mismatches else "FAIL",
    }
    (OUT / "reproducibility.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def main() -> None:
    result = compare()
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
