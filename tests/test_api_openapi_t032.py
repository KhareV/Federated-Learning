"""T032 OpenAPI contract: generated from the real app (never hand-authored), documenting the
correct 400/422/500 ErrorResponse semantics instead of FastAPI's default
HTTPValidationError/422 behavior, and byte-identical on regeneration.
"""

from __future__ import annotations

import json
from pathlib import Path

from api.app import app
from scripts.generate_openapi_v1_t032 import generate

ROOT = Path(__file__).resolve().parents[1]
OPENAPI_PATH = ROOT / "contracts/openapi_v1.json"
ROUTE = "/v1/infer-window"


def test_openapi_file_exists_and_is_canonical_json() -> None:
    assert OPENAPI_PATH.exists(), "run scripts/generate_openapi_v1_t032.py"
    text = OPENAPI_PATH.read_text(encoding="utf-8")
    assert text == json.dumps(json.loads(text), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def test_openapi_file_is_byte_identical_to_fresh_regeneration() -> None:
    on_disk = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
    regenerated = json.loads(json.dumps(generate()))
    assert on_disk == regenerated


def test_openapi_route_documents_infer_window() -> None:
    schema = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
    assert ROUTE in schema["paths"]
    assert "post" in schema["paths"][ROUTE]


def test_openapi_documents_400_422_500_with_correct_meanings_not_fastapi_defaults() -> None:
    schema = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
    responses = schema["paths"][ROUTE]["post"]["responses"]
    assert set(responses) >= {"200", "400", "422", "500"}

    for code in ("400", "422", "500"):
        ref = responses[code]["content"]["application/json"]["schema"]["$ref"]
        assert ref == "#/components/schemas/ErrorResponse"

    assert "unusable" in responses["422"]["description"].lower()
    description_400 = responses["400"]["description"].lower()
    assert "schema" in description_400 or "contract" in description_400

    schemas = schema.get("components", {}).get("schemas", {})
    assert "HTTPValidationError" not in schemas
    assert "ValidationError" not in schemas


def test_openapi_does_not_document_a_disease_diagnosis_field() -> None:
    text = OPENAPI_PATH.read_text(encoding="utf-8").lower()
    for prohibited in ("diagnosis_label", "disease_probability", "arrhythmia_diagnosis"):
        assert prohibited not in text


def test_app_title_and_version_are_api_schema_v1() -> None:
    schema = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
    assert schema["info"]["version"] == "API_SCHEMA_V1"


def test_live_app_openapi_matches_on_disk_contract() -> None:
    """Guards against the common real-world drift: someone edits api/app.py and forgets to
    rerun the generator. Fails loudly instead of silently serving stale documentation."""
    live = json.loads(json.dumps(app.openapi()))
    on_disk = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
    assert live == on_disk
