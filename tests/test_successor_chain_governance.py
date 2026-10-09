# ruff: noqa: E501
"""Negative controls for the successor-aware UI lock chain.

Each test runs the REAL accepted verifiers (``python -m scripts.verify_capstone_ui_v1_9`` etc.) inside a throw-away ``git worktree`` of HEAD
(overlaid with the current governance code), mutates one thing and asserts that verification FAILS. The unmutated worktree must PASS, so a failing
mutation is attributable to that mutation alone."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
OVERLAY_PREFIXES = ("scripts/successor_chain.py", "scripts/capstone_ui_v1_8_successor.py", "scripts/reconcile_ui_lock_chain.py", "scripts/studio_successor_compat.py", "scripts/fl10_successor_compat.py",
                    "artifacts/unified_studio/NHM_UNIFIED_LIVE_FEDERATION_STUDIO_001.lock.json")
FL10_LOCK = "artifacts/fl10/NHM_FL10_001.lock.json"
FINAL_LOCK = "artifacts/final_showcase/NHM_FINAL_SHOWCASE_001.lock.json"


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def run(tree: Path, module: str) -> tuple[int, str]:
    env = {**os.environ, "PYTHONPATH": "src:."}
    env.pop("NHM_GOVERNANCE_GIT_ROOT", None)
    done = subprocess.run([sys.executable, "-m", module], cwd=tree, env=env, capture_output=True, text=True)
    return done.returncode, (done.stdout + done.stderr)


@pytest.fixture(scope="module")
def tree(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("govtree") / "wt"
    git(ROOT, "worktree", "add", "-q", "--detach", str(path), "HEAD")
    for relative in OVERLAY_PREFIXES:  # the governance code under test (and the not-yet-committed lock) may not be in HEAD
        if (ROOT / relative).is_file():
            (path / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, path / relative)
    yield path
    git(ROOT, "worktree", "remove", "--force", str(path))


@pytest.fixture()
def clean(tree: Path) -> Path:
    git(tree, "checkout", "-q", "--", ".")
    git(tree, "clean", "-fdq", "--", "frontend/src", "artifacts")
    for relative in OVERLAY_PREFIXES:
        if (ROOT / relative).is_file():
            (tree / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, tree / relative)
    return tree


VERIFIERS = ["scripts.verify_capstone_ui_v1", "scripts.verify_capstone_ui_v1_2", "scripts.verify_capstone_ui_v1_9"]


@pytest.mark.parametrize("module", VERIFIERS)
def test_unmutated_tree_passes_every_old_verifier(clean: Path, module: str) -> None:
    code, out = run(clean, module)
    assert code == 0 and '"PASS"' in out, out[-600:]


@pytest.mark.parametrize("module", VERIFIERS)
def test_unauthorized_frontend_edit_is_rejected(clean: Path, module: str) -> None:
    target = clean / "frontend/src/lib/product/socket.ts"
    target.write_text(target.read_text() + "\n// unauthorized\n")
    code, out = run(clean, module)
    assert code != 0 and "TAMPER" in out, out[-600:]


def test_edit_to_file_bound_by_successor_after_its_lock_is_rejected(clean: Path) -> None:
    target = clean / "frontend/src/lib/product/api.ts"  # legitimately re-pinned by FL10, so a further edit must NOT be accepted
    target.write_text(target.read_text() + "\n// edit after successor lock\n")
    code, out = run(clean, "scripts.verify_capstone_ui_v1_9")
    assert code != 0 and "TAMPER" in out, out[-600:]


def test_new_unbound_frontend_file_is_rejected(clean: Path) -> None:
    (clean / "frontend/src/lib/product/unbound_extra.ts").write_text("export const x = 1;\n")
    code, out = run(clean, "scripts.verify_capstone_ui_v1_9")
    assert code != 0 and "UNBOUND_OR_MISSING" in out, out[-600:]


def test_missing_successor_lock_does_not_authorize_changed_files(clean: Path) -> None:
    (clean / FL10_LOCK).unlink()
    code, out = run(clean, "scripts.verify_capstone_ui_v1_9")
    assert code != 0, out[-600:]


@pytest.mark.parametrize(("field", "value", "reason"), [
    ("predecessor_lock_sha256", "0" * 64, "PREDECESSOR_DIGEST_MISMATCH"),
    ("predecessor_commit", "0" * 40, "PREDECESSOR_COMMIT_MISMATCH"),
    ("lock_id", "NHM_FL10_FORGED", "IDENTITY_OR_STATUS"),
    ("status", "FAIL", "IDENTITY_OR_STATUS"),
    ("historical_locks_edited", True, "SCOPE_DRIFT"),
    ("automatically_pushed", True, "SCOPE_DRIFT"),
    ("candidate_promoted_or_deployed", True, "SCOPE_DRIFT"),
])
def test_forged_successor_lock_is_rejected(clean: Path, field: str, value: object, reason: str) -> None:
    lock = json.loads((clean / FL10_LOCK).read_text())
    lock[field] = value
    (clean / FL10_LOCK).write_text(json.dumps(lock, indent=1, sort_keys=True) + "\n")
    code, out = run(clean, "scripts.verify_capstone_ui_v1_9")
    assert code != 0 and "SUCCESSOR_CHAIN_BROKEN" in out and reason in out, out[-600:]


def test_mutated_predecessor_lock_bytes_are_rejected(clean: Path) -> None:
    path = clean / FINAL_LOCK
    path.write_text(path.read_text() + " ")
    code, out = run(clean, "scripts.verify_capstone_ui_v1_9")
    assert code != 0 and "CHAIN_BROKEN" in out, out[-600:]


def test_mutated_ancestor_lock_is_rejected(clean: Path) -> None:
    path = clean / "artifacts/capstone/CAPSTONE_UI_V1_8.lock.json"
    path.write_text(path.read_text() + " ")
    code, out = run(clean, "scripts.verify_capstone_ui_v1_9")
    assert code != 0, out[-600:]


def test_reconciliation_has_no_unauthorized_file() -> None:
    sys.path.insert(0, str(ROOT))
    from scripts.reconcile_ui_lock_chain import reconcile

    result = reconcile()
    assert result["summary"].get("UNAUTHORIZED", 0) == 0, result["summary"]
    assert result["summary"]["AUTHORIZED_BY_SUCCESSOR"] > 0


STUDIO_LOCK = "artifacts/unified_studio/NHM_UNIFIED_LIVE_FEDERATION_STUDIO_001.lock.json"


@pytest.mark.skipif(not (ROOT / STUDIO_LOCK).exists(), reason="the Studio lock is created at the end of the work")
@pytest.mark.parametrize(("field", "value", "reason"), [
    ("predecessor_lock_sha256", "0" * 64, "PREDECESSOR_DIGEST_MISMATCH"),
    ("predecessor_commit", "0" * 40, "PREDECESSOR_COMMIT_MISMATCH"),
    ("lock_id", "NHM_UNIFIED_LIVE_FEDERATION_STUDIO_FORGED", "IDENTITY_OR_STATUS"),
    ("historical_locks_edited", True, "SCOPE_DRIFT"),
    ("frozen_scientific_evidence_edited", True, "SCOPE_DRIFT"),
])
def test_forged_studio_successor_lock_is_rejected_by_the_old_verifiers(clean: Path, field: str, value: object, reason: str) -> None:
    lock = json.loads((clean / STUDIO_LOCK).read_text())
    lock[field] = value
    (clean / STUDIO_LOCK).write_text(json.dumps(lock, indent=1, sort_keys=True) + "\n")
    code, out = run(clean, "scripts.verify_capstone_ui_v1_9")
    assert code != 0 and "SUCCESSOR_CHAIN_BROKEN" in out and reason in out, out[-600:]


@pytest.mark.skipif(not (ROOT / STUDIO_LOCK).exists(), reason="the Studio lock is created at the end of the work")
def test_edit_after_the_studio_lock_is_rejected(clean: Path) -> None:
    target = clean / "frontend/src/lib/product/studio/store.svelte.ts"       # bound by the Studio successor: a further edit must not be accepted
    target.write_text(target.read_text() + "\n// edit after the Studio lock\n")
    code, out = run(clean, "scripts.verify_capstone_ui_v1_9")
    assert code != 0 and ("TAMPER" in out or "UNBOUND" in out), out[-600:]
