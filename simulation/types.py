"""Typed structures for the WEARABLE_SIM_V1 kernel.

`ObservedRecord` is the only structure production-like code may consume; it serializes to
exactly the shape required by ``contracts/sample_schema_v1.json``. `SimulationTruth` carries
synthetic-generation ground truth and must never be consumed by production-path modules
(``deployment/mock_inference.py``, ``fusion/state_machine.py``, ``api/app.py``); see
contracts/WEARABLE_SIM_V1.md Section 10.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

SAMPLE_CONTRACT_VERSION = "SAMPLE_SCHEMA_V1"
QualityState = Literal["VALID", "DEGRADED", "UNUSABLE"]
SegmentKind = Literal[
    "NORMAL", "CONTEXT_UNAVAILABLE", "DEGRADED_CONTEXT", "UNUSABLE_ECG", "MOCK_EVENT"
]


@dataclass(frozen=True)
class VirtualParticipant:
    """A deterministic synthetic participant. Engineering entity only; see
    contracts/WEARABLE_SIM_V1.md Section 8 — no clinical/demographic attributes.
    """

    participant_id: str
    participant_seed: int
    baseline_ecg_level: int
    baseline_ppg_red: int
    baseline_ppg_ir: int
    nominal_pulse_rate: float
    nominal_spo2: float
    device_offset: int


@dataclass(frozen=True)
class SegmentSpec:
    """One named, deterministic scenario segment within a simulated session."""

    name: str
    kind: SegmentKind
    sample_count: int


@dataclass(frozen=True)
class SimulationScenario:
    scenario_id: str
    segments: tuple[SegmentSpec, ...]

    @property
    def total_samples(self) -> int:
        return sum(segment.sample_count for segment in self.segments)


@dataclass(frozen=True)
class SimulationSession:
    session_id: str
    participant: VirtualParticipant
    scenario: SimulationScenario
    simulation_version: str
    simulation_seed: int
    dataset_id: str
    source_mode: str
    profile: str


@dataclass(frozen=True)
class ObservedRecord:
    """Production-facing synthetic record. Fields mirror contracts/sample_schema_v1.json
    exactly; ``to_canonical_dict`` must validate against that schema."""

    contract_version: str
    participant_id: str
    session_id: str
    timestamp_us: int
    sample_index: int
    ecg_raw: int | None
    ppg_red_raw: int | None
    ppg_ir_raw: int | None
    spo2_pct: float | None
    spo2_valid: bool
    hr_ecg_bpm: float | None
    pr_ppg_bpm: float | None
    ecg_quality: QualityState
    ppg_quality: QualityState | None
    source: str
    preprocess_version: str | None

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "participant_id": self.participant_id,
            "session_id": self.session_id,
            "timestamp_us": self.timestamp_us,
            "sample_index": self.sample_index,
            "ecg_raw": self.ecg_raw,
            "ppg_red_raw": self.ppg_red_raw,
            "ppg_ir_raw": self.ppg_ir_raw,
            "spo2_pct": self.spo2_pct,
            "spo2_valid": self.spo2_valid,
            "hr_ecg_bpm": self.hr_ecg_bpm,
            "pr_ppg_bpm": self.pr_ppg_bpm,
            "ecg_quality": self.ecg_quality,
            "ppg_quality": self.ppg_quality,
            "source": self.source,
            "preprocess_version": self.preprocess_version,
        }


@dataclass(frozen=True)
class SimulationTruth:
    """Internal-only synthetic ground truth. Never consumed by production-path modules;
    test/simulator-validation use only. See contracts/WEARABLE_SIM_V1.md Section 10."""

    participant_id: str
    session_id: str
    sample_index: int
    segment_name: str
    segment_kind: SegmentKind
    true_activity: str
    latent_hr: float
    latent_spo2: float
    scheduled_fault: str | None
    actual_fault_active: bool
    true_signal_quality: QualityState
    source_mode: str
    expected_monitoring_state: str = field(
        metadata={"doc": "Test-only expectation; never read by production state logic."}
    )
