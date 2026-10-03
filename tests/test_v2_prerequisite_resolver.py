"""Tests the generic MODEL_V2 prerequisite resolver (src/nhm/model_v2_prerequisite_resolver.py).
Proves V2-005's real registry row + hybrid_disposition.json evidence correctly resolves as a
V2-007 prerequisite, while an arbitrary fake skipped future task (no predeclared conditional
branch, no evidence) does not resolve. Canonical T001-T036 prerequisite semantics are
untouched by this module.
"""

from __future__ import annotations

from nhm.model_v2_prerequisite_resolver import (
    is_v2_prerequisite_resolved,
    v2_005_prerequisite_resolved_for_v2_007,
)


def test_pass_status_always_resolved() -> None:
    assert is_v2_prerequisite_resolved("PASS") is True
    assert is_v2_prerequisite_resolved("PASS", task_predeclares_conditional_skip=False) is True


def test_not_started_never_resolved() -> None:
    assert is_v2_prerequisite_resolved("NOT_STARTED") is False


def test_v2_005_shaped_skip_resolves() -> None:
    assert (
        is_v2_prerequisite_resolved(
            "SKIPPED_BY_PROTOCOL",
            task_predeclares_conditional_skip=True,
            has_frozen_disposition_evidence=True,
        )
        is True
    )


def test_arbitrary_fake_skipped_task_without_predeclared_branch_rejected() -> None:
    assert (
        is_v2_prerequisite_resolved(
            "SKIPPED_BY_PROTOCOL",
            task_predeclares_conditional_skip=False,
            has_frozen_disposition_evidence=True,
        )
        is False
    )


def test_arbitrary_fake_skipped_task_without_evidence_rejected() -> None:
    assert (
        is_v2_prerequisite_resolved(
            "SKIPPED_BY_PROTOCOL",
            task_predeclares_conditional_skip=True,
            has_frozen_disposition_evidence=False,
        )
        is False
    )


def test_real_v2_005_resolves_v2_007_prerequisite_from_committed_evidence() -> None:
    # Integration check against the actual committed registry row and
    # reports/model_v2/v2_005/hybrid_disposition.json -- not synthetic data.
    assert v2_005_prerequisite_resolved_for_v2_007() is True


def test_real_v2_005_resolution_breaks_if_v2g4_not_pass(tmp_path, monkeypatch) -> None:
    import csv
    import shutil

    from nhm import model_v2_prerequisite_resolver as resolver_module

    fake_root = tmp_path / "repo"
    (fake_root / "manifests/model_v2").mkdir(parents=True)
    (fake_root / "reports/model_v2/v2_005").mkdir(parents=True)
    (fake_root / "configs/model_v2").mkdir(parents=True)

    real_root = resolver_module.ROOT
    shutil.copy(
        real_root / "manifests/model_v2/task_registry_v1.csv",
        fake_root / "manifests/model_v2/task_registry_v1.csv",
    )
    shutil.copy(
        real_root / "reports/model_v2/v2_005/hybrid_disposition.json",
        fake_root / "reports/model_v2/v2_005/hybrid_disposition.json",
    )
    shutil.copy(
        real_root / "configs/model_v2/research_protocol_v2.yaml",
        fake_root / "configs/model_v2/research_protocol_v2.yaml",
    )

    gate_path = real_root / "manifests/model_v2/gate_registry_v1.csv"
    with gate_path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
        fieldnames = rows[0].keys()
    for row in rows:
        if row["gate_id"] == "V2G4":
            row["status"] = "NOT_STARTED"
    fake_gate_path = fake_root / "manifests/model_v2/gate_registry_v1.csv"
    with fake_gate_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    assert resolver_module.v2_005_prerequisite_resolved_for_v2_007(root=fake_root) is False
