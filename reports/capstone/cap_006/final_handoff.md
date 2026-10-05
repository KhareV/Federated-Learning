# CAP-006 FINAL HANDOFF - Local training buffer + federated client product adapter (gate CAPG5)

----------------------------------------------------------------------
PHASE RESULT
----------------------------------------------------------------------
CAP-006: **PASS**   CAPG5: **PASS** (94/94 criteria: the 89 prompt-mandated + 5 implementation-specific, frozen before evaluation). Evidence: `reports/capstone/cap_006/capg5_criteria.json`.

----------------------------------------------------------------------
ENTRY
----------------------------------------------------------------------
Entry SHA `b8a6c70ed6b77a38273cb8bdb6659452dfe26f83`; origin/main identical; tree clean. Prior phases CAP-001..005 PASS / CAPG0..4 PASS; CAP-006..011 NOT_STARTED.
All prior locks/amendment chains verified link by link (CAP-001 +1, CAP-002 +4, CAP-003 +1, CAP-004 +6, CAP-005 +5, CAPSTONE_UI_V1), at entry and again at final.

----------------------------------------------------------------------
UPSTREAM PROTECTION
----------------------------------------------------------------------
Scientific/runtime drift: NO. V2-FL drift: NO (`federated/`, `privacy/`, `reports/model_v2/` untouched). Backend drift: NO. CAPSTONE_UI_V1 drift: NO (203 frontend files byte-identical; `frontend_drift = []`).
FL_INIT_V2 unchanged: YES (`6a2923ca...` equal in V2-FL-005 evidence, FEDPROX_MU_V2 lock, repro lock and regenerated state). V2-FL-005 unchanged: YES (its lock verifies).

----------------------------------------------------------------------
PROTOCOL
----------------------------------------------------------------------
`CAPSTONE_LOCAL_TRAINING_PROTOCOL_V1`; freeze commit `a1582da` (before any canonical run); lock `artifacts/capstone/CAPSTONE_LOCAL_TRAINING_PROTOCOL_V1.lock.json` (sha256 in `capg5_criteria.json`/lock file); 94 criteria.

----------------------------------------------------------------------
COHORT
----------------------------------------------------------------------
WEARABLE_SIM_FL_COHORT_V1; clients SIM_FL_SITE_00..07; participants SIM_P000101..SIM_P000108. Existing cohort reused: YES (`simulation.fl_cohort_v1.cohort_profiles()` + `build_local_dataset`). Second client universe: NO.
Dataset parity: all eight clients equal V2-FL-005 on source records, windows, VALID/DEGRADED/UNUSABLE, trainable, synthetic positive/negative **and dataset SHA256** (read from frozen evidence, not copied).

----------------------------------------------------------------------
LABELS
----------------------------------------------------------------------
Label contract `WEARABLE_SIM_EVENT_WINDOW_V1` (source `SIMULATION_TRUTH_ENGINEERING`): positive = a scheduled SYNTHETIC / ENGINEERING EVENT inside the window. SimulationTruth consumer: only the existing `federated/wearable_sim_local_labels.py`.
Direct truth import under `product/`: NO (static AST scan of all of `product/`, `api/`, `capstone_persistence/`, `privacy/` + frozen CAP-001 importer tests). Prediction-derived labels: NO (rejected by the buffer; static scan). AAMI_SVF equivalence: NOT claimed.

----------------------------------------------------------------------
LOCAL TRAINING BUFFER
----------------------------------------------------------------------
`product/edge/local_training_buffer.py` (`LOCAL_TRAINING_BUFFER_V1`), binding doc `docs/capstone/CAPSTONE_LOCAL_BUFFER_BINDING_V1.md`. Storage: deterministic local in-memory regeneration. Batch IDs `WEARABLE_SIM_FL_BATCH_0001__<client>__<dataset_sha[:12]>`.
Record counts = eligible counts = V2-FL-005 trainable counts (93, 91, 91, 89, 90, 93, 93, 83); only trainable windows stored, all `quality_eligible=true`. `model_input_ref` = opaque `LOCALREF:<sha16>:<pos>:<digest16>`; tensors live in a private owner-only store.
Central SQLite used: NO. Cross-client access: refused (`CROSS_CLIENT_INPUT_ACCESS`; tested and mutation-controlled).

----------------------------------------------------------------------
FL CLIENT ADAPTER
----------------------------------------------------------------------
`product/federation/client.py` (`CAPSTONE_FL_CLIENT_ADAPTER_V1`) + `update_bridge.py` + `local_cohort.py`. `isinstance(client, FLClient)` holds; signatures match the frozen contract. Edge identities come from `edge_identity_for_site` (frozen mapping).
Base model: `FL_INIT_V2` only (MODEL_V2_FINAL fails closed; the base state must equal the frozen FL_INIT_V2 sha). Lifecycle: IDLE -> DATA_READY -> TRAINING -> UPDATE_READY (FAILED on execution failure); SUBMITTED is reserved for CAP-007 and never reached.
FedAvg: calls the existing `train_local_epoch_v2` with the frozen V2-FL-005 hyperparameters imported (not copied). FedProx: calls the existing `train_local_fedprox_epoch_v2` with the frozen `mu` read from `FEDPROX_MU_V2`.

----------------------------------------------------------------------
FEDAVG CANONICAL LOCAL TRAINING
----------------------------------------------------------------------
8 clients, 8 local-training calls per run (runtime tripwire confirmed 0 aggregation/coordinator calls), round 1, base state `6a2923ca87793fb78571b4cffad4026f8b4ce99d9dfcb3abe885e259c68a572f`.
Examples per client: 93, 91, 91, 89, 90, 93, 93, 83. Update SHAs equal the frozen ones (e.g. SITE_00 `65a450bc...`). All updates finite; aggregation: NO; metrics: NO (`metrics_computed=false`).

----------------------------------------------------------------------
V2-FL-005 PARITY
----------------------------------------------------------------------
Dataset counts equal: YES. Dataset SHAs equal: YES. Examples equal: YES. Shuffle seeds equal: YES. Update SHA256 equal: YES (also payload bytes and base global-state sha). Any mismatch: NO. No tuning was needed: the existing code was reused, and the very first probe reproduced the frozen values.

----------------------------------------------------------------------
FEDPROX LOCAL SMOKE
----------------------------------------------------------------------
Client SIM_FL_SITE_00, round 1, FL_INIT_V2, mu = 0.1 (frozen). Existing implementation used: YES (1 call; FedAvg epoch not called). Examples 93 = eligible; finite: YES; digest `17a5f952...`. Aggregation: NO. Metrics: NO. Classification: product-adapter compatibility smoke, not research evidence and not part of the parity digest.

----------------------------------------------------------------------
UPDATE BOUNDARY
----------------------------------------------------------------------
UpdateSubmission fields: client_id, round_id, base_state_digest, update_digest, examples_seen (frozen mapping to the envelope). Existing V2 envelope reused: YES (`make_envelope`; no new schema). Raw ECG: none. Raw PPG: none. Labels: none. Truth: none
(`scan_forbidden` = [] plus structural checks on every envelope in both runs and the smoke). Delta digest valid: YES (77 floating tensors finite, 15 integer buffers zero-delta, keys/shapes/dtypes equal the base state).

----------------------------------------------------------------------
LOCALITY
----------------------------------------------------------------------
Logical one-laptop locality: eight separate buffers with owner-checked reads. Training inputs local: YES (never written to SQLite/disk; not reachable from product API, WebSocket or frontend). Server-visible data: the 5-field projection and the existing envelope (metadata + model delta).
SQLite training data: NONE. Claims bounded: no hardware/VM/enclave isolation, no cryptographic secrecy, no differential-privacy or privacy-guarantee claim.

----------------------------------------------------------------------
REPRODUCIBILITY
----------------------------------------------------------------------
Fresh processes: 2 (different pids). Run 1 and run 2: buffer digests, dataset SHAs, examples, shuffle seeds, update digests and UpdateSubmission objects identical; run semantic digest `555e66ba...` identical in both (and in a pre-freeze rehearsal).

----------------------------------------------------------------------
OUT OF SCOPE
----------------------------------------------------------------------
Coordinator.submit? NO. Aggregation? NO. FedAvg server aggregation? NO. FedProx server aggregation? NO. SecAgg? NO. Federation run? NO. Candidate model? NO. Frontend change? NO. Backend change? NO. Personalized/user-session training? NO. Physical hardware? NO. CAP-007 started? NO.

----------------------------------------------------------------------
TESTS
----------------------------------------------------------------------
Targeted: 41 passed (buffer 14, client 17, bridge 7, repro 3). Prior capstone: 423 passed. Full Python regression: 2863 passed, 1 skipped, 0 failed. Mutation controls: 10/10 caught by named tests and restored byte-identically.
Frontend: 145 tests pass, svelte-check 0 errors, build ok. ruff clean; pip check clean. CI queried? NO. CI triggered? NO.

----------------------------------------------------------------------
CONTROL PLANE
----------------------------------------------------------------------
CAP-001/CAPG0 PASS; CAP-002/CAPG1 PASS; CAP-003/CAPG2 PASS; CAP-004/CAPG3 PASS; CAP-005/CAPG4 PASS; CAP-006/CAPG5 PASS; CAP-007 NOT_STARTED.
Components (`component_registry_cap_006_v1.csv`): CAPSTONE_LOCAL_TRAINING_PROTOCOL_V1 (FROZEN_ENGINEERING_PROTOCOL), CAPSTONE_LOCAL_BUFFER_BINDING_V1 (FROZEN_IMPLEMENTATION_BINDING), SIMULATION_LABEL_ADAPTER_V1, LOCAL_TRAINING_BUFFER_V1,
CAPSTONE_FL_CLIENT_ADAPTER_V1, CAPSTONE_FL_UPDATE_BRIDGE_V1, CAPSTONE_FL_CLIENT_COHORT_V1 (FROZEN_ENGINEERING_IMPLEMENTATION).

----------------------------------------------------------------------
GIT
----------------------------------------------------------------------
Entry/control commit `fa96457`; method/local-training freeze `a1582da`; amendments `9734581` (CAP-005 amendment 6 + CAP-006 amendment 1), then CAP-006 amendments 2 and 3 (evaluator fixes); result commit = HEAD after this file; origin/main synchronized after push.

----------------------------------------------------------------------
DISCLOSURES
----------------------------------------------------------------------
Inherited: CAP-001 gate-row wording; CAP-002 code-drafted-before-entry; CAP-003 LIVE_SPEED bounded-settle, manual-stop-mid-outage, context projection; CAP-004 additive Clerk lock, SQLite store location, inherited CAP-003 flaky test; CAP-005 Clerk WebSocket cookie path unverified, no live-Clerk E2E,
accessibility audit not formal WCAG certification, canonical UI evidence on ACCELERATED simulation. New:
1. **Locality limitation:** all eight clients run in one process on one laptop; locality is logical (owner-checked buffers), not process/VM/hardware isolation, and gives no cryptographic secrecy.
2. **Synthetic engineering labels:** `WEARABLE_SIM_EVENT_WINDOW_V1` labels exist only to exercise real local optimisation; they are not AAMI_SVF labels and no efficacy/accuracy statement follows from them. No metric was computed.
3. **FedProx smoke classification:** one client, one round, frozen mu; adapter-compatibility evidence only, outside the V2-FL-005 parity digest, no FedProx global model.
4. **Chronology:** the implementation was drafted and probed (one client reproduced the frozen round-1 update SHA) *before* the entry commit; it was committed only with the method freeze (disclosed in `entry_audit.json`). The canonical runs, mutation run and logs all happened after the freeze.
5. **Method repairs (before the recorded evaluation, criteria text unchanged):** CAPSTONE_FRONTEND_PRODUCT_PROTOCOL_V1 amendment 6 (the CAP-005 backend-identity guard failed on ADDED files under `product/`; narrowed to modified/deleted via `--diff-filter=MD`), CAP-006 amendment 1 (audit allow-list), and CAP-006 amendments 2-3 (evaluator false positives on comment mentions; one regex slip of mine). No implementation or canonical-run file changed after the freeze.
6. `SUBMITTED` is never reached by CAP-006; the client exposes `mark_submitted()` only for the CAP-007 coordinator. The frontend still shows the truthful "NOT YET ENABLED" federation placeholder.

----------------------------------------------------------------------
FINAL DECISION
----------------------------------------------------------------------
CAP-006 accepted? Awaiting audit - result: PASS. CAPG5 accepted? Awaiting audit - result: PASS. CAP-007 allowed? Yes, after audit; it was NOT started.
Any frozen scientific/FL/runtime reopening required? NO. (Reopened frozen items, disclosed: one CAP-005 guard test via a recorded amendment.)
