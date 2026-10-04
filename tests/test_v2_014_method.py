"""V2-014 method tests: protocol content, harness discipline (static), control-plane prerequisite
correction, clean-clone test gating, lock integrity and (when present) the committed evidence."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import yaml

from nhm.hashing import hash_file
from scripts import verify_v2_014_evidence as verifier
from tests import conftest as gating

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = yaml.safe_load((ROOT / "configs/model_v2/complete_repro_protocol_v1.yaml").read_text())


def test_protocol_defines_four_categories_and_forbidden_reruns() -> None:
    assert set(PROTOCOL["evidence_categories"]) == {
        "A_tracked_artifact_identity", "B_stored_evidence_scientific_reconstruction",
        "C_executable_software_and_synthetic_reproduction", "D_full_repository_regression"}
    text = " ".join(PROTOCOL["must_not_rerun"])
    for item in ("architecture search", "CAL_V2 fitting", "one-shot checkpoint inference",
                 "50-round", "real-TRAIN SecAgg"):
        assert item in text
    assert PROTOCOL["gateway_reexport"]["BYTE_IDENTICAL_REEXPORT_REQUIRED"] is False
    assert PROTOCOL["gateway_reexport"]["SEMANTIC_REEXPORT_REQUIRED"] is True
    assert PROTOCOL["operational_default"] == "MODEL_V1"
    assert "4096" in PROTOCOL["secagg_exploration_disclosure"]
    assert "no exploratory" not in PROTOCOL["secagg_exploration_disclosure"].lower()


def test_harness_static_discipline() -> None:
    source = (ROOT / "scripts/run_v2_014_clean_repro.py").read_text()
    assert '["git", "clone", remote' in source and "--detach" in source
    assert '["npm", "ci"]' in source and '"--no-deps"' in source
    assert "worktree" not in source.replace("worktree_used", "").replace(
        "not worktree", "").replace("fresh_clone_is_not_worktree", "").replace(
        "git_dir_is_directory_not_worktree_file", "").replace("or reused", "")
    assert "shutil.copy" not in source and "rsync" not in source
    assert '"npm", "install"' not in source
    env_line = source[source.index("self.env = {"):source.index("self.raw =")]
    assert "PYTHONPATH" not in env_line and "NODE_PATH" not in env_line
    assert '"PYTHONNOUSERSITE": "1"' in env_line


def test_clone_checks_never_open_real_data_or_retrain() -> None:
    text = (ROOT / "scripts/v2_014_clone_checks.py").read_text()
    for banned in ("load_population", "guarded_population", "train_local_epoch", "fit_cal",
                   "internal_test_once", "external-incart-once"):
        assert banned not in text
    recon = (ROOT / "scripts/v2_014_fl_dev_reconstruct.py").read_text()
    assert "guarded_population" not in recon and "torch" not in recon


def test_control_plane_prerequisite_correction_is_prospective() -> None:
    with (ROOT / "manifests/model_v2/task_registry_v1.csv").open(newline="") as handle:
        tasks = {r["task_id"]: r for r in csv.DictReader(handle)}
    prerequisites = tasks["V2-014"]["prerequisites"].split(";")
    assert prerequisites[:2] == ["V2-001", "V2-013"] and "V2-FL-005" in prerequisites
    with (ROOT / "manifests/model_v2/gate_registry_v1.csv").open(newline="") as handle:
        gates = {r["gate_id"]: r for r in csv.DictReader(handle)}
    purpose = gates["V2G13"]["purpose"]
    for phrase in ("central MODEL_V2 lineage", "federated MODEL_V2 lineage",
                   "SecAgg+ engineering evidence", "WEARABLE_SIM virtual-client FL system path",
                   "frontend/runtime reproducibility"):
        assert phrase in purpose


def test_clean_clone_gating_only_skips_absent_inputs() -> None:
    for prefix, patterns in gating.GATES:
        path = ROOT / prefix.split("::")[0]
        assert path.exists(), prefix
        assert prefix.split("::")[1].split("[")[0] in path.read_text(), prefix
        assert patterns
    assert gating._missing(("this/does/not/exist/*.dat",)) == ["this/does/not/exist/*.dat"]
    assert gating._missing(("pyproject.toml",)) == []


def test_lock_binds_method_files_and_excludes_lifecycle_test() -> None:
    lock = json.loads(
        (ROOT / "artifacts/MODEL_V2_COMPLETE_REPRO_PROTOCOL_V1.lock.json").read_text())
    assert lock["lifecycle_test_bound"] is False
    assert not any("current_lifecycle" in p for p in lock["bound_artifacts"])
    for path, digest in lock["bound_artifacts"].items():
        assert hash_file(ROOT / path) == digest, path
    assert "requirements-dev.lock" in lock["bound_artifacts"]
    assert "frontend/package-lock.json" in lock["bound_artifacts"]


def test_evidence_verifier_passes_in_current_state() -> None:
    result = verifier.verify()
    assert result["status"] == "PASS", result
    assert result["lock_drift"] == []
