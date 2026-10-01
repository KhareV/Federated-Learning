from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/t001.yml"


def _triggers() -> dict:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    # PyYAML parses the bare `on:` key as the boolean True under YAML 1.1.
    return workflow.get(True, workflow.get("on", {}))


def test_automatic_ci_is_restored_at_t033() -> None:
    """Regression guard: T033 is the first stage where automatic push/pull_request CI is
    restored, after being intentionally deferred from T004 through T032 (see
    docs/HARDWARE_DEFERRED_EXECUTION_PLAN.md). This test replaces the pre-T033
    manual-only-until-T033 guard; it must be updated, not deleted, if the CI policy changes
    again at T034/T035/T036.
    """
    triggers = _triggers()
    assert isinstance(triggers, dict)
    assert "push" in triggers
    assert "pull_request" in triggers
    assert "workflow_dispatch" in triggers


def test_ci_restoration_is_documented_in_the_workflow() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "T033" in text
    assert "restored" in text.lower()


def test_ci_deferral_history_remains_documented_in_the_deferral_plan() -> None:
    plan = (ROOT / "docs/HARDWARE_DEFERRED_EXECUTION_PLAN.md").read_text(encoding="utf-8")
    normalized = " ".join(plan.split())
    assert "workflow_dispatch" in plan
    assert "T033" in plan
    assert "T004 through T032" in normalized


def test_t033_jobs_never_acquire_raw_datasets_in_ci() -> None:
    """T033 CI is scoped to git-tracked checkpoints/artifacts/manifests only -- it must never
    invoke a multi-GB PhysioNet acquisition script (that remains a local, manual step)."""
    text = WORKFLOW.read_text(encoding="utf-8")
    for forbidden in ("acquire_mitdb", "acquire_incart", "acquire_nstdb", "acquire_bidmc"):
        assert forbidden not in text


def test_t033_backend_job_runs_lint_and_relevant_tests() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "t033-backend:" in text
    assert "make lint" in text
    assert "test_api_t032.py" in text
    assert "test_dashboard_states.py" in text
    assert "verify_api_runtime_t032.py" in text
    assert "verify_dashboard_ui_t033.py" in text
    assert "pip check" in text


def test_t033_frontend_job_runs_locked_install_check_test_build() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "t033-frontend:" in text
    assert "working-directory: frontend" in text
    assert "npm ci" in text
    assert "npm run check" in text
    assert "vitest run" in text
    assert "npm run build" in text
