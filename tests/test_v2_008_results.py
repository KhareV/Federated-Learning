"""V2-008 post-freeze tests: locks the real, committed MODEL_V2_FINAL package. Mirrors
tests/test_model_v1_freeze.py's F08 tamper-test pattern exactly, applied to copies of the
REAL canonical artifacts this time (they now exist). Fails if the checkpoint/config/vector
are not byte-identical to the frozen V2-007 release candidate, if any status-distinction
field (promotion_eligible, operational_lineage, runtime_acceptance) is wrong, or if tamper
detection regresses.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import torch
import yaml

from models.model_v2_architectures import ModelV2TcnMean, count_trainable_parameters
from models.model_v2_final_freeze import (
    ModelV2FinalFreezeError,
    load_model_v2_final,
    verify_model_v2_final,
)
from nhm.hashing import hash_file
from scripts.generate_model_v2_final_test_vector_v2008 import write_deterministic_npz

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SHA = "89418edcc2c13f0edd9a36666bac560ad922dd4700b4b6dd19b56d067d4eff9b"
SOURCE_CANDIDATE = (
    ROOT / "checkpoints/model_v2/v2_007_official_validation/V2-007-TCNMEAN-S20260927_best.pt"
)


def frozen_copy(tmp_path: Path) -> Path:
    manifest = json.loads((ROOT / "checkpoints/MODEL_V2_FINAL.manifest.json").read_text())
    paths = {
        manifest["checkpoint"]["path"],
        manifest["frozen_config"]["path"],
        manifest["test_vector"]["path"],
        *manifest["upstream_sha256"],
    }
    for relative in paths:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    target_manifest = tmp_path / "checkpoints/MODEL_V2_FINAL.manifest.json"
    target_manifest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "checkpoints/MODEL_V2_FINAL.manifest.json", target_manifest)
    return target_manifest


def test_committed_package_verifies_and_loads_eval_model() -> None:
    result = verify_model_v2_final(ROOT)
    assert result["status"] == "PASS"
    assert result["maximum_absolute_error"] <= 1e-7
    model, metadata = load_model_v2_final(ROOT)
    assert model.training is False
    assert metadata["checkpoint_sha256"] == hash_file(ROOT / "checkpoints/MODEL_V2_FINAL.pt")


def test_checkpoint_byte_identical_to_source_and_sha_exact() -> None:
    final = ROOT / "checkpoints/MODEL_V2_FINAL.pt"
    assert hash_file(final) == EXPECTED_SHA
    assert SOURCE_CANDIDATE.read_bytes() == final.read_bytes()
    first = torch.load(SOURCE_CANDIDATE, map_location="cpu", weights_only=False)["state_dict"]
    second = torch.load(final, map_location="cpu", weights_only=False)["state_dict"]
    assert first.keys() == second.keys()
    assert all(torch.equal(first[key], second[key]) for key in first)


def test_checkpoint_force_tracked() -> None:
    tracked = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard",
         "checkpoints/MODEL_V2_FINAL.pt"],
        cwd=ROOT, text=True,
    )
    assert "checkpoints/MODEL_V2_FINAL.pt" in tracked


def test_parameter_count_exact() -> None:
    model = ModelV2TcnMean()
    payload = torch.load(ROOT / "checkpoints/MODEL_V2_FINAL.pt", map_location="cpu",
                          weights_only=False)
    model.load_state_dict(payload["state_dict"], strict=True)
    assert count_trainable_parameters(model) == 57553


def test_frozen_config_status_distinction_fields_exact() -> None:
    config = yaml.safe_load((ROOT / "configs/model_v2_final_frozen.yaml").read_text())
    assert config["model_id"] == "MODEL_V2_FINAL"
    assert config["parent_architecture"] == "MODEL_V2_TCN_MEAN"
    assert config["schedule_id"] == "CONFIG_V2_TCN_MEAN_ORIGINAL_V1"
    assert config["release_seed"] == 20260927
    assert config["selected_epoch"] == 5
    assert config["parameter_count"] == 57553
    assert config["calibration"] == "NONE_YET"
    assert config["operating_threshold"] == "NONE_YET"
    assert config["official_validation_promotion_eligible"] is False
    assert config["official_validation_promotion_decision"] == (
        "MODEL_V2_NOT_PROMOTED_RELEASE_CI"
    )
    assert config["operational_lineage"] == "MODEL_V1"
    assert config["runtime_acceptance"] == "NOT_EVALUATED"
    assert config["scientific_final_frozen"] is True


def test_synthetic_fixture_contains_no_patient_data() -> None:
    metadata = json.loads(
        (ROOT / "tests/fixtures/model_v2_final_test_vector.metadata.json").read_text()
    )
    assert metadata["synthetic"] is True
    assert metadata["patient_data"] is False
    assert metadata["number_of_vectors"] == 3
    with np.load(
        ROOT / "tests/fixtures/model_v2_final_test_vector.npz", allow_pickle=False
    ) as fixture:
        raw = fixture["raw_windows_float64"]
    assert raw.shape == (3, 2500)
    assert np.all(raw[0] == 0.0)


def test_fixture_regeneration_byte_identical() -> None:
    metadata = json.loads(
        (ROOT / "tests/fixtures/model_v2_final_test_vector.metadata.json").read_text()
    )
    assert metadata["byte_identical_regeneration"] is True
    assert metadata["first_generation_sha256"] == metadata["second_generation_sha256"]
    assert metadata["npz_sha256"] == hash_file(
        ROOT / "tests/fixtures/model_v2_final_test_vector.npz"
    )


@pytest.mark.parametrize(
    ("kind", "error"),
    [
        ("checkpoint", "MODEL_V2_FINAL_CHECKPOINT_HASH_MISMATCH"),
        ("config", "MODEL_V2_FINAL_CONFIG_HASH_MISMATCH"),
        ("vector", "MODEL_V2_FINAL_TEST_VECTOR_HASH_MISMATCH"),
        ("upstream", "MODEL_V2_FINAL_UPSTREAM_HASH_MISMATCH"),
    ],
)
def test_bound_artifact_tamper_is_detected(tmp_path: Path, kind: str, error: str) -> None:
    manifest_path = frozen_copy(tmp_path)
    manifest = json.loads(manifest_path.read_text())
    relative = {
        "checkpoint": manifest["checkpoint"]["path"],
        "config": manifest["frozen_config"]["path"],
        "vector": manifest["test_vector"]["path"],
        "upstream": next(iter(manifest["upstream_sha256"])),
    }[kind]
    target = tmp_path / relative
    data = bytearray(target.read_bytes())
    data[len(data) // 2] ^= 1
    target.write_bytes(bytes(data))
    with pytest.raises(ModelV2FinalFreezeError, match=error):
        verify_model_v2_final(tmp_path, manifest_path)


def test_semantic_test_vector_tamper_is_detected(tmp_path: Path) -> None:
    manifest_path = frozen_copy(tmp_path)
    manifest = json.loads(manifest_path.read_text())
    vector = tmp_path / manifest["test_vector"]["path"]
    with np.load(vector, allow_pickle=False) as fixture:
        arrays = {name: fixture[name].copy() for name in fixture.files}
    arrays["expected_logits_float32"].flat[0] += np.float32(5.0)
    write_deterministic_npz(vector, arrays)
    manifest["test_vector"]["sha256"] = hash_file(vector)
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ModelV2FinalFreezeError, match="MODEL_V2_FINAL_TEST_VECTOR_LOGIT_MISMATCH"):
        verify_model_v2_final(tmp_path, manifest_path)


def test_release_seed_tamper_is_detected(tmp_path: Path) -> None:
    manifest_path = frozen_copy(tmp_path)
    manifest = json.loads(manifest_path.read_text())
    manifest["release_seed"] = 20260928
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(
        ModelV2FinalFreezeError, match="MODEL_V2_FINAL_MANIFEST_IDENTITY_MISMATCH"
    ):
        verify_model_v2_final(tmp_path, manifest_path)


def test_promotion_eligible_cannot_be_flipped_true(tmp_path: Path) -> None:
    manifest_path = frozen_copy(tmp_path)
    manifest = json.loads(manifest_path.read_text())
    manifest["promotion_eligible"] = True
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(
        ModelV2FinalFreezeError, match="MODEL_V2_FINAL_MANIFEST_IDENTITY_MISMATCH"
    ):
        verify_model_v2_final(tmp_path, manifest_path)


def test_operational_lineage_cannot_be_changed(tmp_path: Path) -> None:
    manifest_path = frozen_copy(tmp_path)
    manifest = json.loads(manifest_path.read_text())
    manifest["operational_lineage"] = "MODEL_V2_FINAL"
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(
        ModelV2FinalFreezeError, match="MODEL_V2_FINAL_MANIFEST_IDENTITY_MISMATCH"
    ):
        verify_model_v2_final(tmp_path, manifest_path)


def test_runtime_acceptance_cannot_be_prematurely_accepted(tmp_path: Path) -> None:
    manifest_path = frozen_copy(tmp_path)
    manifest = json.loads(manifest_path.read_text())
    manifest["runtime_acceptance"] = "ACCEPTED"
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(
        ModelV2FinalFreezeError, match="MODEL_V2_FINAL_MANIFEST_IDENTITY_MISMATCH"
    ):
        verify_model_v2_final(tmp_path, manifest_path)


def test_architecture_tamper_is_detected_even_with_updated_config_hash(tmp_path: Path) -> None:
    manifest_path = frozen_copy(tmp_path)
    manifest = json.loads(manifest_path.read_text())
    config_path = tmp_path / manifest["frozen_config"]["path"]
    config = yaml.safe_load(config_path.read_text())
    config["parameter_count"] = 57554
    config_path.write_text(yaml.safe_dump(config, sort_keys=False))
    manifest["frozen_config"]["sha256"] = hash_file(config_path)
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(
        ModelV2FinalFreezeError, match="MODEL_V2_FINAL_CONFIG_SEMANTIC_MISMATCH"
    ):
        verify_model_v2_final(tmp_path, manifest_path)


def test_fresh_process_verification() -> None:
    command = (
        "from pathlib import Path; "
        "from models.model_v2_final_freeze import verify_model_v2_final; "
        "assert verify_model_v2_final(Path('.'))['status']=='PASS'"
    )
    for _ in range(2):
        subprocess.run([sys.executable, "-c", command], cwd=ROOT, check=True)


def test_two_process_reproducibility_report() -> None:
    audit = json.loads(
        (ROOT / "reports/model_v2/v2_008/checkpoint_byte_identity.json").read_text()
    )
    assert audit["overall_status"] == "PASS"
    assert audit["maximum_absolute_error"] == 0.0
    assert audit["maximum_relative_error"] == 0.0
    assert audit["process_a_logits"] == audit["process_b_logits"]
    assert audit["official_validation_promotion_eligible"] is False
    assert audit["operational_lineage"] == "MODEL_V1"
    assert audit["runtime_acceptance"] == "NOT_EVALUATED"
    for key, value in audit["data_access_counts"].items():
        assert value == 0, key


def test_manifest_status_distinction_fields_exact() -> None:
    manifest = json.loads(
        (ROOT / "checkpoints/MODEL_V2_FINAL.manifest.json").read_text()
    )
    assert manifest["model_id"] == "MODEL_V2_FINAL"
    assert manifest["scientific_status"] == "FROZEN"
    assert manifest["operational_status"] == "NOT_OPERATIONAL"
    assert manifest["promotion_decision"] == "MODEL_V2_NOT_PROMOTED_RELEASE_CI"
    assert manifest["promotion_eligible"] is False
    assert manifest["operational_lineage"] == "MODEL_V1"
    assert manifest["runtime_acceptance"] == "NOT_EVALUATED"
    assert manifest["release_seed"] == 20260927
    assert manifest["selected_epoch"] == 5
    assert manifest["parameter_count"] == 57553
