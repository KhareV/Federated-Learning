# Change Control

Every change must be classified before artifacts dependent on it are regenerated. Reviewers must
escalate ambiguous changes to the higher-impact class. No Class C change may happen silently.

## Class A — implementation bug fix

A correction that does not alter scientific meaning, such as a parsing bug, test defect, incorrect
path, or serialization problem. It may retain the same scientific version, but requires a focused
regression test and a recorded rationale in normal version-control history.

## Class B — implementation/interface revision

A change to a software contract without changing the scientific target. It requires an interface
version bump where applicable, downstream impact analysis, and regression testing before dependent
artifacts are accepted.

## Class C — scientific/methodological revision

A change to the target, label mapping, lead, split policy, preprocessing, model-selection policy,
threshold policy, federated partition definition, or any decision with equivalent scientific
effect. It requires:

- an explicit new scientific or methodological version;
- the reason and approving authority;
- identification of impacted experiments and invalidated artifacts;
- a regeneration and re-verification plan.

Class C work must not reuse evidence generated under the superseded definition unless the evidence
is explicitly shown to be unaffected.

