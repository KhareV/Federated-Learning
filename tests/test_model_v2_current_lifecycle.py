"""STRICT current-lineage lifecycle state machine for the MODEL_V2 registries. Exact statuses --
no 'in {...}' relaxation. This is the single test that must be updated at each phase transition
(older phase-specific tests only verify forward-compatible, non-regressing facts).

Current state: V2-FL-001/002/003, V2-FL-EVAL-001, V2-FL-004 and V2-FL-005 PASS (V2FLG0/1/2, V2FLEG0,
V2FLG3 and V2FLG4 PASS); V2-014 and V2G13 NOT_STARTED; V2-005 keeps its historical
SKIPPED_BY_PROTOCOL semantics."""

from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EXPECTED_TASKS = {
    "V2-001": "PASS", "V2-002": "PASS", "V2-003": "PASS", "V2-004": "PASS",
    "V2-005": "SKIPPED_BY_PROTOCOL", "V2-006": "PASS", "V2-007": "PASS", "V2-008": "PASS",
    "V2-009": "PASS", "V2-010": "PASS", "V2-011": "PASS", "V2-012": "PASS", "V2-013": "PASS",
    "V2-014": "NOT_STARTED",
    "V2-FL-001": "PASS", "V2-FL-002": "PASS", "V2-FL-003": "PASS",
    "V2-FL-EVAL-001": "PASS", "V2-FL-004": "PASS", "V2-FL-005": "PASS",
}
EXPECTED_GATES = {
    **{f"V2G{n}": "PASS" for n in range(13)}, "V2G13": "NOT_STARTED",
    "V2FLG0": "PASS", "V2FLG1": "PASS", "V2FLG2": "PASS", "V2FLEG0": "PASS",
    "V2FLG3": "PASS", "V2FLG4": "PASS",
}
EXPECTED_COMPONENTS = {
    "MODEL_V2_FINAL": "FROZEN", "CAL_V2": "FROZEN",
    "GATEWAY_ARTIFACT_V2": "FROZEN_RESEARCH_GATEWAY",
    "API_RUNTIME_V2": "FROZEN_RESEARCH_RUNTIME", "API_RUNTIME_V2_1": "FROZEN_RESEARCH_RUNTIME",
    "EXPLAINABILITY_V2": "FROZEN_EXPLAINABILITY",
    "MODEL_V2_FL_PROTOCOL_V1": "FROZEN_BEFORE_FIRST_V2_FL_OUTCOME",
    "MODEL_V2_FL_PROTOCOL_V2": "FROZEN_RESEARCH_PROTOCOL_SUCCESSOR",
    "FL_INIT_V2": "FROZEN", "FL_IID_MODEL_V2_V1": "FROZEN", "FL_NON_IID_MODEL_V2_V1": "FROZEN",
    "FEDPROX_METHOD_V2": "FROZEN", "FEDPROX_MU_V2": "FROZEN_ENGINEERING_METHOD",
    "V2_FL_EVAL_PROTOCOL_V1": "FROZEN", "V2_FL_TEST_FAMILY_V1": "FROZEN",
    "V2_FL_INTERNAL_TEST_PREDICTION_FAMILY_V1": "FROZEN",
    "V2_FL_INCART_PREDICTION_FAMILY_V1": "FROZEN",
    "MODEL_V2_LIFECYCLE_TEST_POLICY_V1": "FROZEN_CONTROL_POLICY",
    "SECAGG_CONFIG_V2": "FROZEN_RESEARCH_PRIVACY_PROTOCOL",
    "SECAGG_METHOD_V2": "FROZEN_PRE_RESULT_METHOD",
    "WEARABLE_SIM_FL_COHORT_V1": "FROZEN_ENGINEERING_COHORT",
    "V2_FL_WEARABLE_SYSTEM_PROTOCOL_V1": "FROZEN_ENGINEERING_PROTOCOL",
    "WEARABLE_SIM_FL_SYSTEM_REPLAY_V1": "FROZEN_ENGINEERING_REPLAY",
    "VIRTUAL_FL_CLIENT_SOURCE_V1": "FROZEN_INTERFACE_CONTRACT",
    "WEARABLE_SIM_FL_SECAGG_COMPAT_V1": "FROZEN_ENGINEERING_COMPATIBILITY",
}


def _rows(name: str) -> list[dict]:
    with (ROOT / f"manifests/model_v2/{name}_registry_v1.csv").open(newline="") as handle:
        return list(csv.DictReader(handle))


def test_task_registry_is_exactly_the_current_state() -> None:
    actual = {r["task_id"]: r["status"] for r in _rows("task")}
    assert actual == EXPECTED_TASKS


def test_gate_registry_is_exactly_the_current_state() -> None:
    actual = {r["gate_id"]: r["status"] for r in _rows("gate")}
    assert actual == EXPECTED_GATES


def test_key_component_statuses_are_exact() -> None:
    actual = {r["component_id"]: r["status"] for r in _rows("component")}
    for component, status in EXPECTED_COMPONENTS.items():
        assert actual[component] == status, component
    assert "FL_STATE_TRANSPORT_V2" not in actual


def test_no_unknown_status_vocabulary() -> None:
    allowed = {"PASS", "NOT_STARTED", "SKIPPED_BY_PROTOCOL"}
    assert {r["status"] for r in _rows("task")} <= allowed
    assert {r["status"] for r in _rows("gate")} <= {"PASS", "NOT_STARTED"}


def test_next_phases_are_exactly_not_started_and_gate_blocking_is_consistent() -> None:
    tasks = {r["task_id"]: r for r in _rows("task")}
    gates = {r["gate_id"]: r for r in _rows("gate")}
    for later in ("V2-014",):
        assert tasks[later]["status"] == "NOT_STARTED"
    assert gates["V2FLG2"]["blocks_tasks"] == "V2-FL-EVAL-001"
    assert gates["V2FLEG0"]["blocks_tasks"] == "V2-FL-004"
    assert tasks["V2-FL-EVAL-001"]["prerequisites"] == "V2-FL-003"
    assert tasks["V2-FL-004"]["prerequisites"] == "V2-FL-EVAL-001"
    assert gates["V2FLG3"]["blocks_tasks"] == "V2-FL-005"
    assert gates["V2FLG4"]["blocks_tasks"] == "V2-014"
