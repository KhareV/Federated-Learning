"""Regenerate contracts/capstone/live_event_v1.schema.json from product/events.py.

``product/events.py`` is the single authoritative definition of PRODUCT_LIVE_EVENT_V1; the JSON
Schema is a generated, parity-tested projection. Run with ``--check`` to verify without writing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from product.events import live_event_json_schema

TARGET = Path(__file__).resolve().parents[1] / "contracts/capstone/live_event_v1.schema.json"


def render() -> str:
    return json.dumps(live_event_json_schema(), indent=1, sort_keys=True) + "\n"


if __name__ == "__main__":
    text = render()
    if "--check" in sys.argv:
        sys.exit(0 if TARGET.read_text() == text else 1)
    TARGET.write_text(text)
