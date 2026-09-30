from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from datasets.labels import UNMAPPABLE, map_annotation_symbol
from evaluation.external_incart import validate_method_config, verify_source_contract
from preprocessing.ecg import ECGPreprocessingPipeline
from preprocessing.windowing import select_annotation_indices_closed

ROOT = Path(__file__).resolve().parents[1]


def test_external_method_config_is_exact() -> None:
    config = validate_method_config(ROOT)
    assert config["signal"]["required_lead_name"] == "II"
    assert config["signal"]["fallback"] == "NONE"
    assert config["signal"]["source_rate_hz"] == 257
    assert config["signal"]["target_rate_hz"] == 250
    assert config["one_shot"] is True
    assert config["adaptation"] is False


def test_t007_source_and_lead_contract_closes() -> None:
    result = verify_source_contract(ROOT)
    assert result["records"] == 75
    assert result["patient_groups"] == 32
    assert result["lead_eligible_records"] == 75
    assert result["lead_exclusions"] == 0
    assert result["fallback_used"] is False


def test_257_hz_closed_annotation_boundaries() -> None:
    # Window ending at 10 s covers annotation source indices [0, 2570] inclusively.
    samples = np.asarray([-1, 0, 2569, 2570, 2571], dtype=np.int64)
    selected = select_annotation_indices_closed(samples, 257, 10_000_000)
    assert samples[selected].tolist() == [0, 2569, 2570]


def test_257_to_250_pipeline_is_chunk_equivalent() -> None:
    signal = np.linspace(-1.0, 1.0, 7000, dtype=np.float64)

    def process(chunks: tuple[int, ...]) -> np.ndarray:
        pipeline = ECGPreprocessingPipeline(257, "INCART_257_TO_250_V1")
        values = []
        start = 0
        for size in chunks:
            stop = start + size
            output = pipeline.process(
                signal[start:stop],
                np.arange(start, stop, dtype=np.int64),
                source_timestamps_us=(
                    np.arange(start, stop, dtype=np.int64) * 1_000_000 // 257
                    if start == 0
                    else None
                ),
            )
            values.extend(chunk.filtered_values for chunk in output.chunks)
            start = stop
        return np.concatenate(values)

    whole = process((7000,))
    chunked = process((113, 2000, 17, 4870))
    np.testing.assert_array_equal(whole, chunked)


def test_negative_presignal_annotations_are_preserved_but_not_selected() -> None:
    validation = json.loads((ROOT / "reports/t007/incart_validation.json").read_text())
    affected = {item["record_id"] for item in validation["known_source_anomalies"]}
    assert affected == {"I04", "I17", "I35", "I44", "I57", "I72", "I74"}
    selected = select_annotation_indices_closed(np.asarray([-17, 0, 10]), 257, 10_000_000)
    assert selected.tolist() == [1, 2]


def test_external_symbols_b_and_n_remain_unmappable() -> None:
    assert map_annotation_symbol("B").mapped_class == UNMAPPABLE
    assert map_annotation_symbol("n").mapped_class == UNMAPPABLE
