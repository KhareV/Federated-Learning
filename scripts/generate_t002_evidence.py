#!/usr/bin/env python3
"""Generate T002 traceability evidence with the canonical SHA-256 convention."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from nhm.hashing import hash_file
from nhm.run_manifest import artifact_record, create_run_manifest, write_run_manifest

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports/t002"
SPEC = ROOT / "NHM_ML_Revised_Locked_Specification_v2.2.docx"
LOCAL_PLAN = ROOT / "NHM_Solo_Implementation_Master_Prompt_FINAL.docx"
EXPECTED_PLAN_NAME = "NHM_Solo_Implementation_Execution_Plan_v1.0.docx"
EXPECTED_SOURCE_HASHES = {
    SPEC.name: "1c72bbbf45c7d9eb23b7fa1a00e249538153f06e337d194ce93108029cb16e0c",
    LOCAL_PLAN.name: "e65663dc8c53a4843f10b36ada6fcde07cf08122c961c36163cfdd0c03dfdd01",
}

REGISTRIES = [
    "task_registry_v1.csv",
    "requirements_v22.csv",
    "gate_registry_v1.csv",
    "freeze_registry_v1.csv",
    "do_not_start_v1.csv",
    "experiment_registry_v1.csv",
    "evidence_registry_v1.csv",
]


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def verify_and_write_sources() -> Path:
    sources = []
    for path, role in (
        (SPEC, "primary technical/methodological authority"),
        (LOCAL_PLAN, "local implementation sequencing source available to T001/T002"),
    ):
        if not path.exists():
            raise FileNotFoundError(f"SOURCE_VERSION_CONFLICT: missing {path.name}")
        actual = hash_file(path)
        if actual != EXPECTED_SOURCE_HASHES[path.name]:
            raise RuntimeError(
                f"SOURCE_VERSION_CONFLICT: {path.name} expected "
                f"{EXPECTED_SOURCE_HASHES[path.name]} but found {actual}"
            )
        sources.append({"filename": path.name, "role": role, "sha256": actual})

    output = REPORT_DIR / "source_hashes.json"
    write_json(
        output,
        {
            "algorithm": "sha256",
            "rule": "SHA-256 of exact source-document bytes using nhm.hashing.hash_file",
            "sources": sources,
            "source_name_discrepancy": {
                "expected_by_phase_prompt": EXPECTED_PLAN_NAME,
                "expected_file_present": (ROOT / EXPECTED_PLAN_NAME).exists(),
                "local_file_used": LOCAL_PLAN.name,
                "resolution": (
                    "The only local sequencing source established during T001 was audited; "
                    "no missing document content or hash was invented."
                ),
            },
        },
    )
    return output


def write_summary(audit: dict[str, object]) -> Path:
    output = REPORT_DIR / "coverage_summary.md"
    content = f"""# T002 Coverage Summary

## Outcome

The second machine audit passed with {audit['mandatory_requirement_count']} mandatory
requirements mapped, zero invalid task references, zero invalid gate references, and
zero orphan tasks.

## Two-pass review

- First automated draft: {audit['first_pass_unmapped_count']} structurally unmapped mandatory
  requirements.
- Manual review: completed section-by-section against v2.2, including gates, Definition of Done,
  Appendix A experiments, and Appendix B evidence.
- Manual additions: `R10.2` locked metrics, `R23.2` error slices, `R26.3` clean/private-data
  reproducibility, plus explicit out-of-scope rows `OOS01`-`OOS04`.
- Second automated audit: {audit['second_pass_unmapped_count']} unmapped mandatory requirements.

## Reverse coverage

All 36 tasks have a requirement, gate, or evidence consumer. No task is classified as
`POSSIBLE_ORPHAN`, `COVERAGE_GAP`, `VALID_INFRASTRUCTURE_TASK`, or `VALID_RELEASE_TASK`
because the final orphan count is zero.

## Source and task-name provenance

The phase prompt names `NHM_Solo_Implementation_Execution_Plan_v1.0.docx`, but that file is
not present. The local sequencing source is `NHM_Solo_Implementation_Master_Prompt_FINAL.docx`.
It does not enumerate named work packets T004-T036. Those operational task names are therefore
documented derivations from v2.2 Sections 3, 36, 37, Appendix A, and the local plan's critical
path. The registries do not claim those derived names are verbatim source text.

## Boundary

T002 adds traceability and enforcement metadata only. No dataset ingestion, preprocessing,
training, evaluation, federated execution, API, dashboard, or wearable functionality was
implemented.
"""
    output.write_text(content, encoding="utf-8")
    return output


def record_generated_evidence_hashes(paths: dict[str, Path]) -> None:
    registry = ROOT / "manifests/evidence_registry_v1.csv"
    with registry.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames
        rows = list(reader)
    if fieldnames is None:
        raise RuntimeError("Evidence registry has no header")
    for row in rows:
        if row["evidence_id"] in paths:
            row["sha256"] = hash_file(paths[row["evidence_id"]])
        elif row["status"] == "PLANNED":
            row["sha256"] = ""
    temporary = registry.with_suffix(f"{registry.suffix}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(registry)


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    audit_path = REPORT_DIR / "coverage_audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if audit.get("status") != "PASS" or not audit.get("manual_review_completed"):
        raise RuntimeError("T002 evidence requires a passing second coverage audit")

    source_hashes = verify_and_write_sources()
    summary = write_summary(audit)
    record_generated_evidence_hashes(
        {
            "EV001": ROOT / "reports/t001/closure_verification.json",
            "EV002": audit_path,
            "EV003": source_hashes,
            "EV004": summary,
        }
    )
    registry_paths = [ROOT / "manifests" / name for name in REGISTRIES]
    input_paths = [SPEC, LOCAL_PLAN, *registry_paths]
    output_paths = [audit_path, source_hashes, summary]

    manifest_path = REPORT_DIR / "run_manifest.json"
    manifest = create_run_manifest(
        ROOT,
        run_id="T002-COVERAGE-AUDIT-V1",
        phase_id="T002",
        task_id="T002",
        config_path=ROOT / "configs/base.yaml",
        dependency_snapshot_path=ROOT / "reports/t001/dependencies.txt",
        input_artifacts=[artifact_record(path, ROOT) for path in input_paths],
        output_artifacts=[artifact_record(path, ROOT) for path in output_paths],
        notes=(
            "Second coverage audit after a manual v2.2 section review; source-name "
            "discrepancy is recorded in source_hashes.json."
        ),
    )
    write_run_manifest(manifest, manifest_path, ROOT / "contracts/run_manifest_v1.schema.json")

    hash_paths = [
        ROOT / "configs/base.yaml",
        ROOT / "docs/DO_NOT_START_YET.md",
        ROOT / "docs/TRACEABILITY.md",
        *registry_paths,
        REPORT_DIR / "coverage_audit_first_pass.json",
        audit_path,
        summary,
        source_hashes,
        manifest_path,
    ]
    missing = [str(path) for path in hash_paths if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Cannot hash missing T002 evidence: {missing}")
    write_json(
        REPORT_DIR / "artifact_hashes.json",
        {
            "manifest_version": "1.0",
            "algorithm": "sha256",
            "rule": "exact file bytes; this manifest excludes itself to avoid a circular digest",
            "artifacts": {
                str(path.relative_to(ROOT)): hash_file(path) for path in sorted(hash_paths)
            },
        },
    )
    print("T002 evidence: generated")


if __name__ == "__main__":
    main()
