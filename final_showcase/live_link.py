# ruff: noqa: E501
"""Opt-in live-monitored SITE_00 participant (workstream A).

A NEW simulated monitoring session using the SITE_00-compatible event-bearing profile streams real ``ObservedRecord`` objects through the UNMODIFIED
product monitoring coordinator (``WearableStreamRuntime`` + real inference). The windows that the monitoring runtime actually emitted are tee-captured
(instance-local observer, as in ``product.observatory.live_capture``) and turned into SITE_00's local dataset with the UNCHANGED helpers
(``is_trainable``, ``normalize_windows``, ``dataset_semantic_sha``) and the UNCHANGED label adapter. The result is handed to the original federation
service through its existing ``cohort_provider`` seam. No frozen module is modified; with the mode disarmed the provider is the canonical ``get_cohort``.

Nothing here claims the monitored dataset equals the canonical one: equality is *measured* in ``parity`` and reported as observed."""

from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import threading
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import numpy as np

from federated.virtual_client_source_v1 import (
    LocalDataset,
    dataset_semantic_sha,
    is_trainable,
    normalize_windows,
    stream_windows,
)
from federated.wearable_fl_system_v1 import semantic_digest
from federated.wearable_sim_local_labels import SyntheticObservedSource
from final_showcase import link_trace
from product.devices.replay import canonical_json
from product.devices.scenarios import ScenarioSegment, ScenarioSpec, TimingMode
from product.devices.simulated import SimulatedWearableSource
from product.edge.label_adapter import SimulationLabelAdapterV1
from product.edge.local_training_buffer import LocalTrainingBufferV1
from product.edge.virtual import VirtualEdgeNode, monitoring_edge_identity
from product.federation.service import Cohort
from product.monitoring.coordinator import MonitoringService
from product.monitoring.runtime_state import DeviceEntry, RuntimeState, seed_engineering_session
from product.session import SessionState
from simulation import fl_cohort_v1
from simulation.fl_cohort_v1 import cohort_profiles

LINK_ID = "NHM_LIVE_SITE00_LINK_V1"
SCENARIO_ID = "FL_SITE_00_LIVE_LINK"
SITE_INDEX = 0
LABEL_CONTRACT = "WEARABLE_SIM_EVENT_WINDOW_V1"
LINK_LABEL = "SYNTHETIC LIVE-MONITORED SITE_00 — ENGINEERING LINK, NOT CLINICAL EVIDENCE"
DEVICE_ID = "NHM_LIVELINK_WEARABLE_00"
OWNER = "LIVELINK_OWNER"


def research_root() -> Path:
    return Path(__file__).resolve().parents[1]


class LiveLinkBlocked(RuntimeError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}:{detail}")
        self.code, self.detail = code, detail


def site00_scenario() -> ScenarioSpec:
    profile = cohort_profiles()[SITE_INDEX]
    return ScenarioSpec(scenario_id=SCENARIO_ID, seed=profile.seed, duration_s=fl_cohort_v1.DURATION_S,
                        segments=(ScenarioSegment("site00_event_bearing", 0, fl_cohort_v1.DURATION_S, None, "VALID"),))


class Site00MonitoringSource(SimulatedWearableSource):
    """The existing simulated-wearable device source, fed by the SITE_00-compatible event-bearing profile (same canonical generator as the FL cohort)."""

    def _build_timeline(self) -> Iterator[tuple[str, Any, int]]:
        for record in fl_cohort_v1.iter_observed_records(cohort_profiles()[SITE_INDEX]):
            yield ("record", record, record.timestamp_us)
        yield ("end", None, self._scenario.duration_s * 1_000_000)


class WindowTee:
    """Instance-local observer on one monitoring runtime: records every emitted window, changes nothing."""

    def __init__(self, runtime: Any) -> None:
        self.windows: list[dict[str, Any]] = []
        ingest, finish = runtime.ingest, runtime.finish

        def tee_ingest(records: Any) -> Any:
            out = ingest(records)
            self.windows.extend(out)
            return out

        def tee_finish() -> Any:
            out = finish()
            self.windows.extend(out)
            return out

        runtime.ingest, runtime.finish = tee_ingest, tee_finish


def dataset_from_windows(windows: list[dict[str, Any]], profile: Any) -> LocalDataset:
    """Same transformation as ``build_local_dataset`` but over the windows the monitoring runtime actually emitted."""
    quality = {"VALID": 0, "DEGRADED": 0, "UNUSABLE": 0}
    for w in windows:
        quality[w["ecg_quality"]] += 1
    trainable = [w for w in windows if is_trainable(w)]
    if not trainable:
        raise LiveLinkBlocked("NO_TRAINABLE_MONITORED_WINDOWS")
    edges = [int(w["timestamp_us"]) for w in trainable]
    labels = np.asarray(SimulationLabelAdapterV1(profile).labels_for_windows(edges), dtype=np.float32)
    inputs = normalize_windows(np.asarray([w["ecg"]["samples"] for w in trainable]))
    positives = int(labels.sum())
    counts = {"source_records": None, "windows_emitted": len(windows), **quality, "trainable": len(trainable), "synthetic_positive": positives,
              "synthetic_negative": len(trainable) - positives, "excluded_not_valid": len(windows) - quality["VALID"],
              "excluded_valid_but_incomplete": quality["VALID"] - len(trainable)}
    return LocalDataset(profile.client_id, profile.participant_id, profile.session_id, inputs, labels, tuple(edges), counts, dataset_semantic_sha(inputs, labels, edges))


async def monitor_site00(inference_factory: Callable[[], Any], *, session_id: str, blocking_lookahead: bool = True) -> dict[str, Any]:
    """Run one real monitoring session; return captured windows and the coordinator's own scientific trace."""
    state = RuntimeState()
    source = Site00MonitoringSource(site00_scenario(), device_id=DEVICE_ID, mode=TimingMode.ACCELERATED)
    node = VirtualEdgeNode(monitoring_edge_identity(DEVICE_ID), source)
    entry = DeviceEntry(owner_user_id=OWNER, device_id=DEVICE_ID, scenario_id=SCENARIO_ID, source=source, node=node)
    state.devices[DEVICE_ID] = entry
    await source.scan(0.0)
    entry.event_log.extend([e async for e in source.events()])
    await source.connect(DEVICE_ID)
    entry.event_log.extend([e async for e in source.events()])
    seed_engineering_session(state, owner_user_id=OWNER, device_id=DEVICE_ID, session_id=session_id)
    service = MonitoringService(state, inference_factory, blocking_lookahead=blocking_lookahead)
    try:
        await service.start(OWNER, session_id)
        session_entry = state.sessions[session_id]
        coordinator = session_entry.coordinator
        if coordinator is None or coordinator.telemetry["scientific_record_count"] != 0:
            raise LiveLinkBlocked("CAPTURE_MISSED_FIRST_SOURCE_BATCH")
        tee = WindowTee(coordinator._runtime)
        await session_entry.task
    except LiveLinkBlocked:
        raise
    except Exception as error:
        raise LiveLinkBlocked("MONITORING_SESSION_FAILED", type(error).__name__) from error
    final = session_entry.session.state
    if final is not SessionState.COMPLETED:
        raise LiveLinkBlocked("MONITORING_SESSION_NOT_COMPLETED", final.value)
    statuses = coordinator.telemetry["http_statuses"]
    return {"windows": tee.windows, "scientific_trace": coordinator.scientific_trace, "session_id": session_id, "session_state": final.value,
            "inference_http_statuses": {str(s): statuses.count(s) for s in sorted(set(statuses), key=str)}, "records_seen": coordinator.telemetry["scientific_record_count"],
            "device_id": DEVICE_ID, "scenario_id": SCENARIO_ID}


def regenerate_reference(profile: Any) -> dict[str, Any]:
    """Independent regeneration (separate runtime instance, canonical FL path) used ONLY to measure parity; never used as the training buffer in live mode."""
    digest = hashlib.sha256()
    for record in fl_cohort_v1.iter_observed_records(profile):
        digest.update(canonical_json(record.to_canonical_dict()) + b"\n")
    windows = stream_windows(SyntheticObservedSource(profile))
    return {"records_sha256": digest.hexdigest(), "windows": windows}


def parity(monitored: dict[str, Any], dataset: LocalDataset, profile: Any, canonical_dataset_sha256: str) -> dict[str, Any]:
    ref = regenerate_reference(profile)
    live_w, ref_w = monitored["windows"], ref["windows"]
    same_count = len(live_w) == len(ref_w)
    same_windows = same_count and all(a["timestamp_us"] == b["timestamp_us"] and a["ecg_quality"] == b["ecg_quality"] and a["ecg"]["samples"] == b["ecg"]["samples"] for a, b in zip(live_w, ref_w, strict=True))
    return {"records_sha256_monitored": monitored["scientific_trace"]["records_sha256"], "records_sha256_regenerated": ref["records_sha256"],
            "records_identical": monitored["scientific_trace"]["records_sha256"] == ref["records_sha256"],
            "windows_monitored": len(live_w), "windows_regenerated": len(ref_w), "window_count_identical": same_count, "window_samples_and_timestamps_identical": bool(same_windows),
            "dataset_sha256_live": dataset.dataset_sha256, "dataset_sha256_canonical_site00": canonical_dataset_sha256, "dataset_identical_to_canonical": dataset.dataset_sha256 == canonical_dataset_sha256,
            "label_contract": LABEL_CONTRACT, "counts": dataset.counts,
            "note": "Equality is an observation of this run, not an assumption; a mismatch would be reported, never hidden."}


def live_cohort(base: Cohort, dataset: LocalDataset) -> Cohort:
    """Canonical cohort with SITE_00's buffer replaced by the live-monitored dataset; the seven peers are reused unchanged."""
    first = base.clients[SITE_INDEX]
    buffer = LocalTrainingBufferV1(first.client_id, first.participant_id)
    buffer.ingest_dataset(dataset)
    clients = (dataclasses.replace(first, buffer=buffer), *base.clients[1:])
    manifest = {c.client_id: {"participant_id": c.participant_id, "session_id": c.session_id, "dataset_sha": str(c.buffer.dataset_sha256)} for c in clients}
    return Cohort(clients, manifest, semantic_digest(manifest))


class LiveLinkCohortProvider:
    """Callable used as the federation service's ``cohort_provider``. Disarmed (default) it returns the canonical cohort unchanged."""

    def __init__(self, base: Callable[[], Cohort]) -> None:
        self._base, self._armed, self._lock = base, None, threading.Lock()
        self.armed_label: str | None = None

    def __call__(self) -> Cohort:
        with self._lock:
            return self._armed if self._armed is not None else self._base()

    def base(self) -> Cohort:
        return self._base()

    def arm(self, cohort: Cohort, label: str) -> None:
        with self._lock:
            if self._armed is not None:
                raise LiveLinkBlocked("LIVE_LINK_ALREADY_ARMED")
            self._armed, self.armed_label = cohort, label

    def disarm(self) -> None:
        with self._lock:
            self._armed, self.armed_label = None, None

    @property
    def armed(self) -> bool:
        return self._armed is not None


async def run_live_link(*, service: Any, provider: LiveLinkCohortProvider, inference_factory: Callable[[], Any], user_id: str, link_id: str,
                        on_phase: Callable[[str, dict[str, Any]], None] = lambda p, d: None) -> dict[str, Any]:
    """Capture -> dataset -> parity -> arm -> original 3-round FedAvg run -> disarm. Raises LiveLinkBlocked (nothing is trained) if capture fails."""
    if service.active_live_run():
        raise LiveLinkBlocked("FEDERATION_RUN_ALREADY_ACTIVE")
    profile = cohort_profiles()[SITE_INDEX]
    canonical_sha = (await asyncio.to_thread(provider.base)).clients[SITE_INDEX].buffer.dataset_sha256
    on_phase("MONITORING", {})
    monitored = await monitor_site00(inference_factory, session_id=f"LIVELINK-{link_id}")
    dataset = dataset_from_windows(monitored["windows"], profile)
    evidence = parity(monitored, dataset, profile, str(canonical_sha))
    on_phase("CAPTURED", {"parity": evidence})
    cohort = live_cohort(await asyncio.to_thread(provider.base), dataset)
    provider.arm(cohort, link_id)
    expected = link_trace.expected_trace(dataset)
    buffered = link_trace.buffer_trace(cohort.clients[SITE_INDEX].buffer)
    tap = link_trace.TrainerTap()
    try:
        run = service.create_run(user_id, run_type="LIVE_RUN", algorithm="FEDAVG", secagg_mode="PLAIN", planned_rounds=3, scenario_id="FL_SINGLE_RUN")
        on_phase("FL_RUNNING", {"run_id": run.run_id})
        with tap:
            await service.start_run(user_id, run.run_id)
            await service.wait(run.run_id)
        final = service.get_run(user_id, run.run_id)
        meta = service.artifacts.read_run_meta(run.run_id) or {}
        candidates = list(service.store.candidate_ids_for_run(run.run_id))
        digest = service.registry.get_candidate(candidates[0]).state_digest if candidates else None
    finally:
        provider.disarm()
    try:
        trace = link_trace.verify_trace(expected, buffered, tap.calls, client_id=cohort.clients[SITE_INDEX].client_id, rounds=3)
    except link_trace.LinkTraceError as error:
        raise LiveLinkBlocked(error.code, error.detail) from error
    frozen = json.loads((research_root() / "reports/model_v2/v2_fl_005/federation_run.json").read_text())["state_progression"]["3"]["sha256"]
    return {"link_id": link_id, "link_label": LINK_LABEL, "status": str(final.status.value if hasattr(final.status, "value") else final.status), "run_id": run.run_id,
            "monitoring": {k: v for k, v in monitored.items() if k != "windows"}, "parity": evidence, "trace": {k: v for k, v in trace.items()} | {"window_identities": expected["windows"][:3], "window_identity_count": len(expected["windows"]), "buffer_dataset_sha256": buffered["dataset_sha256"]}, "committed_digests": meta.get("committed_digests"),
            "round_base_digests": meta.get("round_base_digests"), "candidate_ids": candidates, "candidate_state_digest": digest,
            "canonical_candidate_digest": frozen, "candidate_digest_equals_canonical": (digest == frozen) if digest else None, "site00_source": "LIVE_MONITORED_WINDOWS", "peers": "SEVEN_EXISTING_SYNTHETIC_CLIENTS", "production_deployed": False}
