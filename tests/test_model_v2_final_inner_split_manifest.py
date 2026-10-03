"""C-V2-PRE006-AUTHORITY-REPAIR: acceptance tests for the real, frozen
MITDB_TRAIN_FINAL_INNER_V2_V1 manifest. Read-only against the committed CSV/lock except for
one subprocess regeneration to prove byte-identical determinism.
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_CSV = ROOT / "manifests/model_v2/cv/MITDB_TRAIN_FINAL_INNER_V2_V1.csv"
MANIFEST_LOCK = ROOT / "manifests/model_v2/cv/MITDB_TRAIN_FINAL_INNER_V2_V1.lock.json"
OUTER_CV_CSV = ROOT / "manifests/model_v2/cv/MITDB_TRAIN_CV_V2_V1.csv"
OUTER_INNER_CSV = ROOT / "manifests/model_v2/cv/MITDB_TRAIN_INNER_V2_V1.csv"
WINDOW_MANIFEST = ROOT / "manifests/windows/MITDB_WINDOWS_V1.csv"


def _rows() -> list[dict[str, str]]:
    with MANIFEST_CSV.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_manifest_has_exactly_27_groups_each_once() -> None:
    rows = _rows()
    ids = [r["participant_group_id"] for r in rows]
    assert len(ids) == 27
    assert len(set(ids)) == 27


def test_roles_disjoint_and_union_is_full_train_population() -> None:
    rows = _rows()
    final_inner = {r["participant_group_id"] for r in rows if r["role"] == "FINAL_INNER_VALIDATION"}
    optimise = {r["participant_group_id"] for r in rows if r["role"] == "OPTIMISE"}
    assert final_inner.isdisjoint(optimise)
    assert len(final_inner) == 5
    assert len(optimise) == 22

    with OUTER_CV_CSV.open(newline="", encoding="utf-8") as handle:
        outer_population = {row["participant_group_id"] for row in csv.DictReader(handle)}
    assert final_inner | optimise == outer_population


def test_no_outer_test_role_present() -> None:
    rows = _rows()
    roles = {r["role"] for r in rows}
    assert roles == {"FINAL_INNER_VALIDATION", "OPTIMISE"}
    assert "OUTER_TEST" not in roles


def test_no_held_out_or_external_group_enters_manifest() -> None:
    manifest_groups = {r["participant_group_id"] for r in _rows()}
    partitions: dict[str, set[str]] = {}
    with WINDOW_MANIFEST.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            partitions.setdefault(row["participant_group_id"], set()).add(row["partition"])

    for pg in manifest_groups:
        assert partitions.get(pg) == {"TRAIN"}, f"{pg} is not pure-TRAIN: {partitions.get(pg)}"


def test_window_and_class_counts_exactly_conserved() -> None:
    aggregates: dict[str, dict[str, int]] = {}
    with WINDOW_MANIFEST.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["partition"] != "TRAIN" or row["core_eligible"] != "TRUE":
                continue
            pg = row["participant_group_id"]
            entry = aggregates.setdefault(pg, {"eligible": 0, "positive": 0, "negative": 0})
            entry["eligible"] += 1
            if int(row["label"]) == 1:
                entry["positive"] += 1
            else:
                entry["negative"] += 1

    rows = _rows()
    total_eligible = sum(aggregates[r["participant_group_id"]]["eligible"] for r in rows)
    total_positive = sum(aggregates[r["participant_group_id"]]["positive"] for r in rows)
    total_negative = sum(aggregates[r["participant_group_id"]]["negative"] for r in rows)

    assert total_eligible == 9660
    assert total_positive == 3557
    assert total_negative == 6103


def test_both_roles_contain_both_classes() -> None:
    aggregates: dict[str, dict[str, int]] = {}
    with WINDOW_MANIFEST.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["partition"] != "TRAIN" or row["core_eligible"] != "TRUE":
                continue
            pg = row["participant_group_id"]
            entry = aggregates.setdefault(pg, {"positive": 0, "negative": 0})
            if int(row["label"]) == 1:
                entry["positive"] += 1
            else:
                entry["negative"] += 1

    rows = _rows()
    for role in ("FINAL_INNER_VALIDATION", "OPTIMISE"):
        groups = [r["participant_group_id"] for r in rows if r["role"] == role]
        positive = sum(aggregates[pg]["positive"] for pg in groups)
        negative = sum(aggregates[pg]["negative"] for pg in groups)
        assert positive > 0, f"{role} has zero positive windows"
        assert negative > 0, f"{role} has zero negative windows"


def test_outer_cv_inner_manifest_unaffected() -> None:
    assert OUTER_INNER_CSV.exists()
    with OUTER_INNER_CSV.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 135
    roles = {r["role"] for r in rows}
    assert roles == {"OPTIMISE", "INNER_VALIDATION", "OUTER_TEST"}


def test_deterministic_regeneration_byte_identical() -> None:
    before_csv = MANIFEST_CSV.read_bytes()
    before_lock = MANIFEST_LOCK.read_bytes()
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/build_model_v2_final_inner_v2_v1.py")],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert MANIFEST_CSV.read_bytes() == before_csv
    assert MANIFEST_LOCK.read_bytes() == before_lock


def test_lock_sha_matches_file_and_binds_method() -> None:
    lock = json.loads(MANIFEST_LOCK.read_text(encoding="utf-8"))
    assert lock["manifest_sha256"] == hash_file(MANIFEST_CSV)
    assert lock["algorithm"] == "EXACT_EXHAUSTIVE_MIN_SQUARED_DEVIATION_5_GROUP_COMBINATION_V1"
    assert lock["method_committed_before_result_generated"] is True
    assert lock["final_inner_validation_size"] == 5
    assert (
        lock["distinct_from"]
        == "MITDB_TRAIN_INNER_V2_V1 (historical per-outer-fold inner manifest, untouched)"
    )


def test_component_registry_row_additive() -> None:
    with (ROOT / "manifests/model_v2/component_registry_v1.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    row = next(r for r in rows if r["component_id"] == "MITDB_TRAIN_FINAL_INNER_V2_V1")
    assert row["status"] == "FROZEN_CV_MANIFEST"
    assert row["predecessor_id"] == ""
