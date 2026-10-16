"""Any canonical cohort site can be the genuinely live-monitored one (studio.site_monitor); SITE_00 keeps its original code path."""

from __future__ import annotations

import asyncio
from functools import cache

import pytest

from federated.virtual_client_source_v1 import build_local_dataset
from federated.wearable_sim_local_labels import SyntheticObservedSource
from final_showcase import live_link as ll
from product.edge.label_adapter import SimulationLabelAdapterV1
from simulation.fl_cohort_v1 import cohort_profiles
from studio import site_monitor
from tests.capstone_product_support import StrictInferenceDouble


@cache
def _canonical(site: int):
    profile = cohort_profiles()[site]
    return profile, build_local_dataset(SyntheticObservedSource(profile), SimulationLabelAdapterV1(profile))


def test_site_zero_delegates_to_the_original_monitor_function():
    import inspect

    assert "ll.monitor_site00(" in inspect.getsource(site_monitor.monitor_site)
    assert site_monitor.site_label(0) == "SITE_00" and site_monitor.site_label(7) == "SITE_07"


@pytest.mark.parametrize("site", [3, 4])
def test_a_monitored_site_reproduces_its_own_canonical_dataset_and_reports_parity(site):
    profile, canonical = _canonical(site)
    double = StrictInferenceDouble()
    monitored = asyncio.run(site_monitor.monitor_site(double.client, site, session_id=f"LIVELINK-TEST-{site}"))
    assert monitored["device_id"] == f"NHM_LIVELINK_WEARABLE_{site:02d}" and monitored["scenario_id"] == f"FL_SITE_{site:02d}_LIVE_LINK" and monitored["session_state"] == "COMPLETED"
    dataset = ll.dataset_from_windows(monitored["windows"], profile)
    assert dataset.client_id == f"SIM_FL_SITE_{site:02d}" and dataset.counts["trainable"] > 0
    evidence = ll.parity(monitored, dataset, profile, canonical.dataset_sha256)
    assert evidence["records_identical"] and evidence["window_samples_and_timestamps_identical"] and evidence["dataset_identical_to_canonical"]
    assert len(double.requests) > 0 and all(r.session_id == f"LIVELINK-TEST-{site}" for r in double.requests)


def test_an_unknown_site_is_refused_and_a_failed_monitoring_session_is_blocked():
    with pytest.raises(ll.LiveLinkBlocked) as unknown:
        asyncio.run(site_monitor.monitor_site(StrictInferenceDouble().client, 8, session_id="X"))
    assert unknown.value.code == "UNKNOWN_SITE"
    with pytest.raises(ll.LiveLinkBlocked) as failed:
        asyncio.run(site_monitor.monitor_site(StrictInferenceDouble(fail_with=500).client, 2, session_id="LIVELINK-TEST-FAIL"))
    assert failed.value.code in ("MONITORING_SESSION_NOT_COMPLETED", "MONITORING_SESSION_FAILED")


def test_the_runner_validates_the_monitored_site_before_creating_a_run(tmp_path):
    from studio.runner10 import StudioFl10Service, StudioRunError

    service = StudioFl10Service(root=tmp_path, observer=None, inference_factory=lambda: None, other_run_active=lambda: False)   # type: ignore[arg-type]

    async def go():
        for bad in (8, -1, True, "3", 1.5):
            with pytest.raises(StudioRunError) as error:
                await service.create("u", "B", "MODEL_V2_FINAL", 3, "FEDAVG", "PLAIN", bad)   # type: ignore[arg-type]
            assert error.value.code == "INVALID_REQUEST"
        with pytest.raises(StudioRunError) as only_b:
            await service.create("u", "A", "MODEL_V2_FINAL", 3, "FEDAVG", "PLAIN", 2)
        assert only_b.value.code == "INVALID_REQUEST"
        job = await service.create("u", "B", "MODEL_V2_FINAL", 3, "FEDAVG", "PLAIN", 5)
        assert job.monitored_site == 5 and service.jobs[job.run_id].mode == "B"
        reloaded = StudioFl10Service(root=tmp_path, observer=None, inference_factory=lambda: None, other_run_active=lambda: False)   # type: ignore[arg-type]
        assert reloaded.jobs[job.run_id].monitored_site == 5            # persisted across a restart (the interrupted run itself fails closed)
        default = await service.create("u", "B", "MODEL_V2_FINAL", 3)
        assert default.monitored_site == 0
    asyncio.run(go())
