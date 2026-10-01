#!/usr/bin/env python3
"""C034 Section 6: eligibility audit of the already-frozen PUBLIC_ECG_REPLAY_V1 selection.

Structural check ONLY (core_eligible, label_status, exclusion_reasons, window_samples,
sample_rate_hz, ecg_quality) against the 12 already-selected window IDs -- never an inspection
of target class, never grounds for reselection. If any window is structurally unusable, this
must STOP with PUBLIC_REPLAY_ELIGIBILITY_CONFLICT rather than silently choosing a replacement.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
WINDOWS_MANIFEST = ROOT / "manifests/windows/MITDB_WINDOWS_V1.csv"
FIXTURE_MANIFEST = ROOT / "tests/fixtures/e2e/PUBLIC_ECG_REPLAY_V1.manifest.json"

EXPECTED_SAMPLES = "2500"
EXPECTED_RATE = "250"


def audit() -> dict[str, Any]:
    selection = json.loads(FIXTURE_MANIFEST.read_text(encoding="utf-8"))["selection"]
    ordered_windows = sorted(selection["windows"], key=lambda w: w["sequence_index"])
    window_ids = [w["example_id"] for w in ordered_windows]

    with WINDOWS_MANIFEST.open(newline="", encoding="utf-8") as handle:
        by_id = {row["example_id"]: row for row in csv.DictReader(handle)}

    rows = []
    conflicts = []
    for window_id in window_ids:
        row = by_id.get(window_id)
        if row is None:
            conflicts.append(f"{window_id}: not found in windows manifest")
            continue
        entry = {
            "example_id": window_id,
            "core_eligible": row["core_eligible"],
            "label_status": row["label_status"],
            "exclusion_reasons": row["exclusion_reasons"],
            "window_samples": row["window_samples"],
            "sample_rate_hz": row["sample_rate_hz"],
            "ecg_quality": row["ecg_quality"],
        }
        rows.append(entry)
        if row["core_eligible"] != "TRUE":
            conflicts.append(f"{window_id}: core_eligible={row['core_eligible']!r}")
        if row["exclusion_reasons"]:
            conflicts.append(f"{window_id}: exclusion_reasons={row['exclusion_reasons']!r}")
        if row["window_samples"] != EXPECTED_SAMPLES:
            conflicts.append(f"{window_id}: window_samples={row['window_samples']!r}")
        if row["sample_rate_hz"] != EXPECTED_RATE:
            conflicts.append(f"{window_id}: sample_rate_hz={row['sample_rate_hz']!r}")
        if row["label_status"] not in ("ELIGIBLE_NEGATIVE", "ELIGIBLE_POSITIVE"):
            conflicts.append(f"{window_id}: label_status={row['label_status']!r}")

    return {
        "windows_checked": len(window_ids),
        "fields_checked": [
            "core_eligible",
            "label_status",
            "exclusion_reasons",
            "window_samples",
            "sample_rate_hz",
            "ecg_quality",
        ],
        "target_class_inspected_for_reselection": False,
        "rows": rows,
        "conflicts": conflicts,
        "status": "PASS" if not conflicts else "PUBLIC_REPLAY_ELIGIBILITY_CONFLICT",
    }


def main() -> None:
    result = audit()
    destination = ROOT / "reports/c034_ui_e2e/replay_eligibility_audit.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "conflicts": result["conflicts"]}, indent=2))
    if result["status"] != "PASS":
        raise SystemExit("PUBLIC_REPLAY_ELIGIBILITY_CONFLICT")


if __name__ == "__main__":
    main()
