"""Loader for the machine-readable CAP-001 contract artifacts under ``contracts/capstone``.

The JSON files are the single authoritative source for state vocabularies, transition tables,
routes, storage entities, auth rules and demo scenarios. Python enums elsewhere in ``product``
only name those vocabularies; ``tests/test_capstone_contracts.py`` proves they cannot drift.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_DIR = ROOT / "contracts" / "capstone"
CONFIG_DIR = ROOT / "configs" / "capstone"

CONTRACT_FILES = {
    "device_source": "device_source_v1.json",
    "session": "session_v1.json",
    "live_event": "live_event_v1.json",
    "product_api": "product_api_v1.json",
    "auth_policy": "auth_policy_v1.json",
    "storage_policy": "storage_policy_v1.json",
    "demo_scenarios": "demo_scenarios_v1.json",
    "connection_table": "connection_table_v1.json",
    "edge_node": "edge_node_v1.json",
    "training_buffer": "local_training_buffer_v1.json",
    "fl_client": "fl_client_v1.json",
    "federation": "federation_v1.json",
    "fl_run": "fl_run_v1.json",
    "model_registry": "model_registry_v1.json",
    "model_governance": "model_governance_v1.json",
    "hardware_replacement": "real_hardware_replacement_v1.json",
}


class IllegalTransitionError(ValueError):
    """A device/session state transition that the frozen contract does not allow."""


@cache
def load_contract(name: str) -> dict[str, Any]:
    return json.loads((CONTRACT_DIR / CONTRACT_FILES[name]).read_text())


@cache
def load_protocol() -> dict[str, Any]:
    return json.loads((CONFIG_DIR / "capstone_product_protocol_v1.json").read_text())


def transition_table(name: str, key: str) -> dict[str, tuple[str, ...]]:
    raw = load_contract(name)[key]
    return {state: tuple(targets) for state, targets in raw.items()}


def assert_transition(table: dict[str, tuple[str, ...]], current: str, new: str, kind: str) -> None:
    if current not in table:
        raise IllegalTransitionError(f"UNKNOWN_{kind}_STATE:{current}")
    if new not in table:
        raise IllegalTransitionError(f"UNKNOWN_{kind}_STATE:{new}")
    if new not in table[current]:
        raise IllegalTransitionError(f"ILLEGAL_{kind}_TRANSITION:{current}->{new}")
