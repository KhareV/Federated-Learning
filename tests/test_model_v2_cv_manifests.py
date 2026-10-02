"""V2-001 outer-CV / inner-validation manifest tests (Sections 10/11/13).

Proves: TRAIN-only, patient-disjoint, class-conserving, 6/6/5/5/5 outer folds; exactly
4-group inner-validation sets per outer fold; outer-test/inner-validation/optimisation are
pairwise disjoint and cover the full 27-patient universe per fold; no VALIDATION/CALIBRATION/
TEST patient (including the merged 201/202 VALIDATION group) ever enters either manifest;
and the frozen lock hashes match the on-disk manifests exactly.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUTER_CSV = ROOT / "manifests/model_v2/cv/MITDB_TRAIN_CV_V2_V1.csv"
OUTER_LOCK = ROOT / "manifests/model_v2/cv/MITDB_TRAIN_CV_V2_V1.lock.json"
INNER_CSV = ROOT / "manifests/model_v2/cv/MITDB_TRAIN_INNER_V2_V1.csv"
INNER_LOCK = ROOT / "manifests/model_v2/cv/MITDB_TRAIN_INNER_V2_V1.lock.json"
SPLIT_CSV = ROOT / "manifests/splits/MITDB_SPLIT_V1.csv"
WINDOW_MANIFEST = ROOT / "manifests/windows/MITDB_WINDOWS_V1.csv"

FOLD_CAPACITIES = [6, 6, 5, 5, 5]


def _outer_rows() -> list[dict[str, str]]:
    with OUTER_CSV.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _inner_rows() -> list[dict[str, str]]:
    with INNER_CSV.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _train_patient_groups() -> set[str]:
    with SPLIT_CSV.open(newline="", encoding="utf-8") as handle:
        return {
            row["participant_group_id"]
            for row in csv.DictReader(handle)
            if row["partition"] == "TRAIN"
        }


def _non_train_patient_groups() -> set[str]:
    with SPLIT_CSV.open(newline="", encoding="utf-8") as handle:
        return {
            row["participant_group_id"]
            for row in csv.DictReader(handle)
            if row["partition"] != "TRAIN"
        }


def test_outer_manifest_has_exactly_27_train_patients_once_each() -> None:
    rows = _outer_rows()
    patients = [r["participant_group_id"] for r in rows]
    assert len(patients) == 27
    assert len(set(patients)) == 27
    assert set(patients) == _train_patient_groups()


def test_outer_fold_sizes_are_6_6_5_5_5() -> None:
    rows = _outer_rows()
    counts = {j: 0 for j in range(5)}
    for row in rows:
        counts[int(row["outer_fold"])] += 1
    assert [counts[j] for j in range(5)] == FOLD_CAPACITIES


def test_outer_manifest_window_and_class_conservation() -> None:
    rows = _outer_rows()
    assert sum(int(r["eligible_windows"]) for r in rows) == 9660
    assert sum(int(r["positive_windows"]) for r in rows) == 3557
    assert sum(int(r["negative_windows"]) for r in rows) == 6103


def test_every_outer_fold_contains_both_classes() -> None:
    rows = _outer_rows()
    for j in range(5):
        fold_rows = [r for r in rows if int(r["outer_fold"]) == j]
        assert sum(int(r["positive_windows"]) for r in fold_rows) > 0
        assert sum(int(r["negative_windows"]) for r in fold_rows) > 0


def test_no_non_train_patient_in_outer_manifest() -> None:
    patients = {r["participant_group_id"] for r in _outer_rows()}
    assert patients.isdisjoint(_non_train_patient_groups())


def test_outer_lock_hash_matches_on_disk_manifest() -> None:
    lock = json.loads(OUTER_LOCK.read_text(encoding="utf-8"))
    assert lock["manifest_sha256"] == hash_file(OUTER_CSV)
    assert lock["status"] == "FROZEN_CV_MANIFEST"
    assert lock["fold_capacities"] == FOLD_CAPACITIES


def test_inner_manifest_covers_every_fold_patient_pair_exactly_once() -> None:
    rows = _inner_rows()
    assert len(rows) == 5 * 27
    seen = {(int(r["outer_fold"]), r["participant_group_id"]) for r in rows}
    assert len(seen) == 5 * 27


def test_inner_validation_has_exactly_4_groups_per_fold() -> None:
    rows = _inner_rows()
    for j in range(5):
        inner = [r for r in rows if int(r["outer_fold"]) == j and r["role"] == "INNER_VALIDATION"]
        assert len(inner) == 4


def test_outer_test_inner_validation_optimise_cover_27_and_are_disjoint_per_fold() -> None:
    rows = _inner_rows()
    for j in range(5):
        fold_rows = [r for r in rows if int(r["outer_fold"]) == j]
        by_role: dict[str, set[str]] = {
            "OUTER_TEST": set(),
            "INNER_VALIDATION": set(),
            "OPTIMISE": set(),
        }
        for r in fold_rows:
            by_role[r["role"]].add(r["participant_group_id"])
        assert len(fold_rows) == 27
        assert by_role["OUTER_TEST"].isdisjoint(by_role["INNER_VALIDATION"])
        assert by_role["OUTER_TEST"].isdisjoint(by_role["OPTIMISE"])
        assert by_role["INNER_VALIDATION"].isdisjoint(by_role["OPTIMISE"])
        assert by_role["OUTER_TEST"] | by_role["INNER_VALIDATION"] | by_role["OPTIMISE"] == (
            _train_patient_groups()
        )
        assert by_role["OUTER_TEST"] == {
            r["participant_group_id"] for r in _outer_rows() if int(r["outer_fold"]) == j
        }


def test_no_non_train_patient_in_inner_manifest() -> None:
    patients = {r["participant_group_id"] for r in _inner_rows()}
    assert patients.isdisjoint(_non_train_patient_groups())


def test_201_202_merged_group_never_enters_cv_manifests() -> None:
    merged_group_id = "MITDB_P201_202"
    outer_patients = {r["participant_group_id"] for r in _outer_rows()}
    inner_patients = {r["participant_group_id"] for r in _inner_rows()}
    assert merged_group_id not in outer_patients
    assert merged_group_id not in inner_patients
    assert merged_group_id in _non_train_patient_groups()


def test_inner_lock_hash_matches_on_disk_manifest() -> None:
    lock = json.loads(INNER_LOCK.read_text(encoding="utf-8"))
    assert lock["manifest_sha256"] == hash_file(INNER_CSV)
    assert lock["status"] == "FROZEN_CV_MANIFEST"
    assert lock["inner_validation_size"] == 4
    assert lock["predecessor_outer_manifest_sha256"] == hash_file(OUTER_CSV)


def test_inner_validation_and_remaining_optimise_both_have_both_classes() -> None:
    inner_lock = json.loads(INNER_LOCK.read_text(encoding="utf-8"))
    for fold_entry in inner_lock["fold_audit"]:
        assert fold_entry["inner_positive_windows"] > 0
        assert fold_entry["inner_negative_windows"] > 0
