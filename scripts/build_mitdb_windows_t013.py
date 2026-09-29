#!/usr/bin/env python3
"""Offline real-data entry point for the partition-first T013 MITDB window build."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from preprocessing.mitdb_windows import build_all  # noqa: E402


def main() -> None:
    result = build_all(ROOT)
    print(
        f"T013 real MITDB build: PASS ({result['audit']['records_successfully_processed']} "
        f"records, {result['audit']['candidate_rows']} candidates, "
        f"{result['audit']['eligible_rows']} eligible)"
    )


if __name__ == "__main__":
    main()
