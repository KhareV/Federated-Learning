from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from deployment.export import DEVELOPMENT_ATOL
from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]


def test_source_model_and_script_selection_are_frozen() -> None:
    assert hash_file(ROOT / "checkpoints/MODEL_V1.pt") == (
        "021352eb067932015b657f0570ac155f8ef00af2d43864e13a110d0252bc7bfe"
    )
    config = (ROOT / "configs/gateway_artifact_v1.yaml").read_text()
    assert "selected: TORCHSCRIPT_SCRIPT" in config
    assert "DEPLOYMENT_EQUIVALENCE_ONLY" in config
    assert DEVELOPMENT_ATOL == 1e-5


def test_development_export_uses_no_internal_test() -> None:
    source = (ROOT / "deployment/export.py").read_text()
    assert "load_internal_population" not in source
    assert "reports/internal_test" not in source
    if (ROOT / "reports/t029/export_development_audit.json").exists():
        audit = json.loads((ROOT / "reports/t029/export_development_audit.json").read_text())
        assert audit["INTERNAL_TEST_used_for_selection"] is False
        assert audit["F08_maximum_absolute_difference"] <= 1e-5


def test_f08_fixture_contract() -> None:
    with np.load(ROOT / "tests/fixtures/model_v1_test_vector.npz") as fixture:
        assert fixture["normalized_inputs_float32"].shape == (3, 1, 2500)
        assert fixture["normalized_inputs_float32"].dtype == np.float32
