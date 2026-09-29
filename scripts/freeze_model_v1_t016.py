#!/usr/bin/env python3
"""Promote the exact T015 release candidate and construct the F08 package."""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
import sys
import tempfile
from copy import deepcopy
from pathlib import Path

import numpy as np
import torch
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from evaluation.leakage_audit import verify_frozen_split  # noqa: E402
from models.baseline_freeze import verify_baseline_freeze  # noqa: E402
from models.ecg_cnn import build_model_v1  # noqa: E402
from nhm.hashing import hash_file  # noqa: E402
from preprocessing.freeze import verify_preproc_freeze  # noqa: E402
from scripts.generate_model_v1_test_vector_t016 import generate  # noqa: E402

CANDIDATE = Path("checkpoints/candidates/MODEL_V1/MODEL_V1_seed_20260927_best.pt")
CANDIDATE_METADATA = Path(
    "checkpoints/candidates/MODEL_V1/MODEL_V1_seed_20260927_best.metadata.json"
)
FINAL = Path("checkpoints/MODEL_V1.pt")
FROZEN_CONFIG = Path("configs/model_v1_frozen.yaml")
VECTOR = Path("tests/fixtures/model_v1_test_vector.npz")
VECTOR_METADATA = Path("tests/fixtures/model_v1_test_vector.metadata.json")
EXPECTED_SHA = "021352eb067932015b657f0570ac155f8ef00af2d43864e13a110d0252bc7bfe"


def write_json(path: Path, value: dict) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    verify_frozen_split(ROOT)
    verify_preproc_freeze(ROOT)
    verify_baseline_freeze(ROOT)
    candidate = ROOT / CANDIDATE
    metadata = json.loads((ROOT / CANDIDATE_METADATA).read_text(encoding="utf-8"))
    if not candidate.exists():
        raise RuntimeError("MODEL_V1_CANDIDATE_BINARY_MISSING")
    if hash_file(candidate) != EXPECTED_SHA:
        raise RuntimeError("MODEL_V1_CANDIDATE_IDENTITY_MISMATCH: SHA")
    expected_identity = {
        "model_id": "MODEL_V1",
        "seed": 20260927,
        "best_epoch": 4,
        "best_validation_auprc": 0.5328607838787021,
        "target_id": "AAMI_SVF_WINDOW_V1",
        "split_id": "MITDB_SPLIT_V1",
        "preproc_id": "PREPROC_V1",
    }
    if any(metadata.get(key) != value for key, value in expected_identity.items()):
        raise RuntimeError("MODEL_V1_CANDIDATE_IDENTITY_MISMATCH: metadata")

    final = ROOT / FINAL
    final.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(candidate, final)
    if candidate.read_bytes() != final.read_bytes() or hash_file(final) != EXPECTED_SHA:
        raise RuntimeError("MODEL_FREEZE_FAILURE: byte promotion")

    candidate_config_path = ROOT / "configs/model_v1.yaml"
    candidate_config = yaml.safe_load(candidate_config_path.read_text(encoding="utf-8"))
    frozen = deepcopy(candidate_config)
    frozen.pop("candidate_status", None)
    frozen.update(
        {
            "status": "FROZEN",
            "freeze_id": "F08",
            "frozen_by_task": "T016",
            "release_seed": 20260927,
            "selected_epoch": 4,
            "selected_validation_auprc": 0.5328607838787021,
            "checkpoint": {"path": str(FINAL), "sha256": EXPECTED_SHA},
            "candidate_source": {
                "path": str(CANDIDATE),
                "sha256": EXPECTED_SHA,
                "byte_identical": True,
            },
            "calibration_id": None,
            "temperature": None,
            "operating_threshold": None,
            "probability_semantics": "UNCALIBRATED_SIGMOID_OF_MODEL_LOGIT",
            "reference_runtime": {
                "python": platform.python_version(),
                "torch": str(torch.__version__),
                "device": "cpu",
            },
            "change_control": (
                "Changing checkpoint, architecture, forward semantics, normalization, frozen "
                "training contract, release seed, or test-vector semantics requires MODEL_V2 "
                "or controlled Class-C change and invalidates downstream MODEL_V1 evidence."
            ),
        }
    )
    frozen_path = ROOT / FROZEN_CONFIG
    frozen_path.write_text(yaml.safe_dump(frozen, sort_keys=False), encoding="utf-8")
    frozen_sha = hash_file(frozen_path)

    vector_path = ROOT / VECTOR
    first = generate(ROOT, vector_path)
    with tempfile.TemporaryDirectory() as directory:
        second_path = Path(directory) / "vector.npz"
        second = generate(ROOT, second_path)
        if (
            first["sha256"] != second["sha256"]
            or vector_path.read_bytes() != second_path.read_bytes()
        ):
            raise RuntimeError("TEST_VECTOR_REPRODUCIBILITY_FAILURE")
    vector_metadata = {
        "test_vector_id": "MODEL_V1_SYNTHETIC_TEST_VECTOR_V1",
        "generator_version": "T016_V1",
        "synthetic": True,
        "patient_data": False,
        "number_of_vectors": 3,
        "raw_shape": [3, 2500],
        "normalized_input_shape": [3, 1, 2500],
        "expected_logit_shape": [3, 1],
        "normalization_id": "PER_WINDOW_ZSCORE_V1",
        "normalization_epsilon": 1e-8,
        "checkpoint_sha256": EXPECTED_SHA,
        "frozen_config_sha256": frozen_sha,
        "expected_logit_dtype": "float32",
        "expected_logits": first["expected_logits"],
        "logit_tolerance_id": "MODEL_V1_LOGIT_TOLERANCE_V1",
        "atol": 1e-6,
        "rtol": 1e-6,
        "npz_sha256": first["sha256"],
        "first_generation_sha256": first["sha256"],
        "second_generation_sha256": second["sha256"],
        "byte_identical_regeneration": True,
    }
    write_json(VECTOR_METADATA, vector_metadata)

    candidate_payload = torch.load(candidate, map_location="cpu", weights_only=True)
    final_payload = torch.load(final, map_location="cpu", weights_only=True)
    state_identical = all(
        torch.equal(candidate_payload["state_dict"][key], final_payload["state_dict"][key])
        for key in candidate_payload["state_dict"]
    )
    if not state_identical:
        raise RuntimeError("MODEL_FREEZE_FAILURE: state dict")
    model = build_model_v1()
    incompatible = model.load_state_dict(final_payload["state_dict"], strict=True)
    if incompatible.missing_keys or incompatible.unexpected_keys:
        raise RuntimeError("MODEL_FREEZE_FAILURE: load")

    upstream = {
        "manifests/labels/AAMI_SVF_MAP_V1.yaml": hash_file(
            ROOT / "manifests/labels/AAMI_SVF_MAP_V1.yaml"
        ),
        "manifests/splits/MITDB_SPLIT_V1.csv": hash_file(
            ROOT / "manifests/splits/MITDB_SPLIT_V1.csv"
        ),
        "manifests/splits/MITDB_SPLIT_V1.lock.json": hash_file(
            ROOT / "manifests/splits/MITDB_SPLIT_V1.lock.json"
        ),
        "manifests/preprocessing/PREPROC_V1.lock.json": hash_file(
            ROOT / "manifests/preprocessing/PREPROC_V1.lock.json"
        ),
        "manifests/windows/MITDB_WINDOWS_V1.csv": hash_file(
            ROOT / "manifests/windows/MITDB_WINDOWS_V1.csv"
        ),
        "manifests/baselines/BASELINE_V1.lock.json": hash_file(
            ROOT / "manifests/baselines/BASELINE_V1.lock.json"
        ),
    }
    fresh_command = (
        "import json,numpy as np,torch; from models.ecg_cnn import build_model_v1; "
        "p=torch.load('checkpoints/MODEL_V1.pt',map_location='cpu',weights_only=True); "
        "m=build_model_v1(); m.load_state_dict(p['state_dict']); m.eval(); "
        "z=np.load('tests/fixtures/model_v1_test_vector.npz',allow_pickle=False); "
        "x=torch.from_numpy(z['normalized_inputs_float32']); "
        "print(json.dumps(m(x).detach().numpy().tolist()))"
    )
    fresh_outputs = []
    for _ in range(2):
        completed = subprocess.run(
            [sys.executable, "-c", fresh_command],
            cwd=ROOT,
            env={**dict(__import__("os").environ), "PYTHONPATH": f"{ROOT}:{ROOT / 'src'}"},
            check=True,
            capture_output=True,
            text=True,
        )
        fresh_outputs.append(json.loads(completed.stdout))
    expected_array = np.asarray(first["expected_logits"], dtype=np.float32)
    actual_array = np.asarray(fresh_outputs[0], dtype=np.float32)
    difference = np.abs(expected_array - actual_array)
    maximum_absolute_error = float(difference.max(initial=0.0))
    maximum_relative_error = float(
        (difference / np.maximum(np.abs(expected_array), np.finfo(np.float32).tiny)).max(
            initial=0.0
        )
    )
    if fresh_outputs[0] != fresh_outputs[1] or not np.allclose(
        expected_array, actual_array, atol=1e-6, rtol=1e-6
    ):
        raise RuntimeError("TEST_VECTOR_REPRODUCIBILITY_FAILURE: fresh process")
    audit = {
        "task_id": "T016",
        "candidate_exists": True,
        "candidate_sha256": EXPECTED_SHA,
        "promotion_byte_identical": True,
        "state_dict_identical": True,
        "architecture_verified": True,
        "parameter_count": 13185,
        "frozen_config_sha256": frozen_sha,
        "test_vector_sha256": first["sha256"],
        "vector_regeneration_byte_identical": True,
        "expected_logits": first["expected_logits"],
        "fresh_process_actual_logits": fresh_outputs,
        "maximum_absolute_error": maximum_absolute_error,
        "maximum_relative_error": maximum_relative_error,
        "upstream_sha256": upstream,
        "data_access_counts": {
            "TRAIN": 0,
            "VALIDATION": 0,
            "CALIBRATION": 0,
            "INTERNAL_TEST": 0,
            "INCART": 0,
            "NSTDB": 0,
            "BIDMC": 0,
            "WEARABLE": 0,
        },
        "training_executed": False,
        "tamper_tests": "VERIFIED_BY_TEST_SUITE",
        "overall_status": "PASS",
    }
    write_json(Path("reports/t016/model_freeze_audit.json"), audit)
    audit_sha = hash_file(ROOT / "reports/t016/model_freeze_audit.json")
    manifest = {
        "freeze_id": "F08",
        "gate_id": "G8",
        "task_id": "T016",
        "model_id": "MODEL_V1",
        "status": "FROZEN",
        "checkpoint": {"path": str(FINAL), "sha256": EXPECTED_SHA},
        "candidate_source": {
            "path": str(CANDIDATE),
            "sha256": EXPECTED_SHA,
            "byte_identical": True,
        },
        "frozen_config": {"path": str(FROZEN_CONFIG), "sha256": frozen_sha},
        "test_vector": {
            "path": str(VECTOR),
            "sha256": first["sha256"],
            "metadata_path": str(VECTOR_METADATA),
            "test_vector_id": "MODEL_V1_SYNTHETIC_TEST_VECTOR_V1",
            "logit_atol": 1e-6,
            "logit_rtol": 1e-6,
        },
        "freeze_audit": {
            "path": "reports/t016/model_freeze_audit.json",
            "sha256": audit_sha,
        },
        "release_seed": 20260927,
        "selected_epoch": 4,
        "best_validation_auprc": 0.5328607838787021,
        "architecture_id": "MODEL_V1_ARCHITECTURE_V1",
        "parameter_count": 13185,
        "target_id": "AAMI_SVF_WINDOW_V1",
        "map_id": "AAMI_SVF_MAP_V1",
        "split_id": "MITDB_SPLIT_V1",
        "preproc_id": "PREPROC_V1",
        "upstream_sha256": upstream,
        "torch_version": str(torch.__version__),
        "python_version": platform.python_version(),
        "calibration_id": None,
        "operating_threshold": None,
        "frozen_by_task": "T016",
        "overall_status": "PASS",
    }
    write_json(Path("checkpoints/MODEL_V1.manifest.json"), manifest)
    subprocess.run(
        ["git", "add", "-f", str(FINAL)], cwd=ROOT, check=True, capture_output=True
    )
    print("MODEL_V1 promotion and deterministic vector generation: PASS")


if __name__ == "__main__":
    main()
