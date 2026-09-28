#!/usr/bin/env python3
"""Write the T005 WEARABLE_SIM_SMOKE golden fixture (regenerate, don't hand-edit)."""

from __future__ import annotations

import json
from pathlib import Path

from simulation.fixtures import (
    MANIFEST_FIXTURE_PATH,
    OBSERVED_FIXTURE_PATH,
    TRUTH_FIXTURE_PATH,
    render_fixture_files,
)

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    observed, truth, manifest = render_fixture_files()

    observed_path = ROOT / OBSERVED_FIXTURE_PATH
    observed_path.parent.mkdir(parents=True, exist_ok=True)
    observed_path.write_text("\n".join(observed) + "\n", encoding="utf-8")

    truth_path = ROOT / TRUTH_FIXTURE_PATH
    truth_path.write_text("\n".join(truth) + "\n", encoding="utf-8")

    manifest_path = ROOT / MANIFEST_FIXTURE_PATH
    temporary = manifest_path.with_suffix(f"{manifest_path.suffix}.tmp")
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(manifest_path)

    print(f"T005 fixture: generated {len(observed)} observed records, {len(truth)} truth records")


if __name__ == "__main__":
    main()
