#!/usr/bin/env python3
"""Generate contracts/openapi_v1.json from the real, unmocked production app (T032).

Never hand-authored: this script is the only source of contracts/openapi_v1.json. Running it
twice against an unchanged api/app.py must produce byte-identical output (deterministic/
canonical JSON serialization) -- tests/test_api_openapi_t032.py checks for this drift.
"""

from __future__ import annotations

import json
from pathlib import Path

from api.app import app

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "contracts/openapi_v1.json"


def generate() -> dict:
    return app.openapi()


def main() -> None:
    schema = generate()
    DESTINATION.write_text(
        json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(DESTINATION)


if __name__ == "__main__":
    main()
