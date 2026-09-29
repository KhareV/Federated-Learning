from __future__ import annotations

import json
from pathlib import Path

import pytest

from evaluation.internal_test import InternalTestError, create_run_started_guard


def audit() -> dict:
    return {"pre_access_method_commit": "synthetic", "method_artifact_sha256": {}}


def test_completed_guard_blocks_second_run(tmp_path: Path) -> None:
    (tmp_path / "artifacts").mkdir()
    (tmp_path / "artifacts/internal_test_access_v1.json").write_text(
        json.dumps({"status": "COMPLETED"}), encoding="utf-8"
    )
    with pytest.raises(InternalTestError, match="INTERNAL_TEST_ALREADY_CONSUMED"):
        create_run_started_guard(tmp_path, audit())


def test_interrupted_guard_blocks_automatic_retry(tmp_path: Path) -> None:
    (tmp_path / "artifacts").mkdir()
    (tmp_path / "artifacts/internal_test_access_v1.json").write_text(
        json.dumps({"status": "RUN_STARTED"}), encoding="utf-8"
    )
    with pytest.raises(InternalTestError, match="INTERNAL_TEST_RUN_INTERRUPTED"):
        create_run_started_guard(tmp_path, audit())

