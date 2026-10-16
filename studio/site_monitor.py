# ruff: noqa: E501
"""Live-monitored simulated site: ANY of the eight canonical cohort sites can be the one that is genuinely monitored.

``final_showcase.live_link.monitor_site00`` is hard-wired to SITE_00 and is a frozen module. This module generalises exactly that procedure to a chosen site without editing it:
the chosen site's frozen event-bearing profile streams real ``ObservedRecord`` objects through the UNMODIFIED monitoring coordinator (real inference); the windows the runtime
actually emitted are tee-captured with the unchanged ``WindowTee`` and become that site's local dataset through the unchanged helpers. Site 0 delegates to ``monitor_site00`` itself,
so the original SITE_00 path is byte-for-byte the same code.

Why only the eight cohort sites and not an arbitrary monitoring session: federation labels come from ``SimulationLabelAdapterV1(profile)``, which needs the event times of an
event-bearing cohort profile. A scenario session created on the Monitor page has no such event times, so it cannot honestly feed federated training."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

from final_showcase import live_link as ll
from product.devices.scenarios import ScenarioSegment, ScenarioSpec, TimingMode
from product.edge.virtual import VirtualEdgeNode, monitoring_edge_identity
from product.monitoring.coordinator import MonitoringService
from product.monitoring.runtime_state import DeviceEntry, RuntimeState, seed_engineering_session
from product.session import SessionState
from simulation import fl_cohort_v1
from simulation.fl_cohort_v1 import cohort_profiles

SITE_COUNT = 8


def site_label(site: int) -> str:
    return f"SITE_{site:02d}"


def site_scenario(site: int) -> ScenarioSpec:
    profile = cohort_profiles()[site]
    return ScenarioSpec(scenario_id=f"FL_SITE_{site:02d}_LIVE_LINK", seed=profile.seed, duration_s=fl_cohort_v1.DURATION_S,
                        segments=(ScenarioSegment(f"site{site:02d}_event_bearing", 0, fl_cohort_v1.DURATION_S, None, "VALID"),))


class SiteMonitoringSource(ll.SimulatedWearableSource):
    """The existing simulated-wearable device source, fed by the chosen site's event-bearing profile (same canonical generator as the FL cohort)."""

    def __init__(self, scenario: ScenarioSpec, *, site_index: int, **kwargs: Any) -> None:
        super().__init__(scenario, **kwargs)
        self._site_index = site_index

    def _build_timeline(self) -> Iterator[tuple[str, Any, int]]:
        for record in fl_cohort_v1.iter_observed_records(cohort_profiles()[self._site_index]):
            yield ("record", record, record.timestamp_us)
        yield ("end", None, self._scenario.duration_s * 1_000_000)


async def monitor_site(inference_factory: Callable[[], Any], site: int, *, session_id: str, blocking_lookahead: bool = True) -> dict[str, Any]:
    """Run one real monitoring session of the chosen site; return the captured windows and the coordinator's own scientific trace."""
    if not 0 <= site < SITE_COUNT:
        raise ll.LiveLinkBlocked("UNKNOWN_SITE", str(site))
    if site == ll.SITE_INDEX:
        return await ll.monitor_site00(inference_factory, session_id=session_id, blocking_lookahead=blocking_lookahead)
    device_id, scenario = f"NHM_LIVELINK_WEARABLE_{site:02d}", site_scenario(site)
    state = RuntimeState()
    source = SiteMonitoringSource(scenario, site_index=site, device_id=device_id, mode=TimingMode.ACCELERATED)
    node = VirtualEdgeNode(monitoring_edge_identity(device_id), source)
    entry = DeviceEntry(owner_user_id=ll.OWNER, device_id=device_id, scenario_id=scenario.scenario_id, source=source, node=node)
    state.devices[device_id] = entry
    await source.scan(0.0)
    entry.event_log.extend([e async for e in source.events()])
    await source.connect(device_id)
    entry.event_log.extend([e async for e in source.events()])
    seed_engineering_session(state, owner_user_id=ll.OWNER, device_id=device_id, session_id=session_id)
    service = MonitoringService(state, inference_factory, blocking_lookahead=blocking_lookahead)
    try:
        await service.start(ll.OWNER, session_id)
        session_entry = state.sessions[session_id]
        coordinator = session_entry.coordinator
        if coordinator is None or coordinator.telemetry["scientific_record_count"] != 0:
            raise ll.LiveLinkBlocked("CAPTURE_MISSED_FIRST_SOURCE_BATCH")
        tee = ll.WindowTee(coordinator._runtime)
        await session_entry.task
    except ll.LiveLinkBlocked:
        raise
    except Exception as error:
        raise ll.LiveLinkBlocked("MONITORING_SESSION_FAILED", type(error).__name__) from error
    final = session_entry.session.state
    if final is not SessionState.COMPLETED:
        raise ll.LiveLinkBlocked("MONITORING_SESSION_NOT_COMPLETED", final.value)
    statuses = coordinator.telemetry["http_statuses"]
    return {"windows": tee.windows, "scientific_trace": coordinator.scientific_trace, "session_id": session_id, "session_state": final.value,
            "inference_http_statuses": {str(s): statuses.count(s) for s in sorted(set(statuses), key=str)}, "records_seen": coordinator.telemetry["scientific_record_count"],
            "device_id": device_id, "scenario_id": scenario.scenario_id}
