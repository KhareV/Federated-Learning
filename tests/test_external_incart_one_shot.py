from __future__ import annotations

import json
from pathlib import Path

import pytest

from evaluation.external_incart import (
    ExternalIncartError,
    assert_external_not_consumed,
    guard_status,
)


def test_guard_allows_absent_state(tmp_path: Path) -> None:
    assert guard_status(tmp_path) == "NOT_STARTED"
    assert_external_not_consumed(tmp_path)


@pytest.mark.parametrize(
    ("status", "message"),
    [
        ("RUN_STARTED", "EXTERNAL_EVALUATION_INTERRUPTED"),
        ("COMPLETED", "EXTERNAL_INCART_ALREADY_CONSUMED"),
    ],
)
def test_guard_fails_closed(tmp_path: Path, status: str, message: str) -> None:
    path = tmp_path / "artifacts/external_incart_access_v1.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"status": status}), encoding="utf-8")
    with pytest.raises(ExternalIncartError, match=message):
        assert_external_not_consumed(tmp_path)
