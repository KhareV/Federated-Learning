# Source Authority

Primary technical/methodological authority:
`NHM_ML_Revised_Locked_Specification_v2.2.docx`

Implementation sequencing authority:
`NHM_Solo_Implementation_Execution_Plan_v1.0.docx`

Planning input and historical support only:
`NHM_Solo_Implementation_Master_Prompt_FINAL.docx`

The master planner prompt is not the implementation sequencing authority and cannot replace the
execution plan while the execution plan exists.

Supporting historical sources:

- Original NHM ML Development Plan — unavailable as a standalone local document at T001.
- Original NHM ML Work Division — unavailable as a standalone local document at T001.

The authority order is the locked specification v2.2, the solo implementation plan, the original
development plan, the original work-division plan, and then older specifications or notes.
**v2.2 overrides contradictory earlier methodology.** Historical documents cannot silently restore scope
that v2.2 removed. An implementation discovery may justify a versioned change under
`CHANGE_CONTROL.md`, but no scientific change may be made silently.

## Implementation sequence

The controlled sequence is:

`T001 → T002 → T003 → T004 → T005 → T006 → T007 → T008 → T009 → T010 → T011 → T012 → T013 → T014 → T015 → T016 → T017 → T018 → T019 → T020 → T021 → T022 → T023 → T024 → T025 → T026 → T027 → T028 → T029 → T030 → T031 → T032 → T033 → T034 → T035 → T036`

All T001-T036 task identities, names, phases, packet fields, and sequencing semantics come from
Section 22 and the dependency/critical-path sections of the execution plan. The checked-in
`manifests/task_packets_v1.json` snapshot is bound to the execution-plan SHA-256 and is the source
used by the task-registry generator and semantic tests.

`CURRENT_PHASE = T007`

The machine-checkable T002 planning baseline is `manifests/requirements_v22.csv`. Its decimal
sub-requirements preserve R01-R28, while CB01-CB06 identify cross-cutting claim boundaries. Any
scientific change requires the Class C process and a new source/registry version where applicable.
