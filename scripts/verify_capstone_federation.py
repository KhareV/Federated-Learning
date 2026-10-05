# ruff: noqa: E501
"""Verify the CAPSTONE_FEDERATION_PROTOCOL_V1 lock and its amendment chain (CAP-007).

    PYTHONPATH=src:. python -m scripts.verify_capstone_federation
Exit code 0 only if every bound file, component, the component registry and every amendment link
(old sha == previous link) is consistent."""

from __future__ import annotations

import json
import sys

from scripts.cap_006_protected_audit import ROOT, verify_amended_lock

LOCK = ROOT / "artifacts/capstone/CAPSTONE_FEDERATION_PROTOCOL_V1.lock.json"
GLOB = "CAPSTONE_FEDERATION_PROTOCOL_V1.amendment_*.json"


def verify() -> dict:
    result = verify_amended_lock(LOCK, GLOB)
    result["verified"] = not result["mismatches"] and not result["broken_chain_links"]  # zero amendments is fine
    return result


def main() -> int:
    result = verify()
    print(json.dumps({k: result[k] for k in ("lock", "entries_checked", "amendments", "mismatches", "broken_chain_links", "verified")}, indent=1))
    return 0 if result["verified"] else 1


if __name__ == "__main__":
    sys.exit(main())
