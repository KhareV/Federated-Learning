from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_source_authority_names_locked_spec_and_current_phase() -> None:
    authority = (ROOT / "docs/SOURCE_AUTHORITY.md").read_text(encoding="utf-8")
    assert "NHM_ML_Revised_Locked_Specification_v2.2.docx" in authority
    assert "CURRENT_PHASE = T002" in authority
    assert "v2.2 overrides contradictory earlier methodology" in authority
