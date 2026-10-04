#!/usr/bin/env python3
"""Prediction-only reproduction of the V2-FL-EVAL-001 statistics in a FRESH process: runs
scripts.compute_v2_fl_eval_stats into reports/.../verification/<label>/ and compares every output
with the canonical statistics (exact JSON equality). Never touches checkpoints or source data.
Usage: python -m scripts.verify_v2_fl_eval_stats <label>"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/model_v2/v2_fl_eval_001"
FILES = ["internal_test_statistics.json", "incart_statistics.json", "shift_tables.json",
         "stats_inputs.json"]


def main() -> None:
    label = sys.argv[1]
    target = OUT / "verification" / label
    subprocess.run([sys.executable, "-m", "scripts.compute_v2_fl_eval_stats", str(target)],
                   cwd=ROOT, check=True)
    results = {}
    for name in FILES:
        canonical = json.loads((OUT / name).read_text())
        rebuilt = json.loads((target / name).read_text())
        results[name] = canonical == rebuilt
    report = {"run_label": label, "files_identical": results,
              "all_identical": all(results.values()),
              "checkpoints_loaded": False, "source_data_opened": False,
              "status": "PASS" if all(results.values()) else "FAIL"}
    (OUT / "verification" / f"reproduction_{label}.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"label": label, "status": report["status"]}))


if __name__ == "__main__":
    main()
