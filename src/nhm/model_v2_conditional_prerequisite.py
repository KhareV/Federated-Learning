"""Narrow predicate for when a MODEL_V2 task's SKIPPED_BY_PROTOCOL status counts as a
resolved prerequisite for downstream tasks.

This is intentionally NOT a general "SKIPPED == PASS" rule. A task's SKIPPED_BY_PROTOCOL
status only resolves a downstream prerequisite when all three conditions hold:
  1. the task's own frozen registry notes predeclare a conditional branch that can resolve
     to a skip (the condition was known and pre-registered before any result existed);
  2. a frozen disposition-evidence artifact exists proving the branch condition was actually
     evaluated from frozen inputs and resolved false; and
  3. the task's status is literally SKIPPED_BY_PROTOCOL.

A task marked SKIPPED_BY_PROTOCOL without a predeclared conditional branch, or without
disposition evidence, is NOT automatically treated as resolved by this predicate -- the
canonical T001-T036 status vocabulary and semantics are untouched by this module.
"""

from __future__ import annotations


def resolves_conditional_skip(
    status: str,
    task_predeclares_conditional_skip: bool,
    has_frozen_disposition_evidence: bool,
) -> bool:
    """Return True only if a SKIPPED_BY_PROTOCOL status is backed by a predeclared
    conditional branch and frozen disposition evidence; False in every other case,
    including for ordinary PASS/NOT_STARTED/FAIL statuses (those resolve by their own
    plain-status rules, not through this predicate)."""
    return (
        status == "SKIPPED_BY_PROTOCOL"
        and task_predeclares_conditional_skip
        and has_frozen_disposition_evidence
    )
