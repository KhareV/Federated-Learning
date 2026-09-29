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

from models.model_freeze import ModelFreezeError, load_frozen_model_v1, verify_frozen_model_v1
from nhm.hashing import hash_file
from scripts.generate_model_v1_test_vector_t016 import write_deterministic_npz

ROOT = Path(__file__).resolve().parents[1]


def frozen_copy(tmp_path: Path) -> Path:
    manifest = json.loads((ROOT / "checkpoints/MODEL_V1.manifest.json").read_text())
    paths = {
        manifest["checkpoint"]["path"],
        manifest["frozen_config"]["path"],
        manifest["test_vector"]["path"],
        manifest["freeze_audit"]["path"],
        *manifest["upstream_sha256"],
    }
    for relative in paths:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    target_manifest = tmp_path / "checkpoints/MODEL_V1.manifest.json"
    target_manifest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "checkpoints/MODEL_V1.manifest.json", target_manifest)
    return target_manifest


def test_committed_f08_package_verifies_and_loads_eval_model() -> None:
    result = verify_frozen_model_v1(ROOT)
    assert result["status"] == "PASS"
    assert result["maximum_absolute_error"] <= 1e-6
    model, metadata = load_frozen_model_v1(ROOT)
    assert model.training is False
    assert metadata["checkpoint_sha256"] == hash_file(ROOT / "checkpoints/MODEL_V1.pt")


def test_candidate_and_final_are_byte_and_state_identical_and_tracked() -> None:
    candidate = ROOT / "checkpoints/candidates/MODEL_V1/MODEL_V1_seed_20260927_best.pt"
    final = ROOT / "checkpoints/MODEL_V1.pt"
    assert candidate.read_bytes() == final.read_bytes()
    first = torch.load(candidate, map_location="cpu", weights_only=True)["state_dict"]
    second = torch.load(final, map_location="cpu", weights_only=True)["state_dict"]
    assert first.keys() == second.keys()
    assert all(torch.equal(first[key], second[key]) for key in first)
    tracked = subprocess.check_output(
        [
            "git",
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            str(final.relative_to(ROOT)),
        ],
        cwd=ROOT,
        text=True,
    )
    assert "checkpoints/MODEL_V1.pt" in tracked


def test_frozen_config_preserves_t015_scientific_contract() -> None:
    candidate = yaml.safe_load((ROOT / "configs/model_v1.yaml").read_text())
    frozen = yaml.safe_load((ROOT / "configs/model_v1_frozen.yaml").read_text())
    keys = {
        "model_id", "spec_version", "target_id", "map_id", "preproc_id", "split_id",
        "input", "architecture", "loss", "optimizer", "scheduler", "training",
        "augmentation", "seeds", "determinism", "partition_contract",
    }
    assert {key: candidate[key] for key in keys} == {key: frozen[key] for key in keys}
    assert frozen["calibration_id"] is None
    assert frozen["temperature"] is None
    assert frozen["operating_threshold"] is None


@pytest.mark.parametrize(
    ("kind", "error"),
    [
        ("checkpoint", "MODEL_CHECKPOINT_HASH_MISMATCH"),
        ("config", "MODEL_CONFIG_HASH_MISMATCH"),
        ("vector", "MODEL_TEST_VECTOR_HASH_MISMATCH"),
        ("upstream", "MODEL_UPSTREAM_HASH_MISMATCH"),
        ("split", "MODEL_UPSTREAM_HASH_MISMATCH"),
    ],
)
def test_f08_bound_artifact_tamper_is_detected(
    tmp_path: Path, kind: str, error: str
) -> None:
    manifest_path = frozen_copy(tmp_path)
    manifest = json.loads(manifest_path.read_text())
    relative = {
        "checkpoint": manifest["checkpoint"]["path"],
        "config": manifest["frozen_config"]["path"],
        "vector": manifest["test_vector"]["path"],
        "upstream": "manifests/preprocessing/PREPROC_V1.lock.json",
        "split": "manifests/splits/MITDB_SPLIT_V1.csv",
    }[kind]
    target = tmp_path / relative
    data = bytearray(target.read_bytes())
    data[len(data) // 2] ^= 1
    target.write_bytes(data)
    with pytest.raises(ModelFreezeError, match=error):
        verify_frozen_model_v1(tmp_path, manifest_path)


@pytest.mark.parametrize("array_name", ["normalized_inputs_float32", "expected_logits_float32"])
def test_semantic_test_vector_tamper_is_detected(
    tmp_path: Path, array_name: str
) -> None:
    manifest_path = frozen_copy(tmp_path)
    manifest = json.loads(manifest_path.read_text())
    vector = tmp_path / manifest["test_vector"]["path"]
    with np.load(vector, allow_pickle=False) as fixture:
        arrays = {name: fixture[name].copy() for name in fixture.files}
    arrays[array_name].flat[0] += np.float32(0.5)
    write_deterministic_npz(vector, arrays)
    manifest["test_vector"]["sha256"] = hash_file(vector)
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ModelFreezeError, match="MODEL_TEST_VECTOR_LOGIT_MISMATCH"):
        verify_frozen_model_v1(tmp_path, manifest_path)


def test_release_seed_tamper_is_detected(tmp_path: Path) -> None:
    manifest_path = frozen_copy(tmp_path)
    manifest = json.loads(manifest_path.read_text())
    manifest["release_seed"] = 20260928
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ModelFreezeError, match="MODEL_MANIFEST_IDENTITY_MISMATCH"):
        verify_frozen_model_v1(tmp_path, manifest_path)


def test_architecture_tamper_is_detected_even_with_updated_config_hash(tmp_path: Path) -> None:
    manifest_path = frozen_copy(tmp_path)
    manifest = json.loads(manifest_path.read_text())
    config_path = tmp_path / manifest["frozen_config"]["path"]
    config = yaml.safe_load(config_path.read_text())
    config["architecture"]["expected_trainable_parameters"] = 13_186
    config_path.write_text(yaml.safe_dump(config, sort_keys=False))
    manifest["frozen_config"]["sha256"] = hash_file(config_path)
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ModelFreezeError, match="MODEL_CONFIG_SEMANTIC_MISMATCH"):
        verify_frozen_model_v1(tmp_path, manifest_path)


def test_fresh_process_verification() -> None:
    command = (
        "from pathlib import Path; "
        "from models.model_freeze import verify_frozen_model_v1; "
        "assert verify_frozen_model_v1(Path('.'))['status']=='PASS'"
    )
    for _ in range(2):
        subprocess.run([sys.executable, "-c", command], cwd=ROOT, check=True)
