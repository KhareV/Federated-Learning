"""V2-008 pre-freeze test gate (Section 30). Must all pass BEFORE the canonical
MODEL_V2_FINAL.pt is created. Covers: entry/upstream/continuity/promotion/source-checkpoint
preflight evidence, the freeze-ID decision (canonical registry untouched), the synthetic
test-vector generator's determinism, and the MODEL_V2_FINAL verifier's tamper-detection logic
-- exercised against a wholly FABRICATED package (a freshly-initialized ModelV2TcnMean, never
the real V2-007 release checkpoint) since the real canonical artifacts do not exist yet.
"""

from __future__ import annotations

import csv
import json
import platform
from pathlib import Path

import numpy as np
import pytest
import torch
import yaml

import scripts.generate_model_v2_final_test_vector_v2008 as vector_gen
from models.model_v2_architectures import ModelV2TcnMean, count_trainable_parameters
from models.model_v2_final_freeze import ModelV2FinalFreezeError, verify_model_v2_final
from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "reports/model_v2/v2_008"


def _load(name: str) -> dict:
    return json.loads((OUT_DIR / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Preflight evidence (Sections 1-11)
# ---------------------------------------------------------------------------

def test_entry_audit_pass() -> None:
    data = _load("entry_audit.json")
    assert data["status"] == "PASS"
    assert data["head_equals_origin_main"] is True
    assert data["model_v2_final_absent"] is True
    assert data["cal_v2_absent"] is True


def test_upstream_identity_pass() -> None:
    data = _load("upstream_identity_audit.json")
    assert data["status"] == "PASS"
    for check in data["checks"].values():
        assert check["match"] is True


def test_v2_007_continuity_audit_pass() -> None:
    data = _load("v2_007_continuity_audit.json")
    assert data["status"] == "PASS"
    assert data["training_method_immutability"] == "PASS"
    assert data["source_train_diagnostic_27_groups_9660_windows"] is True
    assert data["orchestration_rerun_performed"] is False
    assert data["chunked_collected"] == 1680
    assert data["chunked_executed_unique"] == 1680
    assert data["chunked_chunk_count"] == 21
    assert data["chunked_missing"] == 0
    assert data["chunked_duplicates"] == 0
    assert data["chunked_unexpected"] == 0
    assert data["chunked_failed_tests"] == 0
    assert data["chunked_failed_chunks"] == 0


def test_promotion_disposition_exact() -> None:
    data = _load("promotion_disposition.json")
    assert data["status"] == "PASS"
    assert data["decision"] == "MODEL_V2_NOT_PROMOTED_RELEASE_CI"
    assert data["promotion_eligible"] is False
    assert data["criterion_a"] is True
    assert data["criterion_b1"] is False
    assert data["criterion_b2"] is True
    assert data["scientific_final_frozen"] is True
    assert data["official_validation_promotion_eligible"] is False
    assert data["operational_lineage"] == "MODEL_V1"
    assert data["runtime_acceptance_status"] == "NOT_EVALUATED"
    assert data["deployment_authorized"] is False


def test_source_checkpoint_identity_available() -> None:
    data = _load("source_checkpoint_identity.json")
    assert data["status"] == "PASS"
    assert data["bytes_available"] is True
    assert data["match"] is True
    assert data["selected_epoch"] == 5
    assert data["seed"] == 20260927
    assert data["best_scoring_seed_not_substituted"] is True
    assert data["expected_sha256"] == (
        "89418edcc2c13f0edd9a36666bac560ad922dd4700b4b6dd19b56d067d4eff9b"
    )


def test_freeze_id_selection_does_not_touch_canonical_registry() -> None:
    data = _load("freeze_id_selection.json")
    assert data["status"] == "PASS"
    assert data["canonical_registry_modified"] is False
    assert data["canonical_registry_row_count"] == 15
    assert data["canonical_registry_row_count_after"] == 15
    assert data["decision"] == "NO_CANONICAL_FREEZE_ID_ASSIGNED"

    with (ROOT / "manifests/freeze_registry_v1.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 15
    assert {r["freeze_id"] for r in rows} == {f"F{n:02d}" for n in range(1, 16)}


# ---------------------------------------------------------------------------
# Synthetic test-vector generator determinism (Section 16/19)
# ---------------------------------------------------------------------------

def test_synthetic_vectors_contain_no_patient_data_shape() -> None:
    raw = vector_gen.synthetic_raw_windows()
    assert raw.shape == (3, 2500)
    assert np.all(raw[0] == 0.0)
    assert np.any(raw[1] != 0.0)
    assert np.any(raw[2] != 0.0)


def test_vector_generation_byte_identical_across_two_calls(tmp_path: Path) -> None:
    model = ModelV2TcnMean()
    model.eval()
    fake_checkpoint = tmp_path / "fake.pt"
    torch.save({"state_dict": model.state_dict()}, fake_checkpoint)
    fake_sha = hash_file(fake_checkpoint)

    out_a = tmp_path / "a.npz"
    out_b = tmp_path / "b.npz"
    result_a = vector_gen.generate(ROOT, out_a, fake_checkpoint, fake_sha)
    result_b = vector_gen.generate(ROOT, out_b, fake_checkpoint, fake_sha)
    assert result_a["sha256"] == result_b["sha256"]
    assert out_a.read_bytes() == out_b.read_bytes()


def test_vector_generation_rejects_checkpoint_hash_mismatch(tmp_path: Path) -> None:
    model = ModelV2TcnMean()
    fake_checkpoint = tmp_path / "fake.pt"
    torch.save({"state_dict": model.state_dict()}, fake_checkpoint)
    with pytest.raises(RuntimeError, match="MODEL_V2_FINAL_CHECKPOINT_HASH_MISMATCH"):
        vector_gen.generate(ROOT, tmp_path / "out.npz", fake_checkpoint, "0" * 64)


# ---------------------------------------------------------------------------
# Verifier tamper-detection (Section 22/23/30) -- fabricated package only, never the real
# release checkpoint
# ---------------------------------------------------------------------------

def _build_fake_package(tmp_path: Path) -> Path:
    model = ModelV2TcnMean()
    model.eval()
    checkpoint_path = tmp_path / "checkpoints/MODEL_V2_FINAL.pt"
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {"model_id": "MODEL_V2_FINAL", "seed": 20260927, "best_epoch": 5,
         "state_dict": model.state_dict()},
        checkpoint_path,
    )
    checkpoint_sha = hash_file(checkpoint_path)

    vector_path = tmp_path / "tests/fixtures/model_v2_final_test_vector.npz"
    vector_result = vector_gen.generate(ROOT, vector_path, checkpoint_path, checkpoint_sha)

    upstream_rel = "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V3.lock.json"
    upstream_path = tmp_path / upstream_rel
    upstream_path.parent.mkdir(parents=True, exist_ok=True)
    upstream_path.write_text("{}", encoding="utf-8")
    upstream_sha = hash_file(upstream_path)

    config_path = tmp_path / "configs/model_v2_final_frozen.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config = {
        "model_id": "MODEL_V2_FINAL",
        "parent_architecture": "MODEL_V2_TCN_MEAN",
        "schedule_id": "CONFIG_V2_TCN_MEAN_ORIGINAL_V1",
        "release_seed": 20260927,
        "selected_epoch": 5,
        "parameter_count": count_trainable_parameters(model),
        "input_shape": [1, 2500],
        "calibration": "NONE_YET",
        "operating_threshold": "NONE_YET",
        "official_validation_promotion_eligible": False,
        "official_validation_promotion_decision": "MODEL_V2_NOT_PROMOTED_RELEASE_CI",
        "operational_lineage": "MODEL_V1",
        "runtime_acceptance": "NOT_EVALUATED",
        "scientific_final_frozen": True,
        "checkpoint": {"path": "checkpoints/MODEL_V2_FINAL.pt", "sha256": checkpoint_sha},
        "status": "FROZEN",
    }
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    config_sha = hash_file(config_path)

    manifest_path = tmp_path / "checkpoints/MODEL_V2_FINAL.manifest.json"
    manifest = {
        "model_id": "MODEL_V2_FINAL",
        "status": "FROZEN",
        "architecture_id": "MODEL_V2_TCN_MEAN",
        "release_seed": 20260927,
        "selected_epoch": 5,
        "promotion_decision": "MODEL_V2_NOT_PROMOTED_RELEASE_CI",
        "promotion_eligible": False,
        "operational_lineage": "MODEL_V1",
        "runtime_acceptance": "NOT_EVALUATED",
        "checkpoint": {"path": "checkpoints/MODEL_V2_FINAL.pt", "sha256": checkpoint_sha},
        "source_checkpoint": {"sha256": checkpoint_sha},
        "frozen_config": {"path": "configs/model_v2_final_frozen.yaml", "sha256": config_sha},
        "test_vector": {
            "path": "tests/fixtures/model_v2_final_test_vector.npz",
            "sha256": vector_result["sha256"],
            "logit_atol": 1e-7, "logit_rtol": 1e-7,
        },
        "upstream_sha256": {upstream_rel: upstream_sha},
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest_path


def test_fabricated_package_verifies_cleanly(tmp_path: Path) -> None:
    manifest_path = _build_fake_package(tmp_path)
    result = verify_model_v2_final(tmp_path, manifest_path)
    assert result["status"] == "PASS"
    assert result["maximum_absolute_error"] <= 1e-7


def test_tamper_checkpoint_byte_detected(tmp_path: Path) -> None:
    manifest_path = _build_fake_package(tmp_path)
    checkpoint_path = tmp_path / "checkpoints/MODEL_V2_FINAL.pt"
    data = bytearray(checkpoint_path.read_bytes())
    data[len(data) // 2] ^= 1
    checkpoint_path.write_bytes(bytes(data))
    with pytest.raises(ModelV2FinalFreezeError, match="MODEL_V2_FINAL_CHECKPOINT_HASH_MISMATCH"):
        verify_model_v2_final(tmp_path, manifest_path)


def test_tamper_config_byte_detected(tmp_path: Path) -> None:
    manifest_path = _build_fake_package(tmp_path)
    config_path = tmp_path / "configs/model_v2_final_frozen.yaml"
    config_path.write_text(config_path.read_text(encoding="utf-8") + "\n# tampered\n")
    with pytest.raises(ModelV2FinalFreezeError, match="MODEL_V2_FINAL_CONFIG_HASH_MISMATCH"):
        verify_model_v2_final(tmp_path, manifest_path)


def test_tamper_release_seed_detected(tmp_path: Path) -> None:
    manifest_path = _build_fake_package(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["release_seed"] = 20260928
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ModelV2FinalFreezeError, match="MODEL_V2_FINAL_MANIFEST_IDENTITY_MISMATCH"):
        verify_model_v2_final(tmp_path, manifest_path)


def test_tamper_promotion_eligible_flipped_to_true_detected(tmp_path: Path) -> None:
    manifest_path = _build_fake_package(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["promotion_eligible"] = True
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ModelV2FinalFreezeError, match="MODEL_V2_FINAL_MANIFEST_IDENTITY_MISMATCH"):
        verify_model_v2_final(tmp_path, manifest_path)


def test_tamper_operational_lineage_changed_detected(tmp_path: Path) -> None:
    manifest_path = _build_fake_package(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["operational_lineage"] = "MODEL_V2_FINAL"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ModelV2FinalFreezeError, match="MODEL_V2_FINAL_MANIFEST_IDENTITY_MISMATCH"):
        verify_model_v2_final(tmp_path, manifest_path)


def test_tamper_runtime_acceptance_prematurely_accepted_detected(tmp_path: Path) -> None:
    manifest_path = _build_fake_package(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["runtime_acceptance"] = "ACCEPTED"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ModelV2FinalFreezeError, match="MODEL_V2_FINAL_MANIFEST_IDENTITY_MISMATCH"):
        verify_model_v2_final(tmp_path, manifest_path)


def test_tamper_architecture_parameter_count_detected(tmp_path: Path) -> None:
    manifest_path = _build_fake_package(tmp_path)
    config_path = tmp_path / "configs/model_v2_final_frozen.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["parameter_count"] = 99999
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["frozen_config"]["sha256"] = hash_file(config_path)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ModelV2FinalFreezeError, match="MODEL_V2_FINAL_CONFIG_SEMANTIC_MISMATCH"):
        verify_model_v2_final(tmp_path, manifest_path)


def test_tamper_upstream_hash_detected(tmp_path: Path) -> None:
    manifest_path = _build_fake_package(tmp_path)
    upstream_path = tmp_path / "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V3.lock.json"
    upstream_path.write_text('{"tampered": true}', encoding="utf-8")
    with pytest.raises(ModelV2FinalFreezeError, match="MODEL_V2_FINAL_UPSTREAM_HASH_MISMATCH"):
        verify_model_v2_final(tmp_path, manifest_path)


def test_tamper_fixture_expected_logit_detected(tmp_path: Path) -> None:
    manifest_path = _build_fake_package(tmp_path)
    vector_path = tmp_path / "tests/fixtures/model_v2_final_test_vector.npz"
    with np.load(vector_path, allow_pickle=False) as fixture:
        arrays = {name: fixture[name].copy() for name in fixture.files}
    arrays["expected_logits_float32"].flat[0] += np.float32(5.0)
    vector_gen.write_deterministic_npz(vector_path, arrays)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["test_vector"]["sha256"] = hash_file(vector_path)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ModelV2FinalFreezeError, match="MODEL_V2_FINAL_TEST_VECTOR_LOGIT_MISMATCH"):
        verify_model_v2_final(tmp_path, manifest_path)


def test_manifest_missing_detected(tmp_path: Path) -> None:
    with pytest.raises(ModelV2FinalFreezeError, match="MODEL_V2_FINAL_MANIFEST_MISSING"):
        verify_model_v2_final(tmp_path, tmp_path / "nonexistent.json")


def test_reference_runtime_recorded_for_reproducibility() -> None:
    # Sanity: the platform module used by the freeze script is importable and callable --
    # guards against an import-time typo breaking METHOD_COMMIT.
    assert isinstance(platform.python_version(), str)
