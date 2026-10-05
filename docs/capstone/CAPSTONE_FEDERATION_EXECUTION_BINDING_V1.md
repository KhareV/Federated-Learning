# CAPSTONE_FEDERATION_EXECUTION_BINDING_V1 (CAP-007)

How the live federation orchestrator is bound to the existing V2 FL stack, **without changing any frozen contract or code**. The machine-readable form is `contracts/capstone/federation_execution_binding_v1.json`; the reconciliation that required it is `reports/capstone/cap_007/federation_contract_reconciliation.json`.

* **One candidate per FL_SINGLE_RUN.** The aggregate of rounds 1 and 2 is the next round's base *state*, not a registry candidate; only the round-3 state becomes `CAPSTONE_FL_CANDIDATE_0001` (parent `FL_INIT_V2`). The V1 round-transition table cannot express this, so the additive `CAPSTONE_FEDERATION_CONTRACT_V2` adds exactly one transition (`AGGREGATING -> COMPLETED`, non-final rounds). `federation_v1.json` is not edited.
* **Client successor.** `CAPSTONE_FL_CLIENT_ADAPTER_V2` subclasses the CAP-006 V1 adapter (unchanged) and accepts a round base only after lineage verification: round 1 = the frozen FL_INIT_V2 digest, round N>1 = the digest of the immediately preceding committed round state. `MODEL_V2_FINAL` and candidates are refused as a base.
* **Server side.** The unchanged `federated.wearable_fl_system_v1.Coordinator` receives the genuine V2 envelopes (open/submit/ready/aggregate/commit) and the unchanged `aggregate_weighted_deltas` aggregates. The normal run injects no bad updates; invalid-update behaviour is a separate harness scenario.
* **Public request.** Only `run_type, algorithm, secagg_mode, planned_rounds, scenario_id`; only `FL_SINGLE_RUN` with exactly 3 rounds; the server derives the base. FedProx uses the frozen `mu` 0.1 only.
* **SecAgg.** `SECAGG_SHADOW` verifies round 1 only, beside the authoritative PLAIN aggregation (`PROTECTED_AGGREGATION_INTERFACE_ONLY`; frozen tolerances; no DP/anonymity claim).
* **Training progress.** Only the start (0.0) and completion (1.0) milestones are emitted; intermediate progress is never invented.
* **Replay / resume.** REPLAY re-emits a prior completed run's events with zero training; a killed server resumes from the last round-boundary checkpoint, otherwise the run is FAILED (nothing is fabricated).
* **Concurrency.** At most one active LIVE run globally; start returns promptly and the run executes in a background task (blocking work in worker threads).
* **Locality.** Eight logically isolated local client datasets on one laptop; no hospital, hardware, VM, enclave or privacy claim. No candidate is served, deployed or promoted.
