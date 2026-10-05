# CAPSTONE_PRODUCT_PROTOCOL_V1 (FL-first)

Status: `FROZEN_PRE_IMPLEMENTATION_PROTOCOL` (task CAP-001, gate CAPG0). Machine-readable form:
`configs/capstone/capstone_product_protocol_v1.json`. **CAP-001 does not change the frozen NHM science.**

## 1. Framing
The capstone is **a federated physiological-monitoring platform in which local edge nodes perform
live monitoring using a released model while participating, separately and under governance, in
federated model-development workflows.** It is not "an ECG monitoring website with an FL research
page". Federation is a top-level product section (`/app/federation/*`, `/app/models`).

## 2. Five separated planes
| # | Plane | Contents |
|---|---|---|
| 1 | Product / user | existing SvelteKit frontend extended additively (**CAPSTONE_UI_V1**): auth, device, monitoring, history, federation, models, research, system, limitations |
| 2 | Edge / client | DeviceSource -> ObservedRecord -> local stream -> live MODEL_V2_FINAL inference -> monitoring events; **separately** local training buffer -> federated local trainer -> model update |
| 3 | Federation | clients 00..07 -> local training -> update submission -> FedAvg/FedProx -> SecAgg+ where applicable -> candidate global state |
| 4 | Model governance | candidate -> registry -> engineering/validation gate -> ACCEPT/REJECT -> sandbox version / archive. **Never auto-replaces the released model** |
| 5 | Released monitoring | SOFTWARE_SYSTEM_V2 (MODEL_V2_FINAL, GATEWAY_ARTIFACT_V2, CAL_V2, PREPROC_V1, QUALITY_V1, ECG_HR_CONTEXT_V2, ALERT_POLICY_V1_MODEL_V2_BINDING, API_SCHEMA_V1) - **frozen** |

Graphs: `reports/capstone/cap_001/architecture_graph.md`; every arrow: `contracts/capstone/connection_table_v1.json`.

## 3. Frontend (hard rule)
The existing `frontend/` SvelteKit app is the only frontend foundation. No second frontend, no
framework migration, no duplicated monitoring/dashboard components; the existing V2 replay integration,
waveform/state/context components, API client and stores are reused. CAP-001 does not touch `frontend/`.

## 4. Wearable != FL client; edge node
A wearable is an acquisition source; a federated client is an edge compute entity (`EDGE_NODE_CONTRACT_V1`).
Today: Virtual Wearable -> Virtual Edge Node -> FL client. Future: Physical Wearable -> phone/laptop/edge
gateway -> FL client. A sensor-class device never runs PyTorch training.

## 5. SimulationTruth boundary and labels
`SimulationTruth` is never consumed by live preprocessing, QUALITY_V1, MODEL_V2 inference, CAL_V2,
alert/state logic, the product monitoring API or the live dashboard. It may feed only the dedicated
`SIMULATION_LABEL_ADAPTER_V1` that builds LOCAL training labels in the federated sandbox
(`label_source = SIMULATION_TRUTH_ENGINEERING`, forbidden for real data). Future real wearable data has
no automatic label: a validated label source is `VERIFICATION_REQUIRED`; unlabeled live streams cannot
continuously train supervised FL.

## 6. No continual production learning
Allowed: interactive multi-round federated model-development, new simulated local batches, candidate
versions, governance, repeatable update cycles (a **continual federated model-development sandbox**).
Forbidden: sample -> prediction -> prediction-as-label -> retraining -> automatic deployment;
self-labeling; uncontrolled online learning; silent replacement of MODEL_V2_FINAL.

## 7. Federation, candidates, governance
Reuses the existing V2 FL stack (FedAvg, frozen FedProx, SecAgg+ shadow, the V2-FL-005 coordinator and
8-client cohort SIM_FL_SITE_00..07 / SIM_P000101..108); no new optimizer, mu tuning, aggregator, privacy
or DP mechanism. Round lifecycle CREATED -> COLLECTING -> LOCAL_TRAINING -> UPDATES_READY -> AGGREGATING
-> CANDIDATE_CREATED -> VALIDATING -> ACCEPTED_TO_SANDBOX/REJECTED -> COMPLETED (+FAILED); no "DEPLOYED".
Candidates `CAPSTONE_FL_CANDIDATE_####` are engineering sandbox candidates, `production_deployed = false`;
acceptance is not scientific promotion. Any inference with a candidate needs the isolated
`CAPSTONE_FL_SANDBOX_RUNTIME`, never `/app/monitoring`. The released runtime gets no model selector.

## 8. Data locality and privacy claims
The federation server never receives raw ECG/PPG/SpO2, SimulationTruth, local labels or minibatches.
Plain FedAvg exposes clear model updates (not private). The SecAgg path supports only the narrow
protected-aggregation-interface claim; no anonymity, DP, complete-privacy or inference-resistance claim.

## 9. Product layer
Additive product API (`/product/v1`) above the frozen `POST /v1/infer-window`; `API_SCHEMA_V1` and
`SOFTWARE_SYSTEM_V2` are unchanged; no direct model import; no second inference implementation.
Live events (`PRODUCT_LIVE_EVENT_V1`): typed unions for monitoring and federation streams.
Auth: `AuthProvider` (Clerk planned; explicit visible Demo provider); identity never selects ML.
Storage: SQLite; no per-sample rows.

## 10. Offline faculty mode and demo
One laptop, no hardware, cloud ML, remote DB, remote federation server, Clerk or internet. A genuine
executable FL demo is required later (live-run mode; a replay/instant mode may coexist; both labelled).
Scenarios: `contracts/capstone/demo_scenarios_v1.json`. The abnormal full-model demo is never tuned; the
alert-policy fixture is labelled "ENGINEERING STATE-MACHINE DEMONSTRATION - NOT MODEL PERFORMANCE EVIDENCE".

## 11. Hardware replacement and claims
See `REAL_HARDWARE_REPLACEMENT_BOUNDARY_V1.md`. Unknown hardware facts are `VERIFICATION_REQUIRED`.
Allowed claims and forbidden claims: protocol JSON `claim_boundary` (no diagnosis, clinical decision
support, certification, real wearable validation, hospital deployment, DP, clinical superiority of a
candidate, synthetic efficacy).

## 12. Roadmap
CAP-001 contract freeze -> CAP-002 simulated wearable + virtual edge node -> CAP-003 product API + live
streaming -> CAP-004 auth/persistence/sessions -> CAP-005 frontend productization -> CAP-006 local
training buffer + FL client adapter -> CAP-007 federation orchestrator + candidate registry -> CAP-008
federation dashboard + governance UX -> CAP-009 history + evidence -> CAP-010 faculty E2E -> CAP-011
one-laptop release. Only CAP-002 is allowed after CAPG0. Clerk SDK integration belongs to CAP-004/005.
CI is deferred.
