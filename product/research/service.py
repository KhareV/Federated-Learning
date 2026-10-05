"""CAPSTONE_RESEARCH_EVIDENCE_SERVICE_V1: verified frozen catalog, no science execution."""

from __future__ import annotations

import json

from product.research.models import FlResearchEvidence, MlResearchEvidence, SourceProvenance
from scripts.build_capstone_research_evidence_catalog import CATALOG
from scripts.verify_capstone_research_evidence_catalog import verify


class ResearchEvidenceService:
    def __init__(self) -> None:
        self._catalog: dict[str, object] | None = None

    def _load(self) -> dict[str, object]:
        # Verify on every read: fail closed if either a source or derived artifact drifts.
        verify()
        self._catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
        return self._catalog

    @staticmethod
    def _provenance(facts: list[dict[str, object]]) -> list[SourceProvenance]:
        unique = {(str(f["phase"]), str(f["source_relative_path"]), str(f["source_sha256"]))
                  for f in facts}
        return [SourceProvenance(phase=phase, source_relative_path=path, source_sha256=digest)
                for phase, path, digest in sorted(unique)]

    def ml(self) -> MlResearchEvidence:
        catalog = self._load()
        facts = catalog["ml_facts"]
        return MlResearchEvidence(
            catalog_id=catalog["catalog_id"], evidence_version=catalog["evidence_version"],
            generated_from_frozen_sources=catalog["generated_from_frozen_sources"],
            facts=facts, source_provenance=self._provenance(facts),
            claim_boundary=catalog["claim_boundary"])

    def fl(self) -> FlResearchEvidence:
        catalog = self._load()
        facts = catalog["fl_facts"]
        return FlResearchEvidence(
            catalog_id=catalog["catalog_id"], evidence_version=catalog["evidence_version"],
            generated_from_frozen_sources=catalog["generated_from_frozen_sources"],
            facts=facts, source_provenance=self._provenance(facts),
            claim_boundary=catalog["claim_boundary"],
            scientific_fl_phases=catalog["scientific_fl_phases"],
            v2_fl_005_role=catalog["v2_fl_005_role"])
