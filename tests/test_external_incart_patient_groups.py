from __future__ import annotations

import numpy as np

from evaluation.bootstrap import expand_cluster_draw, generate_patient_draws
from evaluation.external_incart import load_patient_map


def test_patient_map_closes_75_records_to_32_groups() -> None:
    mapping = load_patient_map()
    assert len(mapping) == 75
    assert len(set(mapping.values())) == 32
    assert set(mapping) == {f"I{number:02d}" for number in range(1, 76)}


def test_multi_record_patient_draw_preserves_full_cluster_multiplicity() -> None:
    # A owns A1/A2 rows, B owns B1, C owns C1/C2/C3.
    patient_ids = np.asarray(["A", "A", "B", "C", "C", "C"])
    patients = np.asarray(["A", "B", "C"])
    draw = np.asarray([0, 0, 2], dtype=np.int64)
    expanded = expand_cluster_draw(patient_ids, patients, draw)
    assert expanded.tolist() == [0, 1, 0, 1, 3, 4, 5]


def test_external_bootstrap_is_patient_clustered_and_exactly_2000() -> None:
    patient_ids = np.asarray(["A", "A", "B", "C", "C"])
    patients, draws = generate_patient_draws(patient_ids, 2000, 20260927)
    assert patients.tolist() == ["A", "B", "C"]
    assert draws.shape == (2000, 3)
