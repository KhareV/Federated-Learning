from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/t001.yml"


def _triggers() -> dict:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    # PyYAML parses the bare `on:` key as the boolean True under YAML 1.1.
    return workflow.get(True, workflow.get("on", {}))


def test_ci_is_manual_only_until_t033() -> None:
    """Regression guard: automatic push/pull_request CI must not be restored before T033.

    Automatic CI (push/pull_request triggers) is intentionally deferred from T004 through
    T032 per docs/HARDWARE_DEFERRED_EXECUTION_PLAN.md. This test must be updated, not deleted,
    when T033 restores automatic triggers.
    """
    triggers = _triggers()
    assert isinstance(triggers, dict)
    assert set(triggers) == {"workflow_dispatch"}
    assert "push" not in triggers
    assert "pull_request" not in triggers


def test_ci_deferral_is_documented_in_the_workflow() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "intentionally deferred" in text
    assert "T033" in text


def test_ci_deferral_is_documented_in_the_deferral_plan() -> None:
    plan = (ROOT / "docs/HARDWARE_DEFERRED_EXECUTION_PLAN.md").read_text(encoding="utf-8")
    normalized = " ".join(plan.split())
    assert "workflow_dispatch" in plan
    assert "T033" in plan
    assert "T004 through T032" in normalized
