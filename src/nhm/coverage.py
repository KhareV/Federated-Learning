"""Machine-checkable T002 traceability and change-control invariants."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

TASK_STATUSES = {
    "NOT_STARTED",
    "IN_PROGRESS",
    "PASS",
    "PASS_WITH_WARNINGS",
    "BLOCKED",
    "FAILED",
    "SUPERSEDED",
}
GATE_STATUSES = {"NOT_STARTED", "PASS", "FAIL", "BLOCKED", "SUPERSEDED"}
REQUIREMENT_STATUSES = {
    "PLANNED",
    "IMPLEMENTED",
    "VERIFIED",
    "BLOCKED",
    "OUT_OF_SCOPE_BY_SPEC",
    "SUPERSEDED",
}
REQUIREMENT_TYPES = {
    "SCIENTIFIC_TARGET",
    "DATA_CONTRACT",
    "DATASET_POLICY",
    "LEAKAGE_INVARIANT",
    "PREPROCESSING",
    "LABEL_POLICY",
    "SPLIT_POLICY",
    "MODEL",
    "CALIBRATION",
    "STATISTICS",
    "MULTIMODAL",
    "ALERTING",
    "FEDERATED",
    "PRIVACY",
    "DEPLOYMENT",
    "WEARABLE",
    "API",
    "DASHBOARD",
    "REPRODUCIBILITY",
    "GATE",
    "EXPERIMENT",
    "CLAIM_BOUNDARY",
    "DEFINITION_OF_DONE",
    "RELEASE",
}
CLAIM_BOUNDARY_IDS = {f"CB{number:02d}" for number in range(1, 7)}
SPEC_FILENAME = "NHM_ML_Revised_Locked_Specification_v2.2.docx"
PLAN_FILENAME = "NHM_Solo_Implementation_Execution_Plan_v1.0.docx"
PLAN_SHA256 = "f260a93e973161a1461497fbb4ae0194bc72f20fc47c1689e57ec6c0cd6f2696"
# The highest task_id currently permitted to be PASS/IN_PROGRESS. Bump this only when a task
# genuinely closes; it never grants a status change by itself. This threshold is intentionally
# independent of whether an *earlier* task is BLOCKED (e.g. T004/BLOCKED_HARDWARE does not
# lower this below T005): the check below only rejects a task ID *above* the threshold, so an
# authorized hardware-independent task can still reach PASS while a numerically earlier,
# explicitly blocked task has not.
LATEST_APPROVED_TASK = "T033"

# Explicit allowlist rather than a numeric/highest-gate threshold: gates do not close in
# strict numeric order once a hardware-independent track exists. G1 (hardware/data contract)
# is BLOCKED_HARDWARE and deliberately stays NOT_STARTED (see
# docs/HARDWARE_DEFERRED_EXECUTION_PLAN.md) while G2/G3 (public-dataset acquisition and
# validation, T006+T007), G4 (label freeze, T008), and G5 (split/leakage audit, T009+T010)
# legitimately close ahead of it. Add a gate here only when its own documented pass criteria
# are genuinely met.
APPROVED_PASSED_GATES = {
    "G0",
    "G2",
    "G3",
    "G4",
    "G5",
    "G6",
    "G7",
    "G8",
    "G10",
    "G11",
    "G12",
    "G13",
    "G14",
    "G15",
    "G17",
    "G18",
    "G19",
}

# Same allowlist principle for freeze status: a freeze may be marked FROZEN only once its
# owning gate has genuinely closed. F01 (source authority) freezes at G0; F04 (label mapping,
# AAMI_SVF_MAP_V1) freezes at G4 (T008); F05 (patient split, MITDB_SPLIT_V1) freezes at G5
# (T009+T010).
APPROVED_FROZEN_ARTIFACTS = {
    "F01",
    "F04",
    "F05",
    "F06",
    "F07",
    "F08",
    "F09",
    "F10",
    "F11",
    "F12",
    "F13",
    "F14",
}

CANONICAL_GATE_TASK_OWNERS = {
    "G0": "T001;T002",
    "G1": "T003;T004",
    "G2": "T006;T007",
    "G3": "T006;T007",
    "G4": "T008",
    "G5": "T009;T010",
    "G6": "T010;T011;T012;T013",
    "G7": "T014",
    "G8": "T015;T016",
    "G9": "T021;T022;T023",
    "G10": "T017;T018",
    "G11": "T024;T025",
    "G12": "T026",
    "G13": "T027",
    "G14": "T028",
    "G15": "T029",
    "G16": "T030",
    "G17": "T031",
    "G18": "T032",
    "G19": "T033",
    "G20": "T035",
    "G21": "T034",
    "G22": "T036",
}
CANONICAL_EXPERIMENT_TASK_OWNERS = {
    "E01": "T014",
    "E02": "T015",
    "E03": "T017",
    "E04": "T018",
    "E05": "T019",
    "E06": "T020",
    "E07": "T021",
    "E08": "T023",
    "E09": "T025",
    "E10": "T026",
    "E11": "T026",
    "E12": "T026",
    "E13": "T027",
    "E14": "T028",
    "E15": "T029",
    "E16": "T030",
}
CANONICAL_EVIDENCE_TASK_OWNERS = {
    "EV001": "T001",
    "EV002": "T002",
    "EV003": "T002",
    "EV004": "T002",
    "EV005": "T003;T004",
    "EV006": "T006;T007",
    "EV007": "T008",
    "EV008": "T009;T010",
    "EV009": "T010;T011;T012;T013",
    "EV010": "T014",
    "EV011": "T015;T016",
    "EV012": "T021",
    "EV013": "T022;T023",
    "EV014": "T017",
    "EV015": "T018",
    "EV016": "T019",
    "EV017": "T020",
    "EV018": "T031",
    "EV019": "T024;T025",
    "EV020": "T026",
    "EV021": "T027",
    "EV022": "T028",
    "EV023": "T029",
    "EV024": "T030",
    "EV025": "T032",
    "EV026": "T033",
    "EV027": "T034",
    "EV028": "T035",
    "EV029": "T036",
    "EV030": "T002",
    "EV031": "T002",
}
CANONICAL_FREEZE_INVALIDATIONS = {
    "F01": "T002-T036",
    "F02": "T005;T030;T032;T034",
    "F03": "T008-T031;T034-T036",
    "F04": "T009-T031;T034-T036",
    "F05": "T010-T031;T034-T036",
    "F06": "T014-T035",
    "F07": "T015;T016;T035;T036",
    "F08": "T017-T034;T036",
    "F09": "T018-T034;T036",
    "F10": "T019-T036",
    "F11": "T031;T035;T036",
    "F12": "T027;T028;T035;T036",
    "F13": "T035;T036",
    "F14": "T030;T032-T036",
    "F15": "",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def split_refs(value: str) -> list[str]:
    return [item.strip() for item in value.split(";") if item.strip()]


def expand_refs(value: str) -> list[str]:
    """Expand semicolon-delimited references, including same-prefix numeric ranges."""
    expanded: list[str] = []
    for item in split_refs(value):
        match = re.fullmatch(r"([A-Z]+)(\d+)-([A-Z]+)?(\d+)", item)
        if not match:
            expanded.append(item)
            continue
        prefix, start, end_prefix, end = match.groups()
        if end_prefix and end_prefix != prefix:
            expanded.append(item)
            continue
        width = len(start)
        expanded.extend(f"{prefix}{number:0{width}d}" for number in range(int(start), int(end) + 1))
    return expanded


def duplicates(values: list[str]) -> list[str]:
    return sorted({value for value in values if values.count(value) > 1})


def classify_change(description: str) -> str:
    """Classify representative changes under the documented A/B/C policy."""
    normalized = description.casefold()
    scientific_markers = (
        "mit-bih lead",
        "best-performing lead",
        "window to 8",
        "window length",
        "aami_svf_map",
        "target change",
        "split policy",
        "threshold policy",
        "preprocessing change",
        "federated partition",
    )
    if any(marker in normalized for marker in scientific_markers):
        return "C"
    if any(marker in normalized for marker in ("api field", "schema", "interface", "file path")):
        return "B"
    return "A"


def audit_registries(repository_root: str | Path) -> dict[str, Any]:
    root = Path(repository_root)
    manifest_dir = root / "manifests"
    tasks = read_csv(manifest_dir / "task_registry_v1.csv")
    gates = read_csv(manifest_dir / "gate_registry_v1.csv")
    requirements = read_csv(manifest_dir / "requirements_v22.csv")
    freezes = read_csv(manifest_dir / "freeze_registry_v1.csv")
    controls = read_csv(manifest_dir / "do_not_start_v1.csv")
    experiments = read_csv(manifest_dir / "experiment_registry_v1.csv")
    evidence = read_csv(manifest_dir / "evidence_registry_v1.csv")

    errors: list[str] = []
    expected_tasks = {f"T{number:03d}" for number in range(1, 37)}
    expected_gates = {f"G{number}" for number in range(23)}
    task_ids = [row["task_id"] for row in tasks]
    gate_ids = [row["gate_id"] for row in gates]
    requirement_ids = [row["requirement_id"] for row in requirements]
    task_set, gate_set, requirement_set = set(task_ids), set(gate_ids), set(requirement_ids)

    task_snapshot = json.loads((manifest_dir / "task_packets_v1.json").read_text(encoding="utf-8"))
    snapshot_tasks = {row["task_id"]: row for row in task_snapshot["packets"]}
    semantic_task_mapping_errors: list[str] = []
    if (
        task_snapshot["source_document"] != PLAN_FILENAME
        or task_snapshot["source_sha256"] != PLAN_SHA256
        or task_snapshot["packet_count"] != 36
    ):
        semantic_task_mapping_errors.append("canonical task snapshot source identity mismatch")

    reconciliation_path = root / "reports/t002/task_registry_reconciliation.csv"
    if reconciliation_path.exists():
        reconciliation = read_csv(reconciliation_path)
        task_by_id = {row["task_id"]: row for row in tasks}
        for row in reconciliation:
            current = task_by_id.get(row["task_id"], {}).get(row["field"])
            if current != row["authoritative_plan_value"]:
                semantic_task_mapping_errors.append(
                    f"stale reconciliation row {row['task_id']}.{row['field']}"
                )
        if {row["task_id"] for row in reconciliation} != expected_tasks:
            semantic_task_mapping_errors.append(
                "task reconciliation does not cover all 36 corrected task packets"
            )
    else:
        semantic_task_mapping_errors.append("task reconciliation evidence is missing")

    if len(tasks) != 36 or task_set != expected_tasks:
        errors.append(f"task registry must be exactly T001-T036; got {len(tasks)} rows")
    if duplicates(task_ids):
        errors.append(f"duplicate task IDs: {duplicates(task_ids)}")
    invalid_task_statuses = sorted({row["status"] for row in tasks} - TASK_STATUSES)
    if invalid_task_statuses:
        errors.append(f"invalid task statuses: {invalid_task_statuses}")
    future_task_passes = [
        row["task_id"]
        for row in tasks
        if row["task_id"] > LATEST_APPROVED_TASK and row["status"] not in {"NOT_STARTED", "BLOCKED"}
    ]
    if future_task_passes:
        errors.append(f"future tasks falsely advanced: {future_task_passes}")

    for row in tasks:
        source = snapshot_tasks.get(row["task_id"])
        if source is None:
            semantic_task_mapping_errors.append(f"{row['task_id']}:missing source packet")
            continue
        comparisons = {
            "task_name": source["task_name"],
            "phase_family": source["phase"],
            "source_prerequisites": source["prerequisites"],
            "source_gate_impact": source["gate_freeze_impact"],
            "source_document": PLAN_FILENAME,
            "source_sha256": PLAN_SHA256,
        }
        for field, expected in comparisons.items():
            if row.get(field) != expected:
                semantic_task_mapping_errors.append(
                    f"{row['task_id']}.{field}: expected {expected!r}, got {row.get(field)!r}"
                )
    remaining_derived = [
        row["task_id"] for row in tasks if "derived" in " ".join(row.values()).casefold()
    ]
    if remaining_derived:
        semantic_task_mapping_errors.append(
            f"remaining derived task definitions: {remaining_derived}"
        )

    invalid_prerequisites: list[str] = []
    for row in tasks:
        for reference in split_refs(row["prerequisites"]):
            if reference not in task_set | gate_set:
                invalid_prerequisites.append(f"{row['task_id']}->{reference}")
        for reference in split_refs(row["gate_impact"]):
            if reference not in gate_set:
                invalid_prerequisites.append(f"{row['task_id']}.gate_impact->{reference}")
    if invalid_prerequisites:
        errors.append(f"invalid task prerequisites: {invalid_prerequisites}")

    if len(gates) != 23 or gate_set != expected_gates:
        errors.append(f"gate registry must be exactly G0-G22; got {len(gates)} rows")
    if duplicates(gate_ids):
        errors.append(f"duplicate gate IDs: {duplicates(gate_ids)}")
    invalid_gate_statuses = sorted({row["status"] for row in gates} - GATE_STATUSES)
    if invalid_gate_statuses:
        errors.append(f"invalid gate statuses: {invalid_gate_statuses}")
    future_gate_passes = [
        row["gate_id"]
        for row in gates
        if row["gate_id"] not in APPROVED_PASSED_GATES and row["status"] != "NOT_STARTED"
    ]
    if future_gate_passes:
        errors.append(f"future gates falsely advanced: {future_gate_passes}")
    g0 = next((row for row in gates if row["gate_id"] == "G0"), None)
    if not g0 or g0["status"] != "PASS" or not g0["evidence_path"]:
        errors.append("G0 must be PASS with evidence")
    for row in gates:
        expected = CANONICAL_GATE_TASK_OWNERS.get(row["gate_id"])
        if expected != row["prerequisite_tasks"]:
            semantic_task_mapping_errors.append(
                f"{row['gate_id']}.prerequisite_tasks: expected {expected!r}, "
                f"got {row['prerequisite_tasks']!r}"
            )

    if duplicates(requirement_ids):
        errors.append(f"duplicate requirement IDs: {duplicates(requirement_ids)}")
    missing_core = sorted({f"R{number:02d}" for number in range(1, 29)} - requirement_set)
    if missing_core:
        errors.append(f"missing core requirements: {missing_core}")
    invalid_requirement_statuses = sorted(
        {row["status"] for row in requirements} - REQUIREMENT_STATUSES
    )
    if invalid_requirement_statuses:
        errors.append(f"invalid requirement statuses: {invalid_requirement_statuses}")
    invalid_requirement_types = sorted(
        {row["requirement_type"] for row in requirements} - REQUIREMENT_TYPES
    )
    if invalid_requirement_types:
        errors.append(f"invalid requirement types: {invalid_requirement_types}")

    core_requirement_map = dict(task_snapshot["requirement_task_map"])
    core_requirement_map["R27"] = ";".join(f"T{number:03d}" for number in range(1, 37))
    for requirement_id, expected_tasks in core_requirement_map.items():
        row = next(
            (item for item in requirements if item["requirement_id"] == requirement_id),
            None,
        )
        if row is not None and row["implementation_tasks"] != expected_tasks:
            semantic_task_mapping_errors.append(
                f"{requirement_id}.implementation_tasks: expected {expected_tasks!r}, "
                f"got {row['implementation_tasks']!r}"
            )

    mandatory = [row for row in requirements if row["mandatory"].upper() == "TRUE"]
    unmapped: list[str] = []
    invalid_task_refs: list[str] = []
    invalid_gate_refs: list[str] = []
    required_fields = (
        "source_document",
        "source_version",
        "source_section",
        "source_page_or_locator",
        "implementation_tasks",
        "planned_files_or_modules",
        "validation_method",
        "acceptance_criterion",
        "gate_ids",
        "evidence_artifacts",
        "change_class",
    )
    for row in mandatory:
        missing = [field for field in required_fields if not row[field].strip()]
        if missing:
            unmapped.append(f"{row['requirement_id']}:{','.join(missing)}")
        for reference in split_refs(row["implementation_tasks"]):
            if reference not in task_set:
                invalid_task_refs.append(f"{row['requirement_id']}->{reference}")
        for reference in split_refs(row["gate_ids"]):
            if reference not in gate_set:
                invalid_gate_refs.append(f"{row['requirement_id']}->{reference}")
        if row["source_document"] == SPEC_FILENAME and row["source_version"] != "2.2":
            errors.append(f"{row['requirement_id']} silently differs from source version 2.2")
        elif row["source_document"] == PLAN_FILENAME and row["source_version"] != "1.0":
            errors.append(f"{row['requirement_id']} has unexpected solo-plan version")
        elif row["source_document"] not in {SPEC_FILENAME, PLAN_FILENAME}:
            errors.append(f"{row['requirement_id']} uses unknown source document")
        if row["status"] == "VERIFIED" and not Path(root / row["evidence_artifacts"]).exists():
            errors.append(f"{row['requirement_id']} is VERIFIED without local evidence")

    if unmapped:
        errors.append(f"mandatory unmapped requirements: {unmapped}")
    if invalid_task_refs:
        errors.append(f"invalid requirement task references: {invalid_task_refs}")
    if invalid_gate_refs:
        errors.append(f"invalid requirement gate references: {invalid_gate_refs}")

    missing_claims = sorted(CLAIM_BOUNDARY_IDS - requirement_set)
    if missing_claims:
        errors.append(f"missing claim boundaries: {missing_claims}")
    for claim_id in sorted(CLAIM_BOUNDARY_IDS & requirement_set):
        row = next(item for item in requirements if item["requirement_id"] == claim_id)
        if row["requirement_type"] != "CLAIM_BOUNDARY" or not row["claim_boundary"]:
            errors.append(f"{claim_id} is not an explicit claim boundary")
    claim_markers = {
        "CB01": ("research prototype", "not diagnostic"),
        "CB02": ("wearable", "disease ground truth"),
        "CB03": ("simulated", "real hospitals"),
        "CB04": ("secagg+", "not complete privacy"),
        "CB05": ("not learned", "arrhythmia prediction"),
        "CB06": ("source-domain", "not wearable-domain"),
    }
    for claim_id, markers in claim_markers.items():
        row = next((item for item in requirements if item["requirement_id"] == claim_id), {})
        claim_text = " ".join(str(value).casefold() for value in row.values())
        if not all(marker in claim_text for marker in markers):
            errors.append(f"{claim_id} does not preserve its required claim semantics")

    gate_task_refs = {
        reference
        for row in gates
        for field in ("prerequisite_tasks", "blocks_tasks")
        for reference in split_refs(row[field])
        if reference.startswith("T")
    }
    gate_req_refs = {
        reference for row in gates for reference in split_refs(row["required_requirements"])
    }
    bad_gate_tasks = sorted(gate_task_refs - task_set)
    bad_gate_requirements = sorted(gate_req_refs - requirement_set)
    if bad_gate_tasks:
        errors.append(f"invalid gate task references: {bad_gate_tasks}")
    if bad_gate_requirements:
        errors.append(f"invalid gate requirement references: {bad_gate_requirements}")

    evidence_task_refs = {
        reference for row in evidence for reference in split_refs(row["task_ids"])
    }
    evidence_req_refs = {
        reference for row in evidence for reference in split_refs(row["requirement_ids"])
    }
    evidence_gate_refs = {
        reference for row in evidence for reference in split_refs(row["gate_ids"])
    }
    if evidence_task_refs - task_set:
        errors.append(f"invalid evidence task references: {sorted(evidence_task_refs - task_set)}")
    if evidence_req_refs - requirement_set:
        invalid = sorted(evidence_req_refs - requirement_set)
        errors.append(f"invalid evidence requirement references: {invalid}")
    if evidence_gate_refs - gate_set:
        errors.append(f"invalid evidence gate references: {sorted(evidence_gate_refs - gate_set)}")
    for row in evidence:
        expected = CANONICAL_EVIDENCE_TASK_OWNERS.get(row["evidence_id"])
        if expected != row["task_ids"]:
            semantic_task_mapping_errors.append(
                f"{row['evidence_id']}.task_ids: expected {expected!r}, got {row['task_ids']!r}"
            )

    invalid_freeze_task_refs: list[str] = []
    invalid_freeze_experiment_refs: list[str] = []
    invalid_freeze_gate_refs: list[str] = []
    expected_experiments = {f"E{number:02d}" for number in range(1, 17)}
    for row in freezes:
        if row["freeze_gate"] not in gate_set:
            invalid_freeze_gate_refs.append(f"{row['freeze_id']}->{row['freeze_gate']}")
        for reference in expand_refs(row["invalidated_tasks_if_changed"]):
            if reference not in task_set:
                invalid_freeze_task_refs.append(f"{row['freeze_id']}->{reference}")
        for reference in expand_refs(row["invalidated_experiments_if_changed"]):
            if reference not in expected_experiments:
                invalid_freeze_experiment_refs.append(f"{row['freeze_id']}->{reference}")
    if invalid_freeze_task_refs:
        errors.append(f"invalid freeze task references: {invalid_freeze_task_refs}")
    if invalid_freeze_experiment_refs:
        errors.append(f"invalid freeze experiment references: {invalid_freeze_experiment_refs}")
    if invalid_freeze_gate_refs:
        errors.append(f"invalid freeze gate references: {invalid_freeze_gate_refs}")

    invalid_control_gates = [
        f"{row['work_item']}->{reference}"
        for row in controls
        for reference in split_refs(row["required_gate"])
        if reference not in gate_set
    ]
    if invalid_control_gates:
        errors.append(f"invalid do-not-start gate references: {invalid_control_gates}")

    requirement_task_refs = {
        reference for row in requirements for reference in split_refs(row["implementation_tasks"])
    }
    covered_tasks = requirement_task_refs | gate_task_refs | evidence_task_refs
    orphan_tasks = sorted(task_set - covered_tasks)
    orphan_classifications = {
        task_id: (
            "VALID_RELEASE_TASK"
            if task_id >= "T033"
            else "VALID_INFRASTRUCTURE_TASK"
            if task_id <= "T003"
            else "POSSIBLE_ORPHAN"
        )
        for task_id in orphan_tasks
    }

    experiment_ids = [row["experiment_id"] for row in experiments]
    if set(experiment_ids) != expected_experiments:
        errors.append("experiment registry must preserve E01-E16 exactly")
    if duplicates(experiment_ids):
        errors.append(f"duplicate experiment IDs: {duplicates(experiment_ids)}")
    for row in experiments:
        if row["status"] != "PLANNED":
            errors.append(f"future experiment {row['experiment_id']} is not PLANNED")
        if row["implementing_task"] not in task_set:
            errors.append(f"{row['experiment_id']} has invalid implementing task")
        expected = CANONICAL_EXPERIMENT_TASK_OWNERS.get(row["experiment_id"])
        if expected != row["implementing_task"]:
            semantic_task_mapping_errors.append(
                f"{row['experiment_id']}.implementing_task: expected {expected!r}, "
                f"got {row['implementing_task']!r}"
            )
        for reference in split_refs(row["prerequisite_gates"]):
            if reference not in gate_set:
                errors.append(f"{row['experiment_id']} has invalid gate {reference}")

    if len(freezes) < 15:
        errors.append("freeze registry lacks mandatory freeze points")
    for row in freezes:
        expected = CANONICAL_FREEZE_INVALIDATIONS.get(row["freeze_id"])
        if expected != row["invalidated_tasks_if_changed"]:
            semantic_task_mapping_errors.append(
                f"{row['freeze_id']}.invalidated_tasks_if_changed: expected {expected!r}, "
                f"got {row['invalidated_tasks_if_changed']!r}"
            )
    premature_freezes = [
        row["freeze_id"]
        for row in freezes
        if row["freeze_id"] not in APPROVED_FROZEN_ARTIFACTS and row["current_status"] == "FROZEN"
    ]
    if premature_freezes:
        errors.append(f"future freezes falsely marked FROZEN: {premature_freezes}")
    if len(controls) < 12 or not any(row["status"] == "PERMANENTLY_PROHIBITED" for row in controls):
        errors.append("do-not-start registry lacks required controls/prohibition")

    no_coverage_placeholders = re.compile(r"\b(?:TODO|TBD|implement eventually)\b", re.I)
    placeholder_rows = [
        row["requirement_id"]
        for row in mandatory
        if any(no_coverage_placeholders.search(row[field] or "") for field in required_fields)
    ]
    if placeholder_rows:
        errors.append(f"coverage placeholders found: {placeholder_rows}")
    if semantic_task_mapping_errors:
        errors.append(f"semantic task mapping errors: {semantic_task_mapping_errors}")

    return {
        "task_count": len(tasks),
        "gate_count": len(gates),
        "requirement_count": len(requirements),
        "mandatory_requirement_count": len(mandatory),
        "optional_out_of_scope_requirement_count": len(requirements) - len(mandatory),
        "mapped_requirement_count": len(mandatory) - len(unmapped),
        "unmapped_requirement_count": len(unmapped),
        "invalid_task_reference_count": (
            len(invalid_task_refs) + len(bad_gate_tasks) + len(invalid_freeze_task_refs)
        ),
        "invalid_gate_reference_count": (
            len(invalid_gate_refs)
            + len(evidence_gate_refs - gate_set)
            + len(invalid_freeze_gate_refs)
            + len(invalid_control_gates)
        ),
        "orphan_task_count": len(orphan_tasks),
        "orphan_tasks": orphan_tasks,
        "orphan_classifications": orphan_classifications,
        "semantic_task_mapping_error_count": len(semantic_task_mapping_errors),
        "semantic_task_mapping_errors": semantic_task_mapping_errors,
        "remaining_derived_task_definition_count": len(remaining_derived),
        "experiment_count": len(experiments),
        "freeze_count": len(freezes),
        "do_not_start_count": len(controls),
        "evidence_count": len(evidence),
        "source_version": "2.2",
        "errors": errors,
        "status": "PASS" if not errors else "FAIL",
    }
