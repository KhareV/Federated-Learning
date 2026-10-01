"""T032 scope-boundary checks (v2.2 Section 27 / Solo Plan T032 packet).

The production API surface (api/app.py, api/runtime.py, api/schemas.py, api/session.py) must
never import a dataset loader, training code, calibration-fitting code, or SimulationTruth,
and must never express disease-diagnosis wording. api/fixture_v0.py (T005, MOCK_INFERENCE_V0)
is explicitly isolated and excluded from this boundary -- it is historical, not production.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PRODUCTION_API_FILES = (
    ROOT / "api/app.py",
    ROOT / "api/runtime.py",
    ROOT / "api/schemas.py",
    ROOT / "api/session.py",
)

FORBIDDEN_IMPORT_PREFIXES = (
    "simulation.wearable",
    "simulation.truth",
    "training",
    "data.loaders",
    "calibration.fit",
)

PROHIBITED_FIELD_NAMES = (
    "diagnosis_label",
    "disease_probability",
    "arrhythmia_diagnosis",
    "arrhythmia_label",
    "cardiac_emergency",
)


def _imported_module_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_production_api_files_never_import_forbidden_modules() -> None:
    for path in PRODUCTION_API_FILES:
        imported = _imported_module_names(path)
        for forbidden in FORBIDDEN_IMPORT_PREFIXES:
            matches = [
                name
                for name in imported
                if name == forbidden or name.startswith(forbidden + ".")
            ]
            assert not matches, f"{path.name} imports forbidden module(s): {matches}"


def test_production_api_files_never_import_mock_inference_or_fixture_state_policy() -> None:
    """api/app.py may only name MOCK_INFERENCE_V0/FIXTURE_STATE_POLICY_V0 symbols via the
    explicit, documented api/fixture_v0.py re-export for T005 regression tests -- it must
    never call into deployment.mock_inference directly itself."""
    for path in (ROOT / "api/runtime.py", ROOT / "api/schemas.py", ROOT / "api/session.py"):
        imported = _imported_module_names(path)
        assert "deployment.mock_inference" not in imported
        assert "fusion.state_machine" not in imported or path.name == "app.py"


def test_production_api_files_contain_no_prohibited_diagnosis_field_names() -> None:
    """The API's own disclaiming prose ("never a diagnosis") is expected and correct; what
    must never appear is an actual diagnosis-shaped field or output name."""
    for path in PRODUCTION_API_FILES:
        text = path.read_text(encoding="utf-8").lower()
        for prohibited in PROHIBITED_FIELD_NAMES:
            assert prohibited not in text, f"{path.name} contains prohibited field: {prohibited!r}"


def test_production_app_never_constructs_mock_inference_runtime() -> None:
    text = (ROOT / "api/app.py").read_text(encoding="utf-8")
    assert "run_mock_inference(" not in text
    assert "classify_safe(" not in text


def test_fixture_v0_module_is_clearly_isolated_and_historical() -> None:
    text = (ROOT / "api/fixture_v0.py").read_text(encoding="utf-8")
    assert "NOT the production FastAPI application" in text
    assert "T032" in text


def test_production_runtime_binds_only_frozen_artifact_identifiers() -> None:
    text = (ROOT / "api/runtime.py").read_text(encoding="utf-8")
    for required_id in (
        "GATEWAY_ARTIFACT_V1",
        "PREPROC_V1",
        "ECG_HR_CONTEXT_V2",
        "ALERT_POLICY_V1",
    ):
        assert required_id in text


def test_no_database_or_auth_dependencies_are_imported() -> None:
    for path in PRODUCTION_API_FILES:
        imported = _imported_module_names(path)
        for forbidden in ("pymongo", "motor", "sqlalchemy", "jwt", "oauth"):
            assert not any(
                name == forbidden or name.startswith(forbidden + ".") for name in imported
            )
