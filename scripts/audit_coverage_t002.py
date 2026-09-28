#!/usr/bin/env python3
"""Run the T002 registry audit and emit machine-readable evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from nhm.coverage import audit_registries

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "reports/t002/coverage_audit.json",
    )
    parser.add_argument("--first-pass-unmapped-count", type=int)
    parser.add_argument("--manual-review-completed", action="store_true")
    args = parser.parse_args()

    result = audit_registries(ROOT)
    result["first_pass_unmapped_count"] = (
        result["unmapped_requirement_count"]
        if args.first_pass_unmapped_count is None
        else args.first_pass_unmapped_count
    )
    result["second_pass_unmapped_count"] = result["unmapped_requirement_count"]
    result["manual_review_completed"] = args.manual_review_completed
    if not args.manual_review_completed:
        result["status"] = "DRAFT_PASS" if result["status"] == "PASS" else result["status"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(f"{args.output.suffix}.tmp")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(args.output)
    print(
        f"T002 coverage audit: {result['status']} "
        f"requirements={result['requirement_count']} "
        f"unmapped={result['unmapped_requirement_count']} "
        f"orphans={result['orphan_task_count']}"
    )
    if result["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
