"""Authenticated, read-only inspection of frozen MIT-BIH TRAIN processed windows.

This does not read raw WFDB recordings, held-out waveforms, or run model inference.
The window manifest contains aggregate mapped-beat counts, not annotation positions.
"""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict

from product.observatory.models import SignalPoint, SignalStage
from product.observatory.pipeline import _stage

ROOT = Path(__file__).resolve().parents[2]
CACHE_MANIFEST = ROOT / "manifests/windows/MITDB_WINDOWS_V1.cache.csv"
WINDOW_MANIFEST = ROOT / "manifests/windows/MITDB_WINDOWS_V1.csv"
SPLIT_MANIFEST = ROOT / "manifests/splits/MITDB_SPLIT_V1.csv"
CACHE_SHA = "35610daa9e0611cca9976664af0e37492011637e085ba866806f378092c6fe4d"
WINDOW_SHA = "1a68da870c129d77c438a2254fdbfa4eac71181a1a10cf30076ec9e9109d0f4a"
SPLIT_SHA = "00c61f7ebd6b48b153029402d5fdac80031802fbaa700773eef4dcbc65162a4c"
PROCESSED_ROOT = (ROOT / "data/processed/mitdb/1.0.0/PREPROC_V1/MITDB_SPLIT_V1"
                  / "AAMI_SVF_WINDOW_V1/TRAIN")


class ResearchRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    dataset_id: Literal["MITDB"] = "MITDB"
    record_id: str
    participant_group_id: str
    partition: Literal["TRAIN"] = "TRAIN"
    eligible_window_count: int
    source_kind: Literal["FROZEN_PROCESSED_RESEARCH_CACHE"] = "FROZEN_PROCESSED_RESEARCH_CACHE"


class ResearchWindow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    record: ResearchRecord
    window_index: int
    example_id: str
    left_timestamp_us: int
    right_timestamp_us: int
    signal_interval: Literal["LEFT_CLOSED_RIGHT_OPEN"] = "LEFT_CLOSED_RIGHT_OPEN"
    annotation_interval: Literal["BOTH_CLOSED"] = "BOTH_CLOSED"
    stage: SignalStage
    label_contract: Literal["AAMI_SVF_WINDOW_V1"] = "AAMI_SVF_WINDOW_V1"
    label: int
    label_status: str
    mapped_n_count: int
    mapped_s_count: int
    mapped_v_count: int
    mapped_f_count: int
    q_count: int
    unmappable_count: int
    annotation_positions_status: Literal["UNAVAILABLE_RAW_WFDB_NOT_PRESENT"] = (
        "UNAVAILABLE_RAW_WFDB_NOT_PRESENT"
    )
    cache_file_sha256: str
    example_ids_file_sha256: str
    window_manifest_sha256: str = WINDOW_SHA
    split_manifest_sha256: str = SPLIT_SHA
    claim_boundary: Literal["PROCESSED_TRAIN_WINDOW_NOT_HELD_OUT_INFERENCE"] = (
        "PROCESSED_TRAIN_WINDOW_NOT_HELD_OUT_INFERENCE"
    )


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _rows(path: Path, expected_sha: str) -> list[dict[str, str]]:
    if _hash(path) != expected_sha:
        raise ValueError("FROZEN_RESEARCH_MANIFEST_HASH_MISMATCH")
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def _train_cache() -> list[dict[str, str]]:
    split = _rows(SPLIT_MANIFEST, SPLIT_SHA)
    train_ids = {row["record_id"] for row in split if row["partition"] == "TRAIN"}
    rows = _rows(CACHE_MANIFEST, CACHE_SHA)
    result = [row for row in rows if row["partition"] == "TRAIN" and row["record_id"] in train_ids]
    if len(result) != len(train_ids) or len({row["record_id"] for row in result}) != len(result):
        raise ValueError("TRAIN_CACHE_SPLIT_RECONCILIATION_FAILED")
    return sorted(result, key=lambda row: row["record_id"])


def list_train_records() -> list[ResearchRecord]:
    return [ResearchRecord(record_id=row["record_id"],
                           participant_group_id=row["participant_group_id"],
                           eligible_window_count=int(row["eligible_window_count"]))
            for row in _train_cache()]


def _locked_train_file(relative: str) -> Path:
    path = (ROOT / relative).resolve()
    if not path.is_relative_to(PROCESSED_ROOT.resolve()) or not path.is_file():
        raise ValueError("RESEARCH_CACHE_PATH_NOT_ALLOWED_OR_UNAVAILABLE")
    return path


def inspect_train_window(record_id: str, window_index: int) -> ResearchWindow:
    cache = next((row for row in _train_cache() if row["record_id"] == record_id), None)
    if cache is None or window_index < 0 or window_index >= int(cache["eligible_window_count"]):
        raise ValueError("TRAIN_WINDOW_NOT_AVAILABLE")
    wave_path = _locked_train_file(cache["relative_path"])
    id_path = _locked_train_file(cache["example_ids_path"])
    if _hash(wave_path) != cache["sha256"] or _hash(id_path) != cache["example_ids_sha256"]:
        raise ValueError("FROZEN_RESEARCH_CACHE_HASH_MISMATCH")
    ids = id_path.read_text(encoding="utf-8").splitlines()
    windows = np.load(wave_path, mmap_mode="r", allow_pickle=False)
    if windows.shape != (len(ids), 2500) or windows.dtype != np.float64:
        raise ValueError("FROZEN_RESEARCH_CACHE_SHAPE_MISMATCH")
    matching = [row for row in _rows(WINDOW_MANIFEST, WINDOW_SHA)
                if row["example_id"] == ids[window_index]]
    if len(matching) != 1:
        raise ValueError("FROZEN_RESEARCH_EXAMPLE_ID_MISMATCH")
    row = matching[0]
    if (row["partition"] != "TRAIN" or row["record_id"] != record_id
            or row["participant_group_id"] != cache["participant_group_id"]
            or row["core_eligible"].upper() != "TRUE" or row["label"] not in {"0", "1"}
            or int(row["window_samples"]) != 2500 or int(row["sample_rate_hz"]) != 250):
        raise ValueError("FROZEN_RESEARCH_WINDOW_CONTRACT_MISMATCH")
    left_us = int(row["signal_start_timestamp_us"])
    right_us = int(row["signal_end_exclusive_timestamp_us"])
    if right_us - left_us != 10_000_000:
        raise ValueError("FROZEN_RESEARCH_WINDOW_TIME_MISMATCH")
    selected = windows[window_index]
    if not bool(np.isfinite(selected).all()):
        raise ValueError("FROZEN_RESEARCH_WINDOW_NONFINITE")
    stage = _stage("PREPROC_V1_FILTERED_TRAIN_CACHE", "filtered ECG cache units", 250,
                   [SignalPoint(timestamp_us=left_us + index * 4000, value=float(value))
                    for index, value in enumerate(selected)])
    return ResearchWindow(
        record=ResearchRecord(record_id=record_id,
                              participant_group_id=cache["participant_group_id"],
                              eligible_window_count=int(cache["eligible_window_count"])),
        window_index=window_index, example_id=row["example_id"], left_timestamp_us=left_us,
        right_timestamp_us=right_us, stage=stage, label=int(row["label"]),
        label_status=row["label_status"],
        mapped_n_count=int(row["mapped_n_count"]), mapped_s_count=int(row["mapped_s_count"]),
        mapped_v_count=int(row["mapped_v_count"]), mapped_f_count=int(row["mapped_f_count"]),
        q_count=int(row["q_count"]), unmappable_count=int(row["unmappable_count"]),
        cache_file_sha256=cache["sha256"], example_ids_file_sha256=cache["example_ids_sha256"],
    )
