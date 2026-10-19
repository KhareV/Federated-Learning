# ruff: noqa: E501
"""Live-monitored simulated site for the REALISTIC cohort option: any of the eight realistic training clients can be the one genuinely monitored.

The same procedure as ``studio.site_monitor`` (the site's observed records stream through the UNMODIFIED monitoring coordinator with real inference; the windows the runtime actually emitted are
tee-captured and become that site's local dataset), over the realistic generator. ``studio.site_monitor`` and the frozen ``final_showcase.live_link`` are not edited; this module only reuses their
classes. Labels are the realistic annotation labels (``RealisticEventLabelProvider``), so a monitored realistic site gets the same annotation-noisy labels as its regenerated twin."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterator
from typing import Any

import numpy as np

from federated.virtual_client_source_v1 import (
    LocalDataset,
    dataset_semantic_sha,
    is_trainable,
    normalize_windows,
    stream_windows,
)
from final_showcase import live_link as ll
from product.devices.replay import canonical_json
from product.devices.scenarios import ScenarioSegment, ScenarioSpec, TimingMode
from product.edge.virtual import VirtualEdgeNode, monitoring_edge_identity
from product.monitoring.coordinator import MonitoringService
from product.monitoring.runtime_state import DeviceEntry, RuntimeState, seed_engineering_session
from product.session import SessionState
from simulation import fl_cohort_realistic_v2 as realistic

DEFAULT_COHORT = "REALISTIC"


def _module(cohort: str = DEFAULT_COHORT) -> Any:
    """The simulation module of a realistic-family cohort (the invented-noise V2 cohort by default, or the recorded-noise NSTDB cohort)."""
    from studio import cohorts

    return cohorts.module(cohort)


def _module_of(profile: Any) -> Any:
    import sys

    return sys.modules[type(profile).__module__]

SITE_COUNT = 8
LABEL_CONTRACT = "WEARABLE_SIM_REALISTIC_EVENT_WINDOW_V2"


def site_scenario(site: int, cohort: str = DEFAULT_COHORT) -> ScenarioSpec:
    m = _module(cohort)
    profile = m.train_profile(site)
    return ScenarioSpec(scenario_id=f"RL_SITE_{site:02d}_LIVE_LINK", seed=profile.seed, duration_s=m.DURATION_S,
                        segments=(ScenarioSegment(f"site{site:02d}_realistic_event_bearing", 0, m.DURATION_S, None, "VALID"),))


class RealisticMonitoringSource(ll.SimulatedWearableSource):
    """The existing simulated-wearable device source, fed by the chosen realistic client's records (same generator as the realistic cohort)."""

    def __init__(self, scenario: ScenarioSpec, *, site_index: int, cohort: str = DEFAULT_COHORT, **kwargs: Any) -> None:
        super().__init__(scenario, **kwargs)
        self._site_index = site_index
        self._cohort_module = _module(cohort)

    def _build_timeline(self) -> Iterator[tuple[str, Any, int]]:
        for record in self._cohort_module.iter_observed_records(self._cohort_module.train_profile(self._site_index)):
            yield ("record", record, record.timestamp_us)
        yield ("end", None, self._scenario.duration_s * 1_000_000)


async def monitor_site(inference_factory: Callable[[], Any], site: int, *, session_id: str, blocking_lookahead: bool = True, cohort: str = DEFAULT_COHORT) -> dict[str, Any]:
    """Run one real monitoring session of the chosen realistic site; return the captured windows and the coordinator's own scientific trace."""
    if not 0 <= site < SITE_COUNT:
        raise ll.LiveLinkBlocked("UNKNOWN_SITE", str(site))
    device_id, scenario = f"NHM_LIVELINK_WEARABLE_{site:02d}", site_scenario(site, cohort)
    state = RuntimeState()
    source = RealisticMonitoringSource(scenario, site_index=site, cohort=cohort, device_id=device_id, mode=TimingMode.ACCELERATED)
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


def dataset_from_windows(windows: list[dict[str, Any]], profile: Any) -> LocalDataset:
    """Same transformation as ``build_local_dataset`` over the windows the monitoring runtime actually emitted, with the realistic annotation labels."""
    quality = {"VALID": 0, "DEGRADED": 0, "UNUSABLE": 0}
    for w in windows:
        quality[w["ecg_quality"]] += 1
    trainable = [w for w in windows if is_trainable(w)]
    if not trainable:
        raise ll.LiveLinkBlocked("NO_TRAINABLE_MONITORED_WINDOWS")
    edges = [int(w["timestamp_us"]) for w in trainable]
    labels = np.asarray(_module_of(profile).RealisticEventLabelProvider(profile).labels_for_windows(edges), dtype=np.float32)
    inputs = normalize_windows(np.asarray([w["ecg"]["samples"] for w in trainable]))
    positives = int(labels.sum())
    counts = {"source_records": None, "windows_emitted": len(windows), **quality, "trainable": len(trainable), "synthetic_positive": positives,
              "synthetic_negative": len(trainable) - positives, "excluded_not_valid": len(windows) - quality["VALID"], "excluded_valid_but_incomplete": quality["VALID"] - len(trainable)}
    return LocalDataset(profile.client_id, profile.participant_id, profile.session_id, inputs, labels, tuple(edges), counts, dataset_semantic_sha(inputs, labels, edges))


def regenerate_reference(profile: Any) -> dict[str, Any]:
    """Independent regeneration used ONLY to measure parity; never the training buffer in live mode."""
    digest = hashlib.sha256()
    m = _module_of(profile)
    for record in m.iter_observed_records(profile):
        digest.update(canonical_json(record.to_canonical_dict()) + b"\n")
    return {"records_sha256": digest.hexdigest(), "windows": stream_windows(m.RealisticObservedSource(profile))}


def parity(monitored: dict[str, Any], dataset: LocalDataset, profile: Any, canonical_dataset_sha256: str) -> dict[str, Any]:
    ref = regenerate_reference(profile)
    live_w, ref_w = monitored["windows"], ref["windows"]
    same_count = len(live_w) == len(ref_w)
    same_windows = same_count and all(a["timestamp_us"] == b["timestamp_us"] and a["ecg_quality"] == b["ecg_quality"] and a["ecg"]["samples"] == b["ecg"]["samples"] for a, b in zip(live_w, ref_w, strict=True))
    return {"records_sha256_monitored": monitored["scientific_trace"]["records_sha256"], "records_sha256_regenerated": ref["records_sha256"],
            "records_identical": monitored["scientific_trace"]["records_sha256"] == ref["records_sha256"], "windows_monitored": len(live_w), "windows_regenerated": len(ref_w),
            "window_count_identical": same_count, "window_samples_and_timestamps_identical": bool(same_windows), "dataset_sha256_live": dataset.dataset_sha256,
            "dataset_sha256_canonical_site00": canonical_dataset_sha256, "dataset_identical_to_canonical": dataset.dataset_sha256 == canonical_dataset_sha256,
            "label_contract": LABEL_CONTRACT if _module_of(profile) is realistic else "WEARABLE_SIM_REALISTIC_EVENT_WINDOW_V3", "counts": dataset.counts, "note": "Equality is an observation of this run, not an assumption; a mismatch would be reported, never hidden."}
