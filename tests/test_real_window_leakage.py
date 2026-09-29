from __future__ import annotations

import ast
import csv
from pathlib import Path

import numpy as np

from preprocessing.mitdb_windows import build_record, verify_cache_manifest

ROOT = Path(__file__).resolve().parents[1]


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_real_manifest_inherits_frozen_partition_and_has_complete_population() -> None:
    manifest = _rows(ROOT / "manifests/windows/MITDB_WINDOWS_V1.csv")
    split = _rows(ROOT / "manifests/splits/MITDB_SPLIT_V1.csv")
    lookup = {
        row["record_id"]: (row["participant_group_id"], row["partition"]) for row in split
    }
    represented = {row["record_id"] for row in manifest}
    assert represented == set(lookup)
    assert len(represented) == 46
    assert len({row["participant_group_id"] for row in manifest}) == 45
    assert not ({"102", "104"} & represented)
    assert lookup["201"][1] == lookup["202"][1]
    assert all(
        (row["participant_group_id"], row["partition"]) == lookup[row["record_id"]]
        for row in manifest
    )
    assert len({row["example_id"] for row in manifest}) == len(manifest)


def test_real_manifest_geometry_quality_and_eligibility() -> None:
    rows = _rows(ROOT / "manifests/windows/MITDB_WINDOWS_V1.csv")
    for row in rows:
        assert int(row["window_samples"]) == 2500
        assert int(row["sample_rate_hz"]) == 250
        assert int(row["canonical_end_index_exclusive"]) - int(
            row["canonical_start_index"]
        ) == 2500
        assert int(row["prediction_timestamp_us"]) == int(
            row["signal_end_exclusive_timestamp_us"]
        )
        assert int(row["prediction_timestamp_us"]) - 4000 >= int(
            row["signal_start_timestamp_us"]
        )
        if row["core_eligible"] == "TRUE":
            assert row["label"] in {"0", "1"}
            assert row["ecg_quality"] != "UNUSABLE"
        if row["ecg_quality"] == "UNUSABLE":
            assert row["core_eligible"] == "FALSE"


def test_real_cache_paths_are_partition_local_and_fresh() -> None:
    cache_rows = _rows(ROOT / "manifests/windows/MITDB_WINDOWS_V1.cache.csv")
    split = {row["record_id"]: row for row in _rows(ROOT / "manifests/splits/MITDB_SPLIT_V1.csv")}
    assert len(cache_rows) == 46
    assert all(row["partition"] in row["relative_path"].split("/") for row in cache_rows)
    assert all(row["partition"] == split[row["record_id"]]["partition"] for row in cache_rows)
    assert verify_cache_manifest(ROOT)["status"] == "PASS"


def test_selected_real_record_rebuild_is_deterministic(tmp_path: Path) -> None:
    split_row = _rows(ROOT / "manifests/splits/MITDB_SPLIT_V1.csv")[0]
    rows_a, arrays_a, ids_a = build_record(ROOT, split_row, chunk_size=4096)
    rows_b, arrays_b, ids_b = build_record(ROOT, split_row, chunk_size=7777)
    assert rows_a == rows_b
    assert ids_a == ids_b
    np.testing.assert_array_equal(arrays_a, arrays_b)
    paths = [tmp_path / "a.npy", tmp_path / "b.npy"]
    for path, array in zip(paths, (arrays_a, arrays_b), strict=True):
        with path.open("wb") as handle:
            np.save(handle, array, allow_pickle=False)
    assert paths[0].read_bytes() == paths[1].read_bytes()


def test_builder_uses_canonical_pipeline_and_no_forbidden_transform() -> None:
    source = (ROOT / "preprocessing/mitdb_windows.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "preprocessing.ecg"
        for alias in node.names
    }
    assert "ECGPreprocessingPipeline" in imported
    for forbidden in ("scipy.signal.resample", "resample_poly", "filtfilt", "sosfiltfilt"):
        assert forbidden not in source
