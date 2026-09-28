"""Reusable golden-fixture rendering for the T005 WEARABLE_SIM_SMOKE vertical slice.

Both `scripts/generate_t005_fixture.py` (the CLI writer) and
`tests/test_wearable_sim_smoke.py` (the anti-drift regression test) import this module so the
checked-in fixture is always compared against an in-memory regeneration using the exact same
code path.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from simulation.profiles import (
    SMOKE_PARTICIPANT_INDEX,
    SMOKE_PARTICIPANT_SEED,
    SMOKE_SCENARIO,
    SMOKE_SESSION_ID,
    WEARABLE_SIM_SMOKE,
)
from simulation.types import SimulationSession
from simulation.wearable import (
    generate_participant,
    generate_session,
    get_truth,
    iter_observed_records,
)

OBSERVED_FIXTURE_PATH = "tests/fixtures/session_v1.jsonl"
TRUTH_FIXTURE_PATH = "tests/fixtures/session_v1_truth.jsonl"
MANIFEST_FIXTURE_PATH = "tests/fixtures/session_v1_manifest.json"

DESIGN_NOTE = (
    "Sparse smoke fixture: each record represents a discrete scenario segment, not a "
    "continuous high-rate hardware-timed stream, and is not evidence of measured ECG/PPG "
    "sampling rate, jitter, or synchronization. Multi-rate synchronization/resampling "
    "semantics are deferred to T011-T013; see contracts/WEARABLE_SIM_V1.md Section 16."
)


def build_smoke_session() -> SimulationSession:
    participant = generate_participant(SMOKE_PARTICIPANT_INDEX, SMOKE_PARTICIPANT_SEED)
    return generate_session(
        participant,
        SMOKE_SCENARIO,
        session_id=SMOKE_SESSION_ID,
        session_seed=SMOKE_PARTICIPANT_SEED,
        profile=WEARABLE_SIM_SMOKE,
    )


def render_observed_lines(session: SimulationSession) -> list[str]:
    return [
        json.dumps(record.to_canonical_dict(), sort_keys=True)
        for record in iter_observed_records(session)
    ]


def render_truth_lines(session: SimulationSession) -> list[str]:
    return [json.dumps(asdict(truth), sort_keys=True) for truth in get_truth(session)]


def build_manifest(session: SimulationSession, record_count: int) -> dict[str, Any]:
    return {
        "dataset_id": session.dataset_id,
        "simulation_version": session.simulation_version,
        "simulation_seed": session.simulation_seed,
        "profile": session.profile,
        "participant_id": session.participant.participant_id,
        "session_id": session.session_id,
        "source_mode": session.source_mode,
        "scenario_id": session.scenario.scenario_id,
        "segments": [
            {"name": segment.name, "kind": segment.kind, "sample_count": segment.sample_count}
            for segment in session.scenario.segments
        ],
        "record_count": record_count,
        "observed_fixture_path": OBSERVED_FIXTURE_PATH,
        "truth_fixture_path": TRUTH_FIXTURE_PATH,
        "design_note": DESIGN_NOTE,
    }


def render_fixture_files() -> tuple[list[str], list[str], dict[str, Any]]:
    """Return (observed_lines, truth_lines, manifest) for the smoke fixture."""
    session = build_smoke_session()
    observed = render_observed_lines(session)
    truth = render_truth_lines(session)
    manifest = build_manifest(session, len(observed))
    return observed, truth, manifest
