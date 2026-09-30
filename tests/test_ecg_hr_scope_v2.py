from __future__ import annotations

import ast
from pathlib import Path

import pytest

from evaluation.ecg_hr_v2 import records_for_partition

ROOT = Path(__file__).resolve().parents[1]


def test_only_train_validation_partitions_are_accepted() -> None:
    for forbidden in ("CALIBRATION", "INTERNAL_TEST", "INCART", "NSTDB", "BIDMC"):
        with pytest.raises(ValueError, match="SCOPE_VIOLATION"):
            records_for_partition(forbidden)


def test_production_candidate_code_has_no_reference_or_simulation_truth() -> None:
    source = (ROOT / "preprocessing/ecg_hr_context.py").read_text(encoding="utf-8")
    assert "reference_hr" not in source
    assert "SimulationTruth" not in source
    tree = ast.parse(source)
    imports = {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert not any(name.startswith(("datasets.bidmc", "models", "training")) for name in imports)


def test_t021_and_f06_files_are_not_implementation_targets() -> None:
    source = (ROOT / "evaluation/ecg_hr_v2.py").read_text(encoding="utf-8")
    for forbidden in (
        "reports/t021",
        "reports/bidmc_multimodal_engineering",
        "configs/bidmc_context_v1.yaml",
        "data/raw/bidmc",
    ):
        assert forbidden not in source
