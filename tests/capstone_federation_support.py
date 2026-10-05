# ruff: noqa: E501
"""Shared CAP-007 test support: real SQLite + real artifact roots in temp dirs, the real released-model-free
federation stack, real local training. A completed run is built ONCE per process per configuration
(``completed_run``) and shared read-only by the targeted tests."""

from __future__ import annotations

import json
import shutil
import tempfile
import time
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from api.product_app_v1_2 import create_product_app_v1_2
from capstone_persistence.store import CapstoneSqliteStore
from product.auth.base import AuthProviderDescription, AuthProviderType
from product.contracts import ROOT
from scripts.capstone_cap003_test_identity import cap003_test_identity_resolver
from tests.capstone_product_support import BASE, USER_A, USER_B

__all__ = [
    "BASE",
    "SINGLE_RUN",
    "USER_A",
    "USER_B",
    "CompletedRun",
    "RunIds",
    "completed_run",
    "make_fed_app",
    "poll_run",
    "reference",
]

DESCRIPTION = AuthProviderDescription(provider=AuthProviderType.DEMO, demo_mode=True, ui_banner="TEST")
SINGLE_RUN = {"run_type": "LIVE_RUN", "algorithm": "FEDAVG", "secagg_mode": "PLAIN",
              "planned_rounds": 3, "scenario_id": "FL_SINGLE_RUN"}


class RunIds:
    def __init__(self, prefix: str = "FEDRUN-T") -> None:
        self._n, self._prefix = 0, prefix

    def __call__(self) -> str:
        self._n += 1
        return f"{self._prefix}{self._n:04d}"


def make_fed_app(root: Path, **kwargs: Any):
    store = CapstoneSqliteStore(root / "product.sqlite3")
    app = create_product_app_v1_2(
        store=store, identity_resolver=kwargs.pop("resolver", cap003_test_identity_resolver),
        auth_description=DESCRIPTION, federation_artifact_root=root / "federation",
        candidate_root=root / "candidates", run_id_generator=kwargs.pop("run_ids", RunIds()),
        **kwargs)
    return app, store


def poll_run(client: TestClient, run_id: str, headers: dict[str, str], timeout: float = 420.0
             ) -> dict[str, Any]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"{BASE}/federation/runs/{run_id}", headers=headers).json()
        if body["status"] in ("COMPLETED", "FAILED"):
            return body
        time.sleep(0.5)
    raise TimeoutError(run_id)


@dataclass
class CompletedRun:
    root: Path
    run_id: str
    run: dict[str, Any]
    rounds: list[dict[str, Any]]
    events: list[dict[str, Any]]
    meta: dict[str, Any]


@cache
def completed_run(algorithm: str = "FEDAVG", secagg_mode: str = "PLAIN") -> CompletedRun:
    root = Path(tempfile.mkdtemp(prefix="cap007-test-"))
    app, _store = make_fed_app(root)
    body = {**SINGLE_RUN, "algorithm": algorithm, "secagg_mode": secagg_mode}
    with TestClient(app) as client:
        created = client.post(f"{BASE}/federation/runs", json=body, headers=USER_A)
        assert created.status_code == 200, created.text
        run_id = created.json()["run_id"]
        assert client.post(f"{BASE}/federation/runs/{run_id}/start", headers=USER_A).status_code == 200
        run = poll_run(client, run_id, USER_A)
        rounds = client.get(f"{BASE}/federation/runs/{run_id}/rounds", headers=USER_A).json()
    service = app.state.federation_service
    events = [e.model_dump(mode="json") for e in service.journal_for(run_id).events]
    meta = service.artifacts.read_run_meta(run_id)
    return CompletedRun(root, run_id, run, rounds, events, meta)


@cache
def reference() -> dict[str, Any]:
    """The frozen V2-FL-005 evidence (the parity authority); read, never copied into new truth."""
    return json.loads((ROOT / "reports/model_v2/v2_fl_005/federation_run.json").read_text())


def clone_root(root: Path) -> Path:
    """A private copy of a shared completed-run root, for tests that WRITE (e.g. a REPLAY run)."""
    target = Path(tempfile.mkdtemp(prefix="cap007-clone-")) / "root"
    shutil.copytree(root, target)
    return target
