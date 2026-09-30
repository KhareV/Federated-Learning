"""Deterministic whole-patient IID client construction for T025."""

from __future__ import annotations

import csv
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CLIENT_MANIFEST_ID = "CLIENTS_IID_V1"
ASSIGNMENT_METHOD_ID = "BALANCED_WHOLE_PATIENT_IID_V1"
ASSIGNMENT_SEED_ID = "DETERMINISTIC_NO_RANDOM_RESTART_V1"
SITE_IDS = tuple(f"SITE_{index:02d}" for index in range(8))


@dataclass(frozen=True)
class PatientSummary:
    participant_group_id: str
    record_ids: tuple[str, ...]
    windows: int
    positives: int
    negatives: int


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def train_patient_summaries(window_manifest: Path) -> list[PatientSummary]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in read_csv(window_manifest):
        if row["partition"] == "TRAIN" and row["core_eligible"].upper() == "TRUE":
            grouped[row["participant_group_id"]].append(row)
    summaries: list[PatientSummary] = []
    for group_id, rows in grouped.items():
        labels = [int(row["label"]) for row in rows]
        if not set(labels).issubset({0, 1}):
            raise ValueError(f"non-binary TRAIN label for {group_id}")
        positives = sum(labels)
        summaries.append(
            PatientSummary(
                participant_group_id=group_id,
                record_ids=tuple(sorted({row["record_id"] for row in rows})),
                windows=len(rows),
                positives=positives,
                negatives=len(rows) - positives,
            )
        )
    return sorted(summaries, key=lambda item: item.participant_group_id)


def balanced_capacities(patient_count: int) -> dict[str, int]:
    base, remainder = divmod(patient_count, len(SITE_IDS))
    return {
        site: base + (1 if index < remainder else 0)
        for index, site in enumerate(SITE_IDS)
    }


def assignment_objective(
    assignment: dict[str, list[PatientSummary]],
    *,
    total_windows: int,
    total_positives: int,
) -> float:
    target = total_windows / len(SITE_IDS)
    global_rate = total_positives / total_windows
    result = 0.0
    for site in SITE_IDS:
        patients = assignment[site]
        windows = sum(patient.windows for patient in patients)
        positives = sum(patient.positives for patient in patients)
        quantity_error = (windows - target) / target
        site_rate = positives / windows if windows else global_rate
        label_error = site_rate - global_rate
        result += quantity_error**2 + label_error**2
    return result


def build_assignment(
    patients: list[PatientSummary],
) -> tuple[dict[str, list[PatientSummary]], dict[str, Any]]:
    if len(patients) < len(SITE_IDS):
        raise ValueError("fewer TRAIN patients than simulated sites")
    if len({patient.participant_group_id for patient in patients}) != len(patients):
        raise ValueError("duplicate TRAIN participant group")
    capacities = balanced_capacities(len(patients))
    total_windows = sum(patient.windows for patient in patients)
    total_positives = sum(patient.positives for patient in patients)
    assignment = {site: [] for site in SITE_IDS}
    ordered = sorted(patients, key=lambda item: (-item.windows, item.participant_group_id))
    for patient in ordered:
        candidates: list[tuple[float, str]] = []
        for site in SITE_IDS:
            if len(assignment[site]) >= capacities[site]:
                continue
            assignment[site].append(patient)
            objective = assignment_objective(
                assignment, total_windows=total_windows, total_positives=total_positives
            )
            assignment[site].pop()
            candidates.append((objective, site))
        if not candidates:
            raise RuntimeError("IID assignment capacity exhausted")
        _, selected = min(candidates, key=lambda item: (item[0], item[1]))
        assignment[selected].append(patient)
    initial_objective = assignment_objective(
        assignment, total_windows=total_windows, total_positives=total_positives
    )
    swaps = 0
    tolerance = 1e-15
    while True:
        current = assignment_objective(
            assignment, total_windows=total_windows, total_positives=total_positives
        )
        candidates: list[tuple[float, str, str, str, str]] = []
        for left_index, site_a in enumerate(SITE_IDS):
            for site_b in SITE_IDS[left_index + 1 :]:
                for patient_a in sorted(
                    assignment[site_a], key=lambda item: item.participant_group_id
                ):
                    for patient_b in sorted(
                        assignment[site_b], key=lambda item: item.participant_group_id
                    ):
                        index_a = assignment[site_a].index(patient_a)
                        index_b = assignment[site_b].index(patient_b)
                        assignment[site_a][index_a], assignment[site_b][index_b] = (
                            patient_b,
                            patient_a,
                        )
                        objective = assignment_objective(
                            assignment,
                            total_windows=total_windows,
                            total_positives=total_positives,
                        )
                        assignment[site_a][index_a], assignment[site_b][index_b] = (
                            patient_a,
                            patient_b,
                        )
                        if objective < current - tolerance:
                            candidates.append(
                                (
                                    objective,
                                    site_a,
                                    patient_a.participant_group_id,
                                    site_b,
                                    patient_b.participant_group_id,
                                )
                            )
        if not candidates:
            break
        best = min(candidates)
        _, site_a, patient_a_id, site_b, patient_b_id = best
        patient_a = next(
            item for item in assignment[site_a] if item.participant_group_id == patient_a_id
        )
        patient_b = next(
            item for item in assignment[site_b] if item.participant_group_id == patient_b_id
        )
        index_a = assignment[site_a].index(patient_a)
        index_b = assignment[site_b].index(patient_b)
        assignment[site_a][index_a], assignment[site_b][index_b] = patient_b, patient_a
        swaps += 1
    for site in SITE_IDS:
        assignment[site].sort(key=lambda item: item.participant_group_id)
    final_objective = assignment_objective(
        assignment, total_windows=total_windows, total_positives=total_positives
    )
    return assignment, {
        "capacities": capacities,
        "initial_objective": initial_objective,
        "final_objective": final_objective,
        "swap_count": swaps,
        "total_windows": total_windows,
        "total_positives": total_positives,
        "total_negatives": total_windows - total_positives,
    }


def manifest_rows(assignment: dict[str, list[PatientSummary]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for site in SITE_IDS:
        for patient in assignment[site]:
            rows.append(
                {
                    "client_manifest_id": CLIENT_MANIFEST_ID,
                    "site_id": site,
                    "participant_group_id": patient.participant_group_id,
                    "record_ids": ";".join(patient.record_ids),
                    "partition": "TRAIN",
                    "eligible_window_count": str(patient.windows),
                    "positive_window_count": str(patient.positives),
                    "negative_window_count": str(patient.negatives),
                    "positive_rate": format(patient.positives / patient.windows, ".17g"),
                    "assignment_method": ASSIGNMENT_METHOD_ID,
                    "assignment_seed_version": ASSIGNMENT_SEED_ID,
                }
            )
    return rows


def write_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def coefficient_of_variation(values: list[int]) -> float:
    mean = sum(values) / len(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / len(values)) / mean

