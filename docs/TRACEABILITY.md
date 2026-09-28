# T002 Traceability Policy

`manifests/requirements_v22.csv` is the canonical v2.2 implementation traceability registry. The
established R01-R28 IDs are preserved. Decimal children such as R10.2 cover mandatory detail that
would otherwise remain implicit. CB01-CB06 are explicit cross-cutting claim boundaries. OOS IDs
record scope that v2.2 expressly excludes; they are not implementation commitments.

The local sequencing authority file is `NHM_Solo_Implementation_Master_Prompt_FINAL.docx`. The
requested name `NHM_Solo_Implementation_Execution_Plan_v1.0.docx` is not present. The available
document defines decomposition rules and a critical path, but it does not enumerate named
T004-T036 packets. T001-T003 retain their externally supplied names; T004-T036 in the task registry
are the T002 operational decomposition of v2.2 Sections 3, 36, 37, Appendix A, and the solo-plan
critical path. This provenance is explicit in every derived task row.

Run `make coverage` after any registry edit. A mandatory row without task, validation, acceptance,
gate, evidence, change class, or precise source fails. Unknown T/G/R references, missing canonical
IDs, future PASS states, source-version drift, missing claim boundaries, and orphan tasks are also
reported. Scientific edits require Class C change control; changing the source version without a
registry version/impact analysis is prohibited.

