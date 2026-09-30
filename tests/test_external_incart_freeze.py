from __future__ import annotations

import json
from pathlib import Path

import pytest

from evaluation.external_incart import (
    ExternalIncartError,
    assert_external_not_consumed,
    verify_external_freeze,
)
from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]


def test_canonical_external_freeze_verifies_prediction_only() -> None:
    result = verify_external_freeze(ROOT)
    assert result["status"] == "PASS"
    assert result["freeze_id"] == "F11"
    assert result["model_inference_repeated"] is False


def test_completed_external_guard_blocks_second_run() -> None:
    with pytest.raises(ExternalIncartError, match="EXTERNAL_INCART_ALREADY_CONSUMED"):
        assert_external_not_consumed(ROOT)


def test_method_hashes_equal_pre_access_values() -> None:
    audit = json.loads((ROOT / "reports/t020/pre_access_audit.json").read_text())
    for relative, expected in audit["method_artifact_sha256"].items():
        assert hash_file(ROOT / relative) == expected


def test_external_verifier_is_hash_bound_and_fail_closed() -> None:
    source = (ROOT / "evaluation/external_incart.py").read_text(encoding="utf-8")
    assert "EXTERNAL_RESULT_HASH_MISMATCH" in source
    assert "POST_EXTERNAL_METHOD_MUTATION" in source
    assert "INCART_PREDICTION_CLOSURE_FAILURE" in source
