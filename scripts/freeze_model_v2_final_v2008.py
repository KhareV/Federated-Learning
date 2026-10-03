#!/usr/bin/env python3
"""V2-008 Section 32: execute the MODEL_V2_FINAL scientific freeze. Mirrors
scripts/freeze_model_v1_t016.py's F08 promotion pattern exactly (byte copy, frozen config,
test-vector generation + regeneration-reproducibility, state-dict identity check, two-fresh-
process verification, manifest) -- with the mandatory status-distinction fields from Section
7 bound throughout: this is a SCIENTIFIC freeze only; promotion_eligible stays false and
operational_lineage stays MODEL_V1. No waveform/patient data is read anywhere in this script.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import torch
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from models.model_v2_architectures import ModelV2TcnMean, count_trainable_parameters  # noqa: E402
from nhm.hashing import hash_file  # noqa: E402
from scripts.generate_model_v2_final_test_vector_v2008 import generate  # noqa: E402

CANDIDATE = Path("checkpoints/model_v2/v2_007_official_validation/V2-007-TCNMEAN-S20260927_best.pt")
FINAL = Path("checkpoints/MODEL_V2_FINAL.pt")
FROZEN_CONFIG = Path("configs/model_v2_final_frozen.yaml")
VECTOR = Path("tests/fixtures/model_v2_final_test_vector.npz")
VECTOR_METADATA = Path("tests/fixtures/model_v2_final_test_vector.metadata.json")
MANIFEST = Path("checkpoints/MODEL_V2_FINAL.manifest.json")
EXPECTED_SHA = "89418edcc2c13f0edd9a36666bac560ad922dd4700b4b6dd19b56d067d4eff9b"
EXPECTED_EPOCH = 5
EXPECTED_PARAMETER_COUNT = 57553
OUT_DIR = ROOT / "reports/model_v2/v2_008"

UPSTREAM_PATHS = [
    "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V3.lock.json",
    "manifests/model_v2/MODEL_V2_FINALIST_SHORTLIST_V1.lock.json",
    "manifests/model_v2/MODEL_V2_OFFICIAL_VALIDATION_V1.lock.json",
    "manifests/model_v2/MODEL_V2_VALIDATION_DECISION_V1.lock.json",
    "manifests/model_v2/MODEL_V2_VALIDATION_BOOTSTRAP_DRAWS_V1.lock.json",
    "manifests/model_v2/cv/MITDB_TRAIN_FINAL_INNER_V2_V1.csv",
    "reports/model_v2/v2_007/official_validation_predictions.csv",
    "reports/model_v2/v2_007/promotion_decision.json",
    "reports/model_v2/v2_007/finalist_selection.json",
]


def write_json(path: Path, value: dict) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    candidate = ROOT / CANDIDATE
    if not candidate.exists():
        print("V2-008 = BLOCKED_RELEASE_CHECKPOINT_BYTES_UNAVAILABLE")
        raise SystemExit(1)
    observed_sha = hash_file(candidate)
    if observed_sha != EXPECTED_SHA:
        raise RuntimeError(f"MODEL_V2_FINAL_SOURCE_IDENTITY_MISMATCH: {observed_sha}")

    v2_007_rows = json.loads(
        (ROOT / "reports/model_v2/v2_007/validation_ready_checkpoints.json").read_text(
            encoding="utf-8"
        )
    )
    source_row = next(
        r for r in v2_007_rows
        if r["architecture_id"] == "MODEL_V2_TCN_MEAN" and r["seed"] == 20260927
    )
    if source_row["selected_epoch"] != EXPECTED_EPOCH:
        raise RuntimeError("MODEL_V2_FINAL_SOURCE_EPOCH_MISMATCH")

    promotion = json.loads(
        (ROOT / "reports/model_v2/v2_007/promotion_decision.json").read_text(encoding="utf-8")
    )
    if promotion["decision"] != "MODEL_V2_NOT_PROMOTED_RELEASE_CI" or promotion[
        "promotion_eligible"
    ]:
        raise RuntimeError("MODEL_V2_FINAL_PROMOTION_DISPOSITION_MISMATCH")

    final = ROOT / FINAL
    final.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(candidate, final)
    if candidate.read_bytes() != final.read_bytes() or hash_file(final) != EXPECTED_SHA:
        raise RuntimeError("MODEL_V2_FINAL_FREEZE_FAILURE: byte promotion")

    candidate_payload = torch.load(candidate, map_location="cpu", weights_only=False)
    final_payload = torch.load(final, map_location="cpu", weights_only=False)
    state_identical = (
        candidate_payload["state_dict"].keys() == final_payload["state_dict"].keys()
        and all(
            torch.equal(candidate_payload["state_dict"][key], final_payload["state_dict"][key])
            for key in candidate_payload["state_dict"]
        )
    )
    if not state_identical:
        raise RuntimeError("MODEL_V2_FINAL_FREEZE_FAILURE: state dict")
    model = ModelV2TcnMean()
    incompatible = model.load_state_dict(final_payload["state_dict"], strict=True)
    if incompatible.missing_keys or incompatible.unexpected_keys:
        raise RuntimeError("MODEL_V2_FINAL_FREEZE_FAILURE: load")
    parameter_count = count_trainable_parameters(model)
    if parameter_count != EXPECTED_PARAMETER_COUNT:
        raise RuntimeError("MODEL_V2_FINAL_FREEZE_FAILURE: parameter count")

    upstream = {rel: hash_file(ROOT / rel) for rel in UPSTREAM_PATHS}

    frozen_config = {
        "model_id": "MODEL_V2_FINAL",
        "parent_architecture": "MODEL_V2_TCN_MEAN",
        "schedule_id": "CONFIG_V2_TCN_MEAN_ORIGINAL_V1",
        "release_seed": 20260927,
        "selected_epoch": EXPECTED_EPOCH,
        "parameter_count": EXPECTED_PARAMETER_COUNT,
        "input_shape": [1, 2500],
        "sampling_rate_hz": 250,
        "window_seconds": 10,
        "stride_seconds": 5,
        "target": "AAMI_SVF_WINDOW_V1",
        "label_map": "AAMI_SVF_MAP_V1",
        "preprocessing": "PREPROC_V1",
        "neural_normalization": "PER_WINDOW_ZSCORE_V1",
        "normalization_formula": "(x - mean(x)) / (std(x) + 1e-8)",
        "output": "RAW_LOGIT",
        "probability": "SIGMOID_ONCE",
        "calibration": "NONE_YET",
        "operating_threshold": "NONE_YET",
        "protocol_v3_lock_sha256": upstream[
            "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V3.lock.json"
        ],
        "shortlist_lock_sha256": upstream[
            "manifests/model_v2/MODEL_V2_FINALIST_SHORTLIST_V1.lock.json"
        ],
        "official_validation_lock_sha256": upstream[
            "manifests/model_v2/MODEL_V2_OFFICIAL_VALIDATION_V1.lock.json"
        ],
        "validation_decision_lock_sha256": upstream[
            "manifests/model_v2/MODEL_V2_VALIDATION_DECISION_V1.lock.json"
        ],
        "final_inner_manifest_sha256": upstream[
            "manifests/model_v2/cv/MITDB_TRAIN_FINAL_INNER_V2_V1.csv"
        ],
        "architecture_source_sha256": hash_file(ROOT / "models/model_v2_architectures.py"),
        "inference_source_sha256": hash_file(ROOT / "models/model_v2_final_freeze.py"),
        "checkpoint": {"path": str(FINAL), "sha256": EXPECTED_SHA},
        "source_checkpoint": {
            "path": str(CANDIDATE), "sha256": EXPECTED_SHA, "byte_identical": True,
        },
        "official_validation_promotion_eligible": False,
        "official_validation_promotion_decision": promotion["decision"],
        "operational_lineage": "MODEL_V1",
        "runtime_acceptance": "NOT_EVALUATED",
        "scientific_final_frozen": True,
        "status": "FROZEN",
        "reference_runtime": {
            "python": platform.python_version(), "torch": str(torch.__version__), "device": "cpu",
        },
        "change_control": (
            "This frozen config is never mutated in place. A corrected scientific freeze "
            "requires a new, additive MODEL_V2_FINAL_V2 successor; this is never an "
            "operational promotion change -- that requires a separate runtime-acceptance "
            "decision (V2-010) which this freeze does not make."
        ),
    }
    frozen_path = ROOT / FROZEN_CONFIG
    frozen_path.write_text(yaml.safe_dump(frozen_config, sort_keys=False), encoding="utf-8")
    frozen_sha = hash_file(frozen_path)

    vector_path = ROOT / VECTOR
    first = generate(ROOT, vector_path, CANDIDATE, EXPECTED_SHA)
    with tempfile.TemporaryDirectory() as directory:
        second_path = Path(directory) / "vector.npz"
        second = generate(ROOT, second_path, CANDIDATE, EXPECTED_SHA)
        if (
            first["sha256"] != second["sha256"]
            or vector_path.read_bytes() != second_path.read_bytes()
        ):
            raise RuntimeError("MODEL_V2_FINAL_TEST_VECTOR_REPRODUCIBILITY_FAILURE")
    vector_metadata = {
        "test_vector_id": "MODEL_V2_FINAL_SYNTHETIC_TEST_VECTOR_V1",
        "generator_version": "V2008_V1",
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
        "logit_tolerance_id": "MODEL_V2_FINAL_LOGIT_TOLERANCE_V1",
        "atol": 1e-7,
        "rtol": 1e-7,
        "npz_sha256": first["sha256"],
        "first_generation_sha256": first["sha256"],
        "second_generation_sha256": second["sha256"],
        "byte_identical_regeneration": True,
    }
    write_json(VECTOR_METADATA, vector_metadata)

    fresh_command = (
        "import json,numpy as np,torch; "
        "from models.model_v2_architectures import ModelV2TcnMean; "
        "p=torch.load('checkpoints/MODEL_V2_FINAL.pt',map_location='cpu',weights_only=False); "
        "m=ModelV2TcnMean(); m.load_state_dict(p['state_dict']); m.eval(); "
        "z=np.load('tests/fixtures/model_v2_final_test_vector.npz',allow_pickle=False); "
        "x=torch.from_numpy(z['normalized_inputs_float32']); "
        "print(json.dumps(m(x).detach().numpy().tolist()))"
    )
    fresh_outputs = []
    for _ in range(2):
        env = dict(os.environ)
        env["PYTHONPATH"] = f"{ROOT}:{ROOT / 'src'}"
        completed = subprocess.run(
            [sys.executable, "-c", fresh_command],
            cwd=ROOT, env=env, check=True, capture_output=True, text=True,
        )
        fresh_outputs.append(json.loads(completed.stdout))

    import numpy as np

    expected_array = np.asarray(first["expected_logits"], dtype=np.float32)
    process_a = np.asarray(fresh_outputs[0], dtype=np.float32)
    process_b = np.asarray(fresh_outputs[1], dtype=np.float32)
    difference_a = np.abs(expected_array - process_a)
    maximum_absolute_error = float(difference_a.max(initial=0.0))
    maximum_relative_error = float(
        (difference_a / np.maximum(np.abs(expected_array), np.finfo(np.float32).tiny)).max(
            initial=0.0
        )
    )
    atol, rtol = 1e-7, 1e-7
    if not (
        np.allclose(expected_array, process_a, atol=atol, rtol=rtol)
        and np.allclose(expected_array, process_b, atol=atol, rtol=rtol)
        and np.allclose(process_a, process_b, atol=atol, rtol=rtol)
    ):
        raise RuntimeError("MODEL_V2_FINAL_TEST_VECTOR_REPRODUCIBILITY_FAILURE: fresh process")

    freeze_audit = {
        "task_id": "V2-008",
        "source_checkpoint_exists": True,
        "source_checkpoint_sha256": EXPECTED_SHA,
        "promotion_byte_identical": True,
        "state_dict_identical": True,
        "architecture_verified": True,
        "parameter_count": EXPECTED_PARAMETER_COUNT,
        "frozen_config_sha256": frozen_sha,
        "test_vector_sha256": first["sha256"],
        "vector_regeneration_byte_identical": True,
        "expected_logits": first["expected_logits"],
        "process_a_logits": fresh_outputs[0],
        "process_b_logits": fresh_outputs[1],
        "maximum_absolute_error": maximum_absolute_error,
        "maximum_relative_error": maximum_relative_error,
        "tolerance_atol": atol,
        "tolerance_rtol": rtol,
        "upstream_sha256": upstream,
        "data_access_counts": {
            "TRAIN": 0, "VALIDATION": 0, "CALIBRATION": 0, "INTERNAL_TEST": 0,
            "INCART": 0, "NSTDB": 0, "BIDMC": 0, "WEARABLE": 0,
        },
        "training_executed": False,
        "official_validation_promotion_eligible": False,
        "official_validation_promotion_decision": promotion["decision"],
        "operational_lineage": "MODEL_V1",
        "runtime_acceptance": "NOT_EVALUATED",
        "overall_status": "PASS",
    }
    write_json(OUT_DIR / "checkpoint_byte_identity.json", freeze_audit)

    manifest = {
        "model_id": "MODEL_V2_FINAL",
        "scientific_status": "FROZEN",
        "operational_status": "NOT_OPERATIONAL",
        "status": "FROZEN",
        "checkpoint": {"path": str(FINAL), "sha256": EXPECTED_SHA},
        "checkpoint_size_bytes": final.stat().st_size,
        "architecture_id": "MODEL_V2_TCN_MEAN",
        "schedule_id": "CONFIG_V2_TCN_MEAN_ORIGINAL_V1",
        "release_seed": 20260927,
        "selected_epoch": EXPECTED_EPOCH,
        "parameter_count": EXPECTED_PARAMETER_COUNT,
        "frozen_config": {"path": str(FROZEN_CONFIG), "sha256": frozen_sha},
        "test_vector": {
            "path": str(VECTOR), "sha256": first["sha256"],
            "metadata_path": str(VECTOR_METADATA),
            "test_vector_id": "MODEL_V2_FINAL_SYNTHETIC_TEST_VECTOR_V1",
            "logit_atol": atol, "logit_rtol": rtol,
        },
        "target_id": "AAMI_SVF_WINDOW_V1",
        "label_map_id": "AAMI_SVF_MAP_V1",
        "preproc_id": "PREPROC_V1",
        "protocol_v3_lock_sha256": upstream[
            "manifests/model_v2/MODEL_V2_RESEARCH_PROTOCOL_V3.lock.json"
        ],
        "shortlist_lock_sha256": upstream[
            "manifests/model_v2/MODEL_V2_FINALIST_SHORTLIST_V1.lock.json"
        ],
        "official_validation_lock_sha256": upstream[
            "manifests/model_v2/MODEL_V2_OFFICIAL_VALIDATION_V1.lock.json"
        ],
        "validation_decision_lock_sha256": upstream[
            "manifests/model_v2/MODEL_V2_VALIDATION_DECISION_V1.lock.json"
        ],
        "v2_007_continuity_audit_commit": "1c23214f76331fd4cc50b3318e133a164f4c7b58",
        "source_checkpoint": {
            "path": str(CANDIDATE), "sha256": EXPECTED_SHA, "byte_identical": True,
        },
        "promotion_decision": promotion["decision"],
        "promotion_eligible": False,
        "operational_lineage": "MODEL_V1",
        "runtime_acceptance": "NOT_EVALUATED",
        "upstream_sha256": upstream,
        "torch_version": str(torch.__version__),
        "python_version": platform.python_version(),
        "calibration_id": None,
        "operating_threshold": None,
        "overall_status": "PASS",
    }
    write_json(MANIFEST, manifest)

    subprocess.run(["git", "add", "-f", str(FINAL)], cwd=ROOT, check=True, capture_output=True)
    print("MODEL_V2_FINAL scientific freeze and deterministic vector generation: PASS")


if __name__ == "__main__":
    main()
