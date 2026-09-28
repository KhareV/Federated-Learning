import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_source_authority_names_locked_spec_and_current_phase() -> None:
    authority = (ROOT / "docs/SOURCE_AUTHORITY.md").read_text(encoding="utf-8")
    assert "NHM_ML_Revised_Locked_Specification_v2.2.docx" in authority
    assert "NHM_Solo_Implementation_Execution_Plan_v1.0.docx" in authority
    assert "NHM_Solo_Implementation_Master_Prompt_FINAL.docx" in authority
    assert "master planner prompt is not the implementation sequencing authority" in authority
    assert "CURRENT_PHASE = T004" in authority
    assert "v2.2 overrides contradictory earlier methodology" in authority


def test_source_roles_cannot_promote_master_prompt() -> None:
    evidence = json.loads((ROOT / "reports/t002/source_hashes.json").read_text())
    roles = {source["filename"]: source["role"] for source in evidence["sources"]}
    assert roles == {
        "NHM_ML_Revised_Locked_Specification_v2.2.docx": "technical_authority",
        "NHM_Solo_Implementation_Execution_Plan_v1.0.docx": (
            "implementation_sequencing_authority"
        ),
        "NHM_Solo_Implementation_Master_Prompt_FINAL.docx": "planning_input_only",
    }
