"""C-V2-013-QUALITY-FLATLINE-AUDIT: additive simulator scenario with a TRUE contract flatline.

QUALITY_V1 evaluates the FILTERED 250 Hz window and flags FLATLINE only when
std/rms <= 1e-12 (or rms == 0). Through the frozen PREPROC_V1 chain a constant NONZERO source is
turned into a persistent ~1e-5 resampler ripple, so only an exactly-zero source stays exactly
constant. This scenario therefore drives ``ecg_raw == 0`` (a dead lead reading ADC zero) from the
start of the stream. It wraps, and never edits, simulation.profile_v2013 (frozen under the
API_RUNTIME_V2 lock). Generator side only: the production runtime never imports this module.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator
from dataclasses import dataclass

import simulation.profile_v2013 as prof
from simulation.types import ObservedRecord

BASE_PROFILE = dataclasses.replace(
    prof.LIVE_EXCERPT_PROFILE, profile_id="WEARABLE_SIM_V2_FLATLINE_BASE", faults=(),
    context=(prof.ContextSegment(0.0, 100.0, "VALID"),), duration_s=100)


@dataclass(frozen=True)
class FlatlineProfile:
    profile_id: str
    session_id: str
    duration_s: int
    zero_start_s: float
    zero_end_s: float
    seed: int = prof.SEED


FULL_FLATLINE_PROFILE = FlatlineProfile(
    "WEARABLE_SIM_V2_FLATLINE_PROFILE", "SIM_S_C_V2_013_FLATLINE_000001", 100, 0.0, 40.0)
EXCERPT_FLATLINE_PROFILE = FlatlineProfile(
    "WEARABLE_SIM_V2_FLATLINE_EXCERPT", "SIM_S_C_V2_013_FLATLINE_EXCERPT_000001", 45, 0.0, 25.0)


def iter_flatline_records(profile: FlatlineProfile = FULL_FLATLINE_PROFILE
                          ) -> Iterator[ObservedRecord]:
    base = dataclasses.replace(
        BASE_PROFILE, session_id=profile.session_id, duration_s=profile.duration_s,
        context=(prof.ContextSegment(0.0, float(profile.duration_s), "VALID"),))
    lo = round(profile.zero_start_s * prof.SOURCE_RATE_HZ)
    hi = round(profile.zero_end_s * prof.SOURCE_RATE_HZ)
    for record in prof.iter_observed_records(base):
        yield dataclasses.replace(record, ecg_raw=0) if lo <= record.sample_index < hi else record


def provenance(profile: FlatlineProfile = FULL_FLATLINE_PROFILE) -> dict[str, object]:
    return {"generator": "simulation.flatline_scenario_c_v2_013", "profile": vars(profile),
            "base_generator": "simulation.profile_v2013.iter_observed_records",
            "flat_source": "ecg_raw == 0 for the zero interval (exact ADC zero)",
            "participants_are_human": False, "protected_partitions_accessed": False}
