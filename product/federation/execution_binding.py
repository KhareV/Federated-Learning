# ruff: noqa: E501
"""CAPSTONE_FEDERATION_EXECUTION_BINDING_V1 -- the frozen rules that bind the live orchestrator to the
existing V2 FL stack (loaded from contracts/capstone/federation_execution_binding_v1.json).

Also hosts the CAPSTONE_FEDERATION_CONTRACT_V2 round-transition validator (the V1 contract file and
``product.federation.base.validate_round_transition`` stay unchanged and are never edited).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from federated.model_v2_fl import state_sha
from product.contracts import IllegalTransitionError, assert_transition
from product.federation.base import AggregationMode, Algorithm, RoundState, RunType

ROOT = Path(__file__).resolve().parents[2]
BINDING_PATH = ROOT / "contracts/capstone/federation_execution_binding_v1.json"
CONTRACT_V2_PATH = ROOT / "contracts/capstone/federation_v2.json"
BINDING_ID = "CAPSTONE_FEDERATION_EXECUTION_BINDING_V1"
CONTRACT_V2_ID = "CAPSTONE_FEDERATION_CONTRACT_V2"
PUBLIC_SCENARIO = "FL_SINGLE_RUN"
PLANNED_ROUNDS = 3
RUN_BASE_MODEL_ID = "FL_INIT_V2"
PROTOCOL_ID = "V2_FL_WEARABLE_SYSTEM_PROTOCOL_V1"
MU_LOCK = ROOT / "artifacts/FEDPROX_MU_V2.lock.json"


class BindingViolation(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def load_binding() -> dict[str, Any]:
    return json.loads(BINDING_PATH.read_text())


def load_contract_v2() -> dict[str, Any]:
    return json.loads(CONTRACT_V2_PATH.read_text())


def round_transitions_v2() -> dict[str, tuple[str, ...]]:
    return {k: tuple(v) for k, v in load_contract_v2()["round_transitions"].items()}


def validate_round_transition_v2(current: RoundState, new: RoundState, *, final_round: bool) -> None:
    """V2 table plus the final/non-final split: only the final round may create a candidate and only a
    non-final round may go AGGREGATING -> COMPLETED."""
    assert_transition(round_transitions_v2(), current.value, new.value, "ROUND")
    if current is RoundState.AGGREGATING:
        if final_round and new is RoundState.COMPLETED:
            raise IllegalTransitionError("ILLEGAL_ROUND_TRANSITION:final round must create a candidate")
        if not final_round and new is RoundState.CANDIDATE_CREATED:
            raise IllegalTransitionError("ILLEGAL_ROUND_TRANSITION:non-final round cannot create a candidate")


def frozen_fl_init_sha() -> str:
    return str(json.loads(MU_LOCK.read_text())["FL_INIT_V2_round_0_state_sha256"])


def frozen_fedprox_mu() -> float:
    return float(json.loads(MU_LOCK.read_text())["selected_mu"])


def check_public_request(*, run_type: str, algorithm: str, secagg_mode: str, planned_rounds: int,
                         scenario_id: str) -> None:
    """Public create-run policy (CAP-007): only FL_SINGLE_RUN, exactly 3 rounds, known enums."""
    binding = load_binding()
    if scenario_id != binding["public_scenario"]:
        raise BindingViolation(f"SCENARIO_NOT_AVAILABLE:{scenario_id}")
    if planned_rounds != PLANNED_ROUNDS:
        raise BindingViolation("PLANNED_ROUNDS_MUST_BE_3")
    RunType(run_type), Algorithm(algorithm), AggregationMode(secagg_mode)


def verify_round_base(*, round_id: int, state: dict[str, np.ndarray], committed: dict[int, str],
                      base_model_id: str = RUN_BASE_MODEL_ID) -> str:
    """Return the verified base digest of ``round_id`` or raise.

    round 1 -> the frozen FL_INIT_V2 state; round N>1 -> the digest of round N-1's committed global
    state. MODEL_V2_FINAL (and any non FL_INIT_V2 run base, candidates included) is refused."""
    if base_model_id != RUN_BASE_MODEL_ID:
        code = ("CANDIDATE_BASE_NOT_ENABLED_YET" if base_model_id.startswith("CAPSTONE_FL_CANDIDATE_")
                else "BASE_MODEL_NOT_ALLOWED")
        raise BindingViolation(code)
    digest = state_sha(state)
    expected = frozen_fl_init_sha() if round_id == 1 else committed.get(round_id - 1)
    if expected is None:
        raise BindingViolation("PREVIOUS_ROUND_NOT_COMMITTED")
    if digest != expected:
        raise BindingViolation("ROUND_BASE_LINEAGE_MISMATCH")
    return digest
