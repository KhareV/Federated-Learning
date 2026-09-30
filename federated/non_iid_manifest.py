"""Deterministic whole-patient non-IID manifests for T026."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from federated.client_manifest import SITE_IDS, PatientSummary, train_patient_summaries

LABEL_CAPACITIES = (4, 4, 4, 3, 3, 3, 3, 3)
QUANTITY_CAPACITIES = (2, 2, 2, 3, 3, 4, 5, 6)
QUANTITY_RATIOS = (1, 1, 1, 2, 2, 3, 3, 4)
MANIFEST_IDS = {
    "label": "NONIID_LABEL_V1",
    "quantity": "NONIID_QUANTITY_V1",
    "feature": "NONIID_FEATURE_V1",
    "combined": "NONIID_COMBINED_V1",
}
Mode = Literal["label", "quantity", "combined"]


@dataclass(frozen=True)
class Objective:
    primary: float
    secondary: float


def constrained_quantity_allocation(total: int = 27) -> tuple[int, ...]:
    """Return the least-squares integer ratio normalization with >=2 patients/site."""
    targets = tuple(total * ratio / sum(QUANTITY_RATIOS) for ratio in QUANTITY_RATIOS)
    best: tuple[float, tuple[int, ...]] | None = None

    def visit(prefix: tuple[int, ...], remaining: int) -> None:
        nonlocal best
        slots = len(SITE_IDS) - len(prefix)
        if slots == 1:
            if remaining < 2:
                return
            candidate = (*prefix, remaining)
            score = sum(
                (value - target) ** 2 for value, target in zip(candidate, targets, strict=True)
            )
            item = (score, candidate)
            if best is None or item < best:
                best = item
            return
        for value in range(2, remaining - 2 * (slots - 1) + 1):
            visit((*prefix, value), remaining - value)

    visit((), total)
    if best is None:
        raise ValueError("no feasible quantity allocation")
    return best[1]


def label_variance(assignment: dict[str, list[PatientSummary]]) -> float:
    patients = [patient for site in SITE_IDS for patient in assignment[site]]
    global_rate = sum(item.positives for item in patients) / sum(item.windows for item in patients)
    return sum(
        (
            sum(item.positives for item in assignment[site])
            / sum(item.windows for item in assignment[site])
            - global_rate
        )
        ** 2
        for site in SITE_IDS
    )


def _quantity_error(
    assignment: dict[str, list[PatientSummary]], targets: tuple[float, ...]
) -> float:
    return sum(
        ((sum(item.windows for item in assignment[site]) - targets[index]) / targets[index]) ** 2
        for index, site in enumerate(SITE_IDS)
    )


def _window_fraction_error(assignment: dict[str, list[PatientSummary]]) -> float:
    total = sum(item.windows for site in SITE_IDS for item in assignment[site])
    return sum(
        (sum(item.windows for item in assignment[site]) / total - QUANTITY_RATIOS[index] / 17) ** 2
        for index, site in enumerate(SITE_IDS)
    )


def objective(
    assignment: dict[str, list[PatientSummary]], mode: Mode, iid_targets: tuple[float, ...]
) -> Objective:
    variance = label_variance(assignment)
    if mode == "quantity":
        return Objective(variance, _window_fraction_error(assignment))
    secondary = (
        _quantity_error(assignment, iid_targets)
        if mode == "label"
        else _window_fraction_error(assignment)
    )
    return Objective(variance, secondary)


def _better(candidate: Objective, current: Objective, mode: Mode) -> bool:
    tolerance = 1e-12
    if mode in {"label", "combined"}:
        if candidate.primary > current.primary + tolerance:
            return True
        return (
            abs(candidate.primary - current.primary) <= tolerance
            and candidate.secondary < current.secondary - tolerance
        )
    if candidate.primary < current.primary - tolerance:
        return True
    return (
        abs(candidate.primary - current.primary) <= tolerance
        and candidate.secondary < current.secondary - tolerance
    )


def build_assignment(
    patients: list[PatientSummary], mode: Mode, iid_window_targets: dict[str, int]
) -> tuple[dict[str, list[PatientSummary]], dict[str, Any]]:
    capacities = LABEL_CAPACITIES if mode == "label" else constrained_quantity_allocation()
    if len(patients) != sum(capacities):
        raise ValueError("frozen TRAIN patient count does not match capacities")
    ordered = sorted(
        patients,
        key=lambda item: (item.positives / item.windows, item.participant_group_id),
    )
    assignment = {site: [] for site in SITE_IDS}
    if mode in {"label", "combined"}:
        cursor = 0
        for site, capacity in zip(SITE_IDS, capacities, strict=True):
            assignment[site] = ordered[cursor : cursor + capacity]
            cursor += capacity
    else:
        total_windows = sum(item.windows for item in patients)
        global_rate = sum(item.positives for item in patients) / total_windows
        greedy = sorted(patients, key=lambda item: (-item.windows, item.participant_group_id))
        for patient in greedy:
            candidates = []
            for index, site in enumerate(SITE_IDS):
                if len(assignment[site]) >= capacities[index]:
                    continue
                assignment[site].append(patient)
                windows = sum(item.windows for item in assignment[site])
                positives = sum(item.positives for item in assignment[site])
                rate_error = (positives / windows - global_rate) ** 2
                fraction_error = (windows / total_windows - QUANTITY_RATIOS[index] / 17) ** 2
                assignment[site].pop()
                candidates.append((rate_error, fraction_error, site))
            assignment[min(candidates)[2]].append(patient)
    targets = tuple(float(iid_window_targets[site]) for site in SITE_IDS)
    initial = objective(assignment, mode, targets)
    swaps = 0
    while True:
        current = objective(assignment, mode, targets)
        candidates: list[tuple[float, float, str, str, str, str]] = []
        for left, site_a in enumerate(SITE_IDS):
            for site_b in SITE_IDS[left + 1 :]:
                for patient_a in sorted(
                    assignment[site_a], key=lambda item: item.participant_group_id
                ):
                    for patient_b in sorted(
                        assignment[site_b], key=lambda item: item.participant_group_id
                    ):
                        ia, ib = (
                            assignment[site_a].index(patient_a),
                            assignment[site_b].index(patient_b),
                        )
                        assignment[site_a][ia], assignment[site_b][ib] = patient_b, patient_a
                        candidate = objective(assignment, mode, targets)
                        assignment[site_a][ia], assignment[site_b][ib] = patient_a, patient_b
                        if _better(candidate, current, mode):
                            primary_key = (
                                -candidate.primary if mode != "quantity" else candidate.primary
                            )
                            candidates.append(
                                (
                                    primary_key,
                                    candidate.secondary,
                                    site_a,
                                    patient_a.participant_group_id,
                                    site_b,
                                    patient_b.participant_group_id,
                                )
                            )
        if not candidates:
            break
        _, _, site_a, patient_a_id, site_b, patient_b_id = min(candidates)
        ia = next(
            i
            for i, item in enumerate(assignment[site_a])
            if item.participant_group_id == patient_a_id
        )
        ib = next(
            i
            for i, item in enumerate(assignment[site_b])
            if item.participant_group_id == patient_b_id
        )
        assignment[site_a][ia], assignment[site_b][ib] = (
            assignment[site_b][ib],
            assignment[site_a][ia],
        )
        swaps += 1
    for site in SITE_IDS:
        assignment[site].sort(key=lambda item: item.participant_group_id)
    final = objective(assignment, mode, targets)
    return assignment, {
        "capacities": dict(zip(SITE_IDS, capacities, strict=True)),
        "initial_label_objective": initial.primary,
        "final_label_objective": final.primary,
        "secondary_objective": final.secondary,
        "swap_count": swaps,
    }


def rows_for(assignment: dict[str, list[PatientSummary]], mode: str) -> list[dict[str, str]]:
    result = []
    for site in SITE_IDS:
        for patient in assignment[site]:
            result.append(
                {
                    "client_manifest_id": MANIFEST_IDS[mode],
                    "site_id": site,
                    "participant_group_id": patient.participant_group_id,
                    "record_ids": ";".join(patient.record_ids),
                    "partition": "TRAIN",
                    "eligible_window_count": str(patient.windows),
                    "positive_window_count": str(patient.positives),
                    "negative_window_count": str(patient.negatives),
                    "positive_rate": format(patient.positives / patient.windows, ".17g"),
                    "assignment_method": f"{MANIFEST_IDS[mode]}_DETERMINISTIC_OBJECTIVE",
                    "assignment_seed_version": "DETERMINISTIC_NO_RANDOM_RESTART_V1",
                }
            )
    return result


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def iid_targets(path: Path) -> dict[str, int]:
    totals = {site: 0 for site in SITE_IDS}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            totals[row["site_id"]] += int(row["eligible_window_count"])
    return totals


def build_all(root: Path) -> dict[str, Any]:
    patients = train_patient_summaries(root / "manifests/windows/MITDB_WINDOWS_V1.csv")
    targets = iid_targets(root / "manifests/clients/CLIENTS_IID_V1.csv")
    metadata: dict[str, Any] = {}
    assignments: dict[str, dict[str, list[PatientSummary]]] = {}
    for mode in ("label", "quantity", "combined"):
        assignments[mode], metadata[mode] = build_assignment(patients, mode, targets)
    iid_by_group = {item.participant_group_id: item for item in patients}
    feature = {site: [] for site in SITE_IDS}
    with (root / "manifests/clients/CLIENTS_IID_V1.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        for row in csv.DictReader(handle):
            feature[row["site_id"]].append(iid_by_group[row["participant_group_id"]])
    assignments["feature"] = feature
    metadata["feature"] = {"mapping_source": "CLIENTS_IID_V1", "swap_count": 0}
    for mode, filename in {
        "label": "NONIID_LABEL_V1.csv",
        "quantity": "NONIID_QUANTITY_V1.csv",
        "feature": "NONIID_FEATURE_V1.csv",
        "combined": "NONIID_COMBINED_V1.csv",
    }.items():
        write_rows(root / "manifests/clients" / filename, rows_for(assignments[mode], mode))
    return {"assignments": assignments, "metadata": metadata}
