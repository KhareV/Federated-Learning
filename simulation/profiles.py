"""Dataset size profiles for WEARABLE_SIM_V1 (contracts/WEARABLE_SIM_V1.md Section 12).

T005 implements only `WEARABLE_SIM_SMOKE`. `WEARABLE_SIM_DEV`, `WEARABLE_SIM_FULL`, and
`WEARABLE_SIM_STRESS` are reserved identifiers for later tasks and are not implemented here.
"""

from __future__ import annotations

from simulation.types import SegmentSpec, SimulationScenario

WEARABLE_SIM_SMOKE = "WEARABLE_SIM_SMOKE"
WEARABLE_SIM_DEV = "WEARABLE_SIM_DEV"
WEARABLE_SIM_FULL = "WEARABLE_SIM_FULL"
WEARABLE_SIM_STRESS = "WEARABLE_SIM_STRESS"

KNOWN_PROFILES = (WEARABLE_SIM_SMOKE, WEARABLE_SIM_DEV, WEARABLE_SIM_FULL, WEARABLE_SIM_STRESS)
IMPLEMENTED_PROFILES = (WEARABLE_SIM_SMOKE,)

# The smoke scenario deliberately exercises every FIXTURE_STATE_POLICY_V0 branch that a
# schema-valid record can reach: normal, context-unavailable, degraded-but-present context,
# and unusable ECG. SYSTEM_ERROR is exercised separately by feeding an invalid input directly
# to the state machine (a truly broken record cannot appear in a valid golden fixture).
SMOKE_SCENARIO = SimulationScenario(
    scenario_id="WEARABLE_SIM_SMOKE_SCENARIO_V1",
    segments=(
        SegmentSpec(name="normal", kind="NORMAL", sample_count=2),
        SegmentSpec(name="context_unavailable", kind="CONTEXT_UNAVAILABLE", sample_count=2),
        SegmentSpec(name="degraded_context", kind="DEGRADED_CONTEXT", sample_count=2),
        SegmentSpec(name="unusable_ecg", kind="UNUSABLE_ECG", sample_count=2),
        SegmentSpec(name="mock_event", kind="MOCK_EVENT", sample_count=2),
    ),
)

SMOKE_PARTICIPANT_INDEX = 1
SMOKE_PARTICIPANT_SEED = 20260927
SMOKE_SESSION_ID = "SIM_S000001"
