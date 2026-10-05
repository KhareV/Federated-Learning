# ruff: noqa: E501
"""Shared CAP-004 test support (real SQLite in temp dirs; strict HTTP contract double only for
isolated unit tests - the canonical E2E always uses a real released inference process)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from api.product_app_v1_1 import create_product_app_v1_1
from product.auth.base import AuthProviderDescription, AuthProviderType
from product.devices.scenarios import TimingMode
from product.persistence.store import CapstoneSqliteStore
from scripts.capstone_cap003_test_identity import cap003_test_identity_resolver
from tests.capstone_product_support import (
    BASE,
    USER_A,
    USER_B,
    StrictInferenceDouble,
    collect_ws,
)

__all__ = ["BASE", "USER_A", "USER_B", "StrictInferenceDouble", "collect_ws", "make_persistent_app",
           "provisioned_session"]

TEST_DESCRIPTION = AuthProviderDescription(provider=AuthProviderType.DEMO, demo_mode=True,
                                           ui_banner="TEST")


class SeqIds:
    """Deterministic injected session-id generator."""

    def __init__(self, prefix: str = "SESS-T") -> None:
        self._n = 0
        self._prefix = prefix

    def __call__(self) -> str:
        self._n += 1
        return f"{self._prefix}{self._n:04d}"


def make_persistent_app(db_path: str | Path, double: StrictInferenceDouble | None = None, *,
                        resolver: Any = "default", mode: TimingMode = TimingMode.ACCELERATED,
                        ids: Any = None, clock: Any = None):
    store = CapstoneSqliteStore(db_path, **({"clock": clock} if clock else {}))
    chosen = cap003_test_identity_resolver if resolver == "default" else resolver
    app = create_product_app_v1_1(
        store=store, identity_resolver=chosen, auth_description=TEST_DESCRIPTION,
        inference_client_factory=double.client if double else None, timing_mode=mode,
        id_generator=ids or SeqIds())
    return app, store


def provisioned_session(client, scenario_id: str, headers: dict[str, str] | None = None
                        ) -> tuple[str, str]:
    """REST: create + scan + connect a device, then POST /sessions. Returns (device_id, session_id)."""
    headers = headers or USER_A
    device = client.post(f"{BASE}/devices/simulated", json={"scenario_id": scenario_id},
                         headers=headers).json()["device_id"]
    assert client.post(f"{BASE}/devices/{device}/scan", headers=headers).status_code == 200
    assert client.post(f"{BASE}/devices/{device}/connect", headers=headers).status_code == 200
    created = client.post(f"{BASE}/sessions", json={"device_id": device,
                                                    "scenario_id": scenario_id}, headers=headers)
    assert created.status_code == 200, created.text
    return device, created.json()["session_id"]
