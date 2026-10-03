"""Tests the narrow resolves_conditional_skip predicate (Section 15/16 of the V2-005
corrective/disposition spec): SKIPPED_BY_PROTOCOL only resolves a downstream prerequisite
when the task predeclared a conditional branch AND frozen disposition evidence exists. A
task marked SKIPPED_BY_PROTOCOL without either is NOT automatically accepted, and this must
not generalize into "SKIPPED == PASS" for arbitrary future tasks.
"""

from __future__ import annotations

from nhm.model_v2_conditional_prerequisite import resolves_conditional_skip


def test_v2_005_shaped_case_resolves() -> None:
    # V2-005: status SKIPPED_BY_PROTOCOL, predeclared in its own registry notes ("otherwise
    # SKIPPED_BY_PROTOCOL"), and backed by reports/model_v2/v2_005/hybrid_disposition.json.
    assert resolves_conditional_skip("SKIPPED_BY_PROTOCOL", True, True) is True


def test_random_future_task_without_predeclared_branch_not_accepted() -> None:
    # A hypothetical future task marked SKIPPED_BY_PROTOCOL with no predeclared conditional
    # branch in its own frozen registry notes must not be silently treated as resolved.
    assert resolves_conditional_skip("SKIPPED_BY_PROTOCOL", False, True) is False


def test_predeclared_branch_without_frozen_evidence_not_accepted() -> None:
    # Predeclaring a conditional branch is not enough on its own; the disposition must
    # actually have been evaluated and frozen as evidence.
    assert resolves_conditional_skip("SKIPPED_BY_PROTOCOL", True, False) is False


def test_neither_condition_not_accepted() -> None:
    assert resolves_conditional_skip("SKIPPED_BY_PROTOCOL", False, False) is False


def test_non_skip_statuses_never_resolve_through_this_predicate() -> None:
    # PASS/NOT_STARTED/FAIL resolve (or don't) through their own ordinary status rules, not
    # through this conditional-skip predicate -- it only ever returns True for the literal
    # SKIPPED_BY_PROTOCOL string.
    for status in ["PASS", "NOT_STARTED", "FAIL", "BLOCKED", ""]:
        assert resolves_conditional_skip(status, True, True) is False


def test_does_not_generalize_skipped_equals_pass() -> None:
    # Guards against a future regression that collapses this predicate into treating every
    # SKIPPED_BY_PROTOCOL task as equivalent to PASS regardless of evidence.
    always_true_if_skipped_equals_pass = all(
        resolves_conditional_skip("SKIPPED_BY_PROTOCOL", predeclared, has_evidence)
        for predeclared in (True, False)
        for has_evidence in (True, False)
    )
    assert always_true_if_skipped_equals_pass is False
