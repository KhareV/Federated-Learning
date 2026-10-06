# ruff: noqa: E501
"""CAP-011: release manifest / policy / verifier library / result import / final split / portability."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from scripts import capstone_release_lib as lib

ROOT = Path(__file__).resolve().parents[1]
POLICY = json.loads((ROOT / "configs/capstone/cap_011_release_policy_v1.json").read_text())
MANIFEST = json.loads((ROOT / lib.MANIFEST_PATH).read_text())
GUIDE = (ROOT / "docs/capstone/CAPSTONE_RELEASE_GUIDE_V1.md").read_text()


def test_release_manifest_verifies_against_the_tracked_artifacts() -> None:
    result = lib.verify_manifest(MANIFEST, ROOT)
    assert result["ok"], result["failures"]
    assert MANIFEST["release_id"] == "CAPSTONE_RELEASE_V1" and MANIFEST["released_monitoring"]["default_model"] == "MODEL_V2_FINAL"
    assert MANIFEST["candidate"]["production_deployed"] is False and MANIFEST["hardware"]["physical_hardware_available"] is False
    for key in ("checkpoints/MODEL_V2_FINAL.pt", "artifacts/CAL_V2.json", "artifacts/DEFAULT_RUNTIME_BINDING_V2.lock.json", "artifacts/SOFTWARE_SYSTEM_V2.lock.json",
                "artifacts/capstone/CAPSTONE_UI_V1_2.lock.json", "artifacts/capstone/CAPSTONE_RESEARCH_EVIDENCE_CATALOG_V1.lock.json", "artifacts/capstone/CAPSTONE_FACULTY_DEMO_PROTOCOL_V1.lock.json"):
        assert key in MANIFEST["key_artifacts"], key


def test_release_policy_is_frozen_and_has_no_manual_override() -> None:
    assert POLICY["status"] == "FROZEN_PRE_RELEASE_POLICY" and POLICY["manual_override_allowed"] is False and POLICY["waivers_allowed"] is False
    assert POLICY["ci"].startswith("NOT queried")
    assert POLICY["clean_clone_test_gating"]["unexpected_skips_allowed"] == 0 and POLICY["clean_clone_test_gating"]["failures_allowed"] == 0


def test_release_policy_blockers_and_limitations_are_complete() -> None:
    assert [b["id"] for b in POLICY["hard_blockers"]] == [f"B{i:02d}" for i in range(1, 24)]
    assert len(POLICY["limitations"]) == 21 and set(x["text"] for x in POLICY["limitations"]) == set(MANIFEST["limitations"])
    protocol = json.loads((ROOT / "configs/capstone/cap_011_release_protocol_v1.json").read_text())
    mapped = {b for row in protocol["capg10_criteria"] for b in row["blockers"]}
    assert mapped == {b["id"] for b in POLICY["hard_blockers"]}   # every hard blocker is enforced by at least one frozen criterion
    assert protocol["criteria_count"] == len(protocol["capg10_criteria"]) == 136


def test_dependency_lock_hashes_are_bound_by_the_manifest() -> None:
    assert set(MANIFEST["dependency_locks"]) == {"requirements-dev.lock", "requirements-capstone-auth.lock", "pyproject.toml", "frontend/package.json", "frontend/package-lock.json",
                                                 "frontend/clerk-sdk/package.json", "frontend/clerk-sdk/package-lock.json"}
    mutated = json.loads(json.dumps(MANIFEST))
    mutated["dependency_locks"]["requirements-dev.lock"] = "0" * 64
    assert not lib.verify_manifest(mutated, ROOT)["ok"]


def test_verify_checkout_requires_the_exact_full_sha() -> None:
    sha = "a" * 40
    assert lib.verify_checkout(sha, sha)["ok"]
    assert not lib.verify_checkout("b" * 40, sha)["ok"]
    assert "target_not_full_sha" in lib.verify_checkout("main", "main")["failures"]       # a branch name alone is never accepted
    assert "target_not_full_sha" in lib.verify_checkout("abc1234", "abc1234")["failures"]


def test_clone_result_import_rejects_wrong_target_sha_and_malformed_results() -> None:
    sha = "a" * 40
    good = {"release_target_sha": sha, "label": "A", "status": "PASS", "kind": "demo"}
    assert lib.verify_clone_result(good, sha)["ok"]
    assert "release_target_sha_mismatch" in lib.verify_clone_result({**good, "release_target_sha": "b" * 40}, sha)["failures"]
    assert not lib.verify_clone_result({"label": "A"}, sha)["ok"]
    assert "status_malformed" in lib.verify_clone_result({**good, "status": "MAYBE"}, sha)["failures"]
    assert not lib.verify_clone_result([], sha)["ok"]


def _repo(files: dict[str, str]) -> Path:
    d = Path(tempfile.mkdtemp(prefix="caprel_"))
    for args in (["init", "-q"], ["config", "user.email", "t@x"], ["config", "user.name", "t"]):
        subprocess.run(["git", *args], cwd=d, check=True, capture_output=True)
    for rel, body in files.items():
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        (d / rel).write_text(body)
    subprocess.run(["git", "add", "-A"], cwd=d, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=d, check=True, capture_output=True)
    return d


def test_final_diff_allows_only_evidence_and_control_plane_paths() -> None:
    d = _repo({"frontend/src/a.svelte": "a", "manifests/capstone/task_registry_v1.csv": "t", "reports/capstone/cap_011/e.json": "{}"})
    try:
        base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=d, capture_output=True, text=True).stdout.strip()
        (d / "reports/capstone/cap_011/new.json").write_text("{}")
        (d / "manifests/capstone/task_registry_v1.csv").write_text("t2")
        assert lib.verify_final_diff(d, base)["ok"]                    # working tree: evidence + registries only
        (d / "scripts").mkdir()
        (d / "scripts/verify_capstone_release_v1.py").write_text("x")
        assert not lib.verify_final_diff(d, base)["ok"]                # a release executable is a violation
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_portability_audit_finds_no_absolute_developer_paths() -> None:
    assert lib.portability_audit(ROOT)["ok"], lib.portability_audit(ROOT)["hits"]
    d = _repo({"scripts/run_capstone_x.py": "ROOT = '/Users/someone/work'"})
    try:
        assert not lib.portability_audit(d)["ok"]
    finally:
        shutil.rmtree(d, ignore_errors=True)
    assert lib.case_audit(ROOT)["ok"]


@pytest.mark.parametrize("sentence", [
    "The release includes validated physical wearable integration.", "The release is ready for clinical use.", "The installation is air-gapped.",
    "The release reproduces the raw-data scientific results.", "The candidate is deployed to production.", "SecAgg provides differential privacy.",
    "The federation connects eight hospitals.", "A personal model is trained for each user.", "The release is HIPAA compliant.", "Windows and Linux are fully supported.",
])
def test_release_claim_audit_rejects_every_overclaim(sentence) -> None:
    assert lib.audit_release_text(GUIDE)["ok"]
    assert not lib.audit_release_text(GUIDE + "\n\n" + sentence + "\n")["ok"]
