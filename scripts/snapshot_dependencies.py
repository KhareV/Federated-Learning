#!/usr/bin/env python3
"""Write an exact, sorted snapshot of the active Python environment."""

from __future__ import annotations

from importlib.metadata import distributions
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "reports/t001/dependencies.txt"


def main() -> None:
    installed = sorted(
        {
            f"{distribution.metadata['Name']}=={distribution.version}"
            for distribution in distributions()
            if distribution.metadata.get("Name")
        },
        key=str.casefold,
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix(".txt.tmp")
    temporary.write_text("\n".join(installed) + "\n", encoding="utf-8")
    temporary.replace(OUTPUT)
    print(f"T001 dependencies: captured {len(installed)} distributions")


if __name__ == "__main__":
    main()

