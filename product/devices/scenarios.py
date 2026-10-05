"""CAPSTONE_DEVICE_SCENARIO_RUNTIME_V1 -- monitoring scenarios owned by the device/edge layer.

Scenarios are the frozen CAP-001 ``demo_scenarios_v1.json`` monitoring entries. Each is turned into
the EXISTING deterministic WEARABLE_SIM generator profile (simulation/profile_v2013.py:
``IntegrationProfile`` with ``FaultSegment``/``ContextSegment``); no parallel simulator exists. The
profile only describes SOURCE conditions (faults, context availability, transport drops); it never
describes or targets a model output.

Link outages are the ``TRANSPORT_DROPPED_CHUNK`` segments: the generator omits those samples (source
indices/timestamps skip), and the simulated device lifecycle disconnects/reconnects around them.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from product.contracts import load_contract
from simulation import SIMULATION_VERSION
from simulation.profile_v2013 import (
    CONTEXT_MODES,
    ECG_FAULTS,
    SOURCE_MODE,
    SOURCE_RATE_HZ,
    ContextSegment,
    FaultSegment,
    IntegrationProfile,
)
from simulation.wearable import DATASET_ID

MONITORING_SCENARIO_IDS = (
    "NORMAL_MONITORING", "CONTEXT_LOSS", "POOR_SIGNAL", "DISCONNECT_RECONNECT",
    "MIXED_MONITORING_SESSION",
)
LINK_OUTAGE_FAULT = "TRANSPORT_DROPPED_CHUNK"
BASE_HR_BPM = 72.0  # generator convention used by the existing V2-013 profiles (simulation only)


class TimingMode(StrEnum):
    LIVE_SPEED = "LIVE_SPEED"
    ACCELERATED = "ACCELERATED"


@dataclass(frozen=True)
class ScenarioSegment:
    name: str
    start_s: float
    end_s: float
    ecg_fault: str | None
    context_mode: str


@dataclass(frozen=True)
class ScenarioSpec:
    scenario_id: str
    seed: int
    duration_s: int
    segments: tuple[ScenarioSegment, ...]
    expected_connection_events: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        previous_end = 0.0
        for segment in self.segments:
            if segment.start_s < previous_end or segment.end_s <= segment.start_s:
                raise ValueError("SCENARIO_SEGMENTS_MUST_BE_ORDERED_AND_NON_OVERLAPPING")
            if segment.end_s > self.duration_s:
                raise ValueError("SCENARIO_SEGMENT_EXCEEDS_DURATION")
            if segment.context_mode not in CONTEXT_MODES:
                raise ValueError(f"UNKNOWN_CONTEXT_MODE:{segment.context_mode}")
            if segment.ecg_fault is not None and segment.ecg_fault not in ECG_FAULTS:
                raise ValueError(f"UNKNOWN_ECG_FAULT:{segment.ecg_fault}")
            previous_end = segment.end_s
        for _start, end in self.outage_intervals():
            if end >= self.duration_s * SOURCE_RATE_HZ:
                raise ValueError("LINK_OUTAGE_MUST_END_BEFORE_THE_SCENARIO_ENDS")

    @property
    def session_id(self) -> str:
        return f"SIM_S_CAP002_{self.scenario_id}"

    def outage_intervals(self) -> tuple[tuple[int, int], ...]:
        """Sample-index intervals [start, end) of device link outages (no records delivered)."""
        return tuple(
            (round(s.start_s * SOURCE_RATE_HZ), round(s.end_s * SOURCE_RATE_HZ))
            for s in self.segments if s.ecg_fault == LINK_OUTAGE_FAULT)

    def profile(self) -> IntegrationProfile:
        faults = tuple(FaultSegment(s.start_s, s.end_s, s.ecg_fault)
                       for s in self.segments if s.ecg_fault is not None)
        context = tuple(ContextSegment(s.start_s, s.end_s, s.context_mode)
                        for s in self.segments)
        return IntegrationProfile(
            profile_id=f"CAPSTONE_{self.scenario_id}_PROFILE_V1", session_id=self.session_id,
            duration_s=self.duration_s, seed=self.seed, base_hr_bpm=BASE_HR_BPM, faults=faults,
            context=context)

    def provenance(self) -> dict[str, object]:
        return {
            "dataset_id": DATASET_ID, "source_mode": SOURCE_MODE,
            "simulation_version": SIMULATION_VERSION, "scenario_id": self.scenario_id,
            "seed": self.seed, "session_id": self.session_id,
            "nominal_source_rate_hz": SOURCE_RATE_HZ,
            "nominal_source_rate_is": "SIMULATION convention, not a hardware measurement",
            "virtual_participant_is_human": False, "wearable_v1": False,
            "engineering_only": True, "scientific_evidence": False,
        }


def _from_contract(entry: dict) -> ScenarioSpec:
    return ScenarioSpec(
        scenario_id=entry["scenario_id"], seed=entry["seed"], duration_s=entry["duration_s"],
        segments=tuple(ScenarioSegment(s["name"], s["start_s"], s["end_s"], s["ecg_fault"],
                                       s["context_mode"]) for s in entry["segments"]),
        expected_connection_events=tuple(entry["expected_connection_events"]))


def load_scenarios() -> dict[str, ScenarioSpec]:
    """The five frozen monitoring scenarios, read from CAPSTONE_DEMO_SCENARIOS_V1."""
    entries = {e["scenario_id"]: e for e in load_contract("demo_scenarios")["scenarios"]}
    return {sid: _from_contract(entries[sid]) for sid in MONITORING_SCENARIO_IDS}
