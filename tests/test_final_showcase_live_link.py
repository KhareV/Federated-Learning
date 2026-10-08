# ruff: noqa: E501
"""NHM-FINAL-SHOWCASE-001 workstream A: the opt-in live-monitored SITE_00 link."""

from __future__ import annotations

import asyncio
import time
from functools import cache

import pytest
from fastapi.testclient import TestClient

from federated.virtual_client_source_v1 import build_local_dataset, stream_windows
from federated.wearable_sim_local_labels import SyntheticObservedSource
from final_showcase import live_link as ll
from product.edge.label_adapter import SimulationLabelAdapterV1
from product.federation.service import get_cohort
from simulation.fl_cohort_v1 import cohort_profiles
from tests.capstone_federation_support import DESCRIPTION, SINGLE_RUN, RunIds, poll_run
from tests.capstone_product_support import BASE, USER_A, StrictInferenceDouble

CANONICAL_CANDIDATE = "3f0b7762ae7e05f21eb1709521404ed4d7968cae34f89e1797a0cbabd47c70e4"


@cache
def _canonical_site00():
    profile = cohort_profiles()[0]
    return profile, build_local_dataset(SyntheticObservedSource(profile), SimulationLabelAdapterV1(profile))


def test_dataset_from_windows_matches_canonical_builder_on_same_windows():
    profile, canonical = _canonical_site00()
    rebuilt = ll.dataset_from_windows(stream_windows(SyntheticObservedSource(profile)), profile)
    assert rebuilt.dataset_sha256 == canonical.dataset_sha256 and rebuilt.counts["trainable"] == canonical.counts["trainable"]


def test_provider_disarmed_is_canonical_and_arming_is_exclusive():
    base = get_cohort()
    provider = ll.LiveLinkCohortProvider(lambda: base)
    assert provider() is base and not provider.armed
    provider.arm(base, "L1")
    assert provider.armed
    with pytest.raises(ll.LiveLinkBlocked, match="ALREADY_ARMED"):
        provider.arm(base, "L2")
    provider.disarm()
    assert provider() is base


def test_live_cohort_replaces_only_site00_and_reports_observed_identity():
    base = get_cohort()
    _, canonical = _canonical_site00()
    cohort = ll.live_cohort(base, canonical)
    assert cohort.clients[1:] == base.clients[1:] and cohort.clients[0].buffer is not base.clients[0].buffer
    assert cohort.identity == base.identity            # observed because the dataset is identical, not assumed
    altered = type(canonical)(**{**canonical.__dict__, "dataset_sha256": "0" * 64})
    from product.edge.local_training_buffer import BufferError

    with pytest.raises(BufferError):                   # the unchanged buffer recomputes the dataset hash and refuses a tampered one
        ll.live_cohort(base, altered)


def test_blocked_when_monitoring_cannot_complete():
    double = StrictInferenceDouble(fail_with=500)
    with pytest.raises(ll.LiveLinkBlocked) as info:
        asyncio.run(ll.monitor_site00(double.client, session_id="LIVELINK-TEST-BLOCKED"))
    assert info.value.code in ("MONITORING_SESSION_NOT_COMPLETED", "MONITORING_SESSION_FAILED")


def test_blocked_route_never_starts_a_federation_run_and_leaves_provider_disarmed(tmp_path):
    from api.product_app_observatory_v1 import create_product_app_observatory_v1
    from capstone_persistence.store import CapstoneSqliteStore
    from product.inference.client import CapstoneInferenceClient
    from scripts.capstone_cap003_test_identity import cap003_test_identity_resolver

    double = StrictInferenceDouble(fail_with=500)
    app = create_product_app_observatory_v1(store=CapstoneSqliteStore(tmp_path / "p.sqlite3"), identity_resolver=cap003_test_identity_resolver, auth_description=DESCRIPTION,
                                            federation_artifact_root=tmp_path / "f", candidate_root=tmp_path / "c", inference_client_factory=double.client, auto_resume=False)
    assert isinstance(double.client(), CapstoneInferenceClient)
    with TestClient(app) as c:
        assert c.post(f"{BASE}/observatory/live-link/runs").status_code == 401
        link = c.post(f"{BASE}/observatory/live-link/runs", headers=USER_A).json()["link_id"]
        for _ in range(240):
            body = c.get(f"{BASE}/observatory/live-link/runs/{link}", headers=USER_A).json()
            if body["phase"] in ("BLOCKED", "COMPLETED"):
                break
            time.sleep(0.5)
        assert body["phase"] == "BLOCKED" and body["trained"] is False and "fabricated" in body["note"]
        assert c.get(f"{BASE}/federation/runs", headers=USER_A).json() == []
        assert not app.state.live_link_provider.armed
        assert c.get(f"{BASE}/observatory/live-link/runs/{link}", headers={"X-NHM-Test-User": "someone-else"}).status_code in (401, 403, 404)


def test_disabled_mode_reproduces_the_canonical_candidate_digest(tmp_path):
    from api.product_app_observatory_v1 import create_product_app_observatory_v1
    from capstone_persistence.store import CapstoneSqliteStore
    from scripts.capstone_cap003_test_identity import cap003_test_identity_resolver

    app = create_product_app_observatory_v1(store=CapstoneSqliteStore(tmp_path / "p.sqlite3"), identity_resolver=cap003_test_identity_resolver, auth_description=DESCRIPTION,
                                            federation_artifact_root=tmp_path / "f", candidate_root=tmp_path / "c", run_id_generator=RunIds("FEDRUN-OFF"), auto_resume=False)
    with TestClient(app) as c:
        run_id = c.post(f"{BASE}/federation/runs", json=SINGLE_RUN, headers=USER_A).json()["run_id"]
        c.post(f"{BASE}/federation/runs/{run_id}/start", headers=USER_A)
        assert poll_run(c, run_id, USER_A)["status"] == "COMPLETED"
        assert c.get(f"{BASE}/models", headers=USER_A).json()["capstone_fl_candidates"][0]["state_digest"] == CANONICAL_CANDIDATE
    assert not app.state.live_link_provider.armed
