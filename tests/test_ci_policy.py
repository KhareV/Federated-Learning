from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/t001.yml"


def _triggers() -> dict:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    # PyYAML parses the bare `on:` key as the boolean True under YAML 1.1.
    return workflow.get(True, workflow.get("on", {}))


def test_ci_is_manual_only_as_of_t034() -> None:
    """Regression guard: automatic CI (push/pull_request) was briefly restored at T033, then
    deferred again at T034 by explicit in-chat user instruction -- see
    reports/t034/ci_deferral.json. This workflow must stay manual-only (workflow_dispatch)
    until the user explicitly asks for CI to be re-enabled in a future conversation. This test
    must be updated, not deleted, when that happens.
    """
    triggers = _triggers()
    assert isinstance(triggers, dict)
    assert set(triggers) == {"workflow_dispatch"}
    assert "push" not in triggers
    assert "pull_request" not in triggers


def test_ci_deferral_is_documented_in_the_workflow() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "T034" in text
    assert "manual-only" in text.lower()


def test_ci_deferral_history_remains_documented_in_the_deferral_plan() -> None:
    plan = (ROOT / "docs/HARDWARE_DEFERRED_EXECUTION_PLAN.md").read_text(encoding="utf-8")
    normalized = " ".join(plan.split())
    assert "workflow_dispatch" in plan
    assert "T033" in plan
    assert "T004 through T032" in normalized


def test_t033_jobs_are_preserved_not_deleted() -> None:
    """The CI deferral at T034 is a scheduling/control-plane change only -- the T033 jobs
    remain available on demand (workflow_dispatch), never deleted."""
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "t033-backend:" in text
    assert "t033-frontend:" in text
    assert "phase-01:" in text


def test_t033_jobs_never_acquire_raw_datasets_in_ci() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    for forbidden in ("acquire_mitdb", "acquire_incart", "acquire_nstdb", "acquire_bidmc"):
        assert forbidden not in text


def test_historical_t033_ci_evidence_is_preserved() -> None:
    """T034's CI-deferral correction must not rewrite the T033 CI run record."""
    assert (ROOT / "reports/t033/ci_run.json").exists()
    assert (ROOT / "reports/t033/ci_report.json").exists()
    run = (ROOT / "reports/t033/ci_run.json").read_text(encoding="utf-8")
    assert "36910820027" in run
