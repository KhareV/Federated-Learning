# MODEL_V2_LIFECYCLE_TEST_POLICY_V1

Control-plane governance introduced in V2-FL-004 (before the SecAgg+ method freeze).

**Problem.** Each MODEL_V2 phase changed the registry; older phase-specific tests that hard-coded
"later tasks are NOT_STARTED" (or exact passed-sets) then had to be edited to admit the next phase.
That repeated, ad-hoc relaxation is itself a risk (it touched hash-pinned method tests and once
produced a self-exempting finalizer).

**Rules (see `configs/model_v2/lifecycle_test_policy_v1.yaml`).**
A. `tests/test_model_v2_current_lifecycle.py` is the only test asserting the exact current
   task/gate/component state; it is updated at each phase transition and is never part of a
   scientific method freeze.
B. Historical phase tests assert immutable facts (hashes, scientific configuration, historical
   prerequisites, method semantics, results, irreversible completed states) and never require a
   later task to stay NOT_STARTED.
C. Hash-pinned historical freezes are not rewritten.
D. Lifecycle-only test drift stays visible: recorded in each phase's lifecycle-drift audit.
E. No scientific method freeze includes the mutable current-lifecycle test.
F. Only files explicitly classified in the policy may carry lifecycle/control-plane drift; no other
   test or scientific-method file is exempt.

Enforced by `tests/test_model_v2_lifecycle_policy.py`.
