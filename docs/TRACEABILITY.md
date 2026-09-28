# T002 Traceability Policy

`manifests/requirements_v22.csv` is the canonical v2.2 implementation traceability registry. The
established R01-R28 IDs are preserved. Decimal children such as R10.2 cover mandatory detail that
would otherwise remain implicit. CB01-CB06 are explicit cross-cutting claim boundaries. OOS IDs
record scope that v2.2 expressly excludes; they are not implementation commitments.

The sequencing authority is `NHM_Solo_Implementation_Execution_Plan_v1.0.docx`. Its complete
T001-T036 packet table was extracted into `manifests/task_packets_v1.json`, which records the exact
source hash and all packet fields. `scripts/build_t002_registries.py` consumes that checked-in
snapshot; it contains no replacement operational task definitions. Normalized prerequisite IDs
are traceable to the execution plan's dependency graph and critical path.

`NHM_Solo_Implementation_Master_Prompt_FINAL.docx` is retained and hashed as planning input only.
Git history preserves the provisional T002 attempt that used it while the execution plan was
absent. `reports/t002/task_registry_reconciliation.csv` records every changed task field.

Run `make coverage` after any registry edit. A mandatory row without task, validation, acceptance,
gate, evidence, change class, or precise source fails. Unknown T/G/R references, missing canonical
IDs, future PASS states, source-version drift, missing claim boundaries, and orphan tasks are also
reported. Scientific edits require Class C change control; changing the source version without a
registry version/impact analysis is prohibited.
