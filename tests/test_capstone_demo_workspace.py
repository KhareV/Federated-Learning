# ruff: noqa: E501
"""CAP-010: CAPSTONE_DEMO_WORKSPACE_V1 (isolation, sentinel, fresh/resume, safe reset, log secret scan)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.capstone_demo_workspace import (
    ROOT,
    SENTINEL,
    Workspace,
    WorkspaceError,
    scan_logs_for_secrets,
)


def test_fresh_workspace_is_outside_the_repository_and_carries_a_sentinel(tmp_path) -> None:
    ws = Workspace.create_fresh(tmp_path / "demo")
    assert ROOT not in ws.path.resolve().parents and ws.path.resolve() not in ROOT.parents
    manifest = json.loads((ws.path / SENTINEL).read_text())
    assert manifest["workspace_version"] == "CAPSTONE_DEMO_WORKSPACE_V1" and manifest["product_api"] == "CAPSTONE_PRODUCT_API_V1_3"
    assert manifest["auth_mode"] == "DEMO" and manifest["repository_commit"] and set(manifest["paths"]) == {"database", "federation_artifacts", "candidate_artifacts", "logs"}
    for sub in ("federation", "candidates", "logs"):
        assert (ws.path / sub).is_dir()
    assert ws.db.parent == ws.path


def test_default_fresh_workspace_is_a_system_temp_directory() -> None:
    ws = Workspace.create_fresh(None)
    try:
        assert ROOT not in ws.path.resolve().parents and ws.path.name.startswith("nhm-faculty-demo-")
    finally:
        Workspace.reset(ws.path)


def test_a_workspace_inside_the_repository_is_refused() -> None:
    for inside in (ROOT / "demo_ws_test", ROOT / "data" / "demo_ws_test"):
        with pytest.raises(WorkspaceError) as error:
            Workspace.create_fresh(inside)
        assert error.value.code == "WORKSPACE_MUST_BE_OUTSIDE_THE_REPOSITORY"
        assert not inside.exists()
    with pytest.raises(WorkspaceError):
        Workspace.open_resume(ROOT)


def test_fresh_mode_never_silently_erases_an_existing_workspace(tmp_path) -> None:
    ws = Workspace.create_fresh(tmp_path / "demo")
    (ws.path / "product.sqlite3").write_text("precious")
    with pytest.raises(WorkspaceError) as error:
        Workspace.create_fresh(ws.path)
    assert error.value.code == "WORKSPACE_NOT_EMPTY_FOR_FRESH_MODE"
    assert (ws.path / "product.sqlite3").read_text() == "precious"
    other = tmp_path / "occupied"
    other.mkdir()
    (other / "x.txt").write_text("user file")
    with pytest.raises(WorkspaceError):
        Workspace.create_fresh(other)
    assert (other / "x.txt").exists()


def test_resume_requires_a_valid_sentinel(tmp_path) -> None:
    (tmp_path / "nosentinel").mkdir()
    with pytest.raises(WorkspaceError) as missing:
        Workspace.open_resume(tmp_path / "nosentinel")
    assert missing.value.code == "WORKSPACE_SENTINEL_MISSING"
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / SENTINEL).write_text("{not json")
    with pytest.raises(WorkspaceError) as invalid:
        Workspace.open_resume(bad)
    assert invalid.value.code == "WORKSPACE_SENTINEL_INVALID"
    wrong = tmp_path / "wrong"
    wrong.mkdir()
    (wrong / SENTINEL).write_text(json.dumps({"workspace_version": "OTHER", "paths": {}}))
    with pytest.raises(WorkspaceError):
        Workspace.open_resume(wrong)
    good = Workspace.create_fresh(tmp_path / "good")
    assert Workspace.open_resume(good.path).path == good.path.resolve()


@pytest.mark.parametrize("target", ["/", "HOME", "ROOT", "ROOT_PARENT", "ROOT_CHILD", "/tmp", "/usr", "RANDOM_NO_SENTINEL"])
def test_unsafe_reset_targets_are_rejected_and_nothing_is_deleted(tmp_path, target) -> None:
    resolved = {"HOME": Path.home(), "ROOT": ROOT, "ROOT_PARENT": ROOT.parent, "ROOT_CHILD": ROOT / "frontend", "RANDOM_NO_SENTINEL": tmp_path / "random"}.get(target, Path(target))
    if target == "RANDOM_NO_SENTINEL":
        resolved.mkdir()
        (resolved / "keep.txt").write_text("x")
    before = sorted(p.name for p in (resolved.iterdir() if resolved.is_dir() else []))[:50]
    with pytest.raises(WorkspaceError) as error:
        Workspace.reset(resolved)
    assert error.value.code in {"UNSAFE_RESET_TARGET", "WORKSPACE_SENTINEL_MISSING"}
    if target in {"/", "HOME", "ROOT", "ROOT_PARENT", "ROOT_CHILD"}:
        assert error.value.code == "UNSAFE_RESET_TARGET"   # refused by path policy, not merely for lacking a sentinel
    if target == "RANDOM_NO_SENTINEL":
        assert error.value.code == "WORKSPACE_SENTINEL_MISSING"
        assert (resolved / "keep.txt").exists()
    assert before == sorted(p.name for p in (resolved.iterdir() if resolved.is_dir() else []))[:50]


def test_reset_deletes_only_the_validated_workspace(tmp_path) -> None:
    ws = Workspace.create_fresh(tmp_path / "demo")
    sibling = tmp_path / "sibling.txt"
    sibling.write_text("untouched")
    (ws.path / "logs" / "x.log").write_text("log")
    Workspace.reset(ws.path)
    assert not ws.path.exists() and sibling.read_text() == "untouched" and tmp_path.exists()
    with pytest.raises(WorkspaceError):
        Workspace.reset(tmp_path / "gone")


def test_log_secret_scan_detects_secrets_and_passes_clean_logs(tmp_path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "product.log").write_text("INFO started\nGET /product/v1/system 200\n")
    assert scan_logs_for_secrets(logs)["clean"] is True
    for leak in ("CLERK_SECRET_KEY=sk_test_abcdef123456", "Authorization: Bearer abcdefghijklmnopqrstuvwxyz", "cookie __session=abc", "tok eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.sig123456"):
        (logs / "leak.log").write_text(leak)
        scan = scan_logs_for_secrets(logs)
        assert scan["clean"] is False and scan["secret_pattern_hits"], leak
