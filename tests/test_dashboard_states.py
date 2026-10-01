"""T033 dashboard state-contract regression test (Section 53).

Static, source-level checks against the frontend TypeScript source -- this suite does not
require a Node/Svelte runtime. It exists alongside, not instead of, the frontend's own vitest
suite (frontend/src/lib/**/__tests__/*.test.ts), which exercises the same contract at the
TypeScript-type level.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"

EXPECTED_MONITORING_STATES = {
    "NORMAL_MONITORED_PATTERN",
    "POTENTIAL_ECTOPY_ASSOCIATED_PATTERN",
    "RECHECK_SENSOR",
    "CONTEXT_UNAVAILABLE",
    "SYSTEM_ERROR",
}

PROHIBITED_DIAGNOSIS_PHRASES = (
    "healthy",
    "normal heart",
    "no arrhythmia",
    "disease-free",
    "arrhythmia detected",
    "ectopy confirmed",
    "abnormal patient",
    "disease detected",
    "disease risk",
)


def _read(relative_path: str) -> str:
    return (FRONTEND / relative_path).read_text(encoding="utf-8")


def test_frontend_path_is_the_locked_repository_convention() -> None:
    """dashboard/ (solo-plan logical name) -> frontend/ (this repository's physical path)."""
    assert FRONTEND.is_dir()
    assert (FRONTEND / "package.json").exists()
    assert (FRONTEND / "src/routes").is_dir()


def test_no_root_dashboard_ui_web_or_client_app_exists() -> None:
    for forbidden in ("dashboard", "ui", "web", "client"):
        path = ROOT / forbidden
        assert not path.is_dir(), f"a root /{forbidden} directory must not exist (see frontend/)"


def test_frontend_is_sveltekit_not_a_second_parallel_framework() -> None:
    package_json = _read("package.json")
    assert '"@sveltejs/kit"' in package_json
    # No second frontend framework/toolchain introduced for T033.
    for forbidden_dependency in ('"next"', '"react-dom"', '"@angular/core"', '"vue"'):
        assert forbidden_dependency not in package_json


def test_api_client_binds_only_the_frozen_v1_infer_window_route() -> None:
    client = _read("src/lib/api/nhm-v1.ts")
    assert "/v1/infer-window" in client
    assert "API_SCHEMA_V1" in client
    # No client-side reimplementation of inference/calibration/threshold/episode logic.
    for forbidden in ("sigmoid", "torch", "temperature", "K2", "cooldown_us", "episode_manager"):
        assert forbidden not in client


def test_exactly_five_canonical_monitoring_states_are_declared() -> None:
    client = _read("src/lib/api/nhm-v1.ts")
    for state in EXPECTED_MONITORING_STATES:
        assert state in client
    assert "QUALITY_WARNING" not in client


def test_state_presentation_covers_exactly_five_states_no_sixth() -> None:
    presentation = _read("src/lib/dashboard/state-presentation.ts")
    for state in EXPECTED_MONITORING_STATES:
        assert f"{state}:" in presentation
    assert "QUALITY_WARNING:" not in presentation
    # 400 is explicitly a separate request/transport category, never a monitoring_state value.
    assert "displayState: null" in presentation


def test_state_wording_matches_v2_2_required_meanings() -> None:
    presentation = _read("src/lib/dashboard/state-presentation.ts")
    assert "Normal monitored pattern" in presentation
    assert "Potential SVF-associated ECG pattern" in presentation
    assert "Not a diagnosis" in presentation
    assert "Recheck sensor" in presentation or "signal quality" in presentation.lower()
    assert "Context unavailable" in presentation
    assert "Technical system error" in presentation


def test_no_diagnosis_wording_in_rendered_dashboard_route() -> None:
    """state-presentation.ts's own PROHIBITED_WORDING constant legitimately names these
    phrases as data (it is the banned-phrase registry, exercised by the frontend's own vitest
    suite with negation-aware matching) -- this check instead scans the rendered page, which
    must never contain them in any form."""
    lowered = _read("src/routes/monitoring/+page.svelte").lower()
    for phrase in PROHIBITED_DIAGNOSIS_PHRASES:
        assert phrase not in lowered, phrase


def test_research_only_probability_panel_is_present_and_labeled() -> None:
    page = _read("src/routes/monitoring/+page.svelte")
    assert "RESEARCH ONLY" in page
    assert "not a diagnosis" in page.lower() or "not a diagnosis, risk score" in page.lower()


def test_four_persistent_panels_plus_research_panel_are_present() -> None:
    page = _read("src/routes/monitoring/+page.svelte")
    assert "LIVE WAVEFORMS" in page
    assert "SIGNAL QUALITY" in page
    assert "CURRENT MONITORING STATE" in page
    assert "TECHNICAL METADATA" in page
    assert "RESEARCH ONLY" in page


def test_calibration_domain_and_alert_policy_id_are_displayed() -> None:
    page = _read("src/routes/monitoring/+page.svelte")
    assert "calibration_domain" in page
    assert "calibration_patient_count" in page
    assert "alert_policy_id" in page
    assert "SOURCE-DOMAIN CALIBRATION" in page
    assert "NOT WEARABLE-DOMAIN CLINICAL CALIBRATION" in page


def test_dashboard_route_never_computes_monitoring_state_from_probability_locally() -> None:
    page = _read("src/routes/monitoring/+page.svelte")
    # The only source of monitoring_state in the page must be the API response or the
    # httpErrorPresentation/STATE_PRESENTATION mapping -- never a local threshold comparison.
    assert "probability >" not in page
    assert "probability >=" not in page
    assert ">= threshold" not in page
    assert "> threshold" not in page


def test_error_mapping_matches_section_17() -> None:
    presentation = _read("src/lib/dashboard/state-presentation.ts")
    assert "appendProbabilityPoint: false" in presentation
    assert "'RECHECK_SENSOR'" in presentation  # 422 -> RECHECK_SENSOR
    assert "STATE_PRESENTATION.SYSTEM_ERROR.title" in presentation  # 500 -> SYSTEM_ERROR


def test_no_simulation_truth_imported_by_production_dashboard_route() -> None:
    page = _read("src/routes/monitoring/+page.svelte")
    assert "fixtures" not in page
    assert "SimulationTruth" not in page
    assert "UI_TEST_FIXTURE" not in page
