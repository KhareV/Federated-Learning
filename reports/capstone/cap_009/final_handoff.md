# CAP-009 final handoff — PASS / CAPG8 PASS

CAP-009 implements owner-scoped persisted session history and read-only frozen ML/FL evidence in the existing SvelteKit product. It does not reopen scientific promotion, change the released runtime, train on user sessions, run a new FL experiment, or use physical hardware. CAP-010 remains NOT_STARTED. CI was neither queried nor triggered.

## Entry and freeze

- Entry: `bdc16611290d371abbcca582920086dcfe4d49a8`, clean and equal to `origin/main`; immutable entry audit: `reports/capstone/cap_009/entry_audit.json`.
- CAP-001..008 / CAPG0..7: PASS; predecessor protocol/amendment chains verify.
- Method/UI freeze: `e4e6579`; `CAPSTONE_HISTORY_EVIDENCE_PROTOCOL_V1` has 145 prospective CAPG8 criteria, and `CAPSTONE_UI_V1_2` binds all 230 frontend files. Prior UI locks are byte-identical.
- Eight post-freeze amendments were dedicated/pure commits: `40b9f43`, `d7b6e8f`, `dbe1c05`, `ed12ff7`, `f269860`, `14c9a37`, `36ff4fa`, `b0e33e1`. No canonical result evidence was included in them. Two failed responsive browser attempts and one failed gate-report attempt remain preserved.

## Product and history

- `CAPSTONE_PRODUCT_API_V1_3` composes unchanged V1_2 and adds exactly four reserved GET routes: session summary, session timeline, research ML, research FL. `/system` identifies V1_3 while retaining PRODUCT_API_V2, SOFTWARE_SYSTEM_V2, MODEL_V2_FINAL, SIMULATED_ONLY, and ENABLED_ENGINEERING.
- `SESSION_SUMMARY_V1_INFERRED_WINDOWS` is atomic, owner-scoped, idempotent, and available only for COMPLETED sessions. Duration uses PRODUCT_LIFECYCLE_CLOCK. Window, monitoring-state, and ECG-quality counts use persisted INFERENCE EVENTS, not all source windows. HR/valid SpO2 use projected context snapshots. Device disconnect/reconnect counts use session connection rows.
- Source-domain inference/state-change/quality-change/projected-context events and product-clock device lifecycle events are separate. `inference_events.context_json` is never selected for the public timeline. Failed sessions have partial timeline evidence but no completed summary.
- ECG preview is bounded decimated persisted evidence, not raw waveform storage. Null buckets remain gaps.
- Canonical DEMO browser flow used MIXED_MONITORING_SESSION through real V1_3, fresh SOFTWARE_SYSTEM_V2 inference, fresh SQLite, and production SvelteKit build. Session `SESS-940efa58882243eeb5d96179fa2dea66` completed: 86 inference events, 183 source-timeline entries, six device events, one ECG preview with 3,928 points (122 null gaps), one disconnect and one reconnect. Relational DB assertions and backend-restart payload digests passed. Active Chrome request interception allowed loopback only; 832 requests and zero external attempts. Four widths (1440, 1024, 768, 390) passed on all four pages.

## Frozen research evidence

- Catalog `CAPSTONE_RESEARCH_EVIDENCE_CATALOG_V1` contains 49 exact facts from 22 frozen summary sources. Two fresh builds matched byte-for-byte; source SHA/value parity and tamper rejection passed. No prediction table, raw biomedical dataset, inference, training, calibration fitting, bootstrap, FL execution, or SecAgg execution was used to build the view.
- Historical `MODEL_V2_NOT_PROMOTED_RELEASE_CI` and `promotion_eligible=false` remain true. Later `SYSTEM_V2_RESEARCH_DEFAULT_ACCEPTED=true` is a distinct prospective software-system decision, not a rewrite of historical model-promotion criteria. Current default is centrally trained MODEL_V2_FINAL inside SOFTWARE_SYSTEM_V2; CAL_V2 remains MIT-BIH source-domain only.
- V2-010 evidence is post-freeze second-look/runtime evidence. INTERNAL_TEST has six eligible contributing groups. INCART is project-exposed external second-look evidence. QUALITY_V1 stuck-nonzero and lack of physical wearable validation remain visible.
- Scientific FL series is V2-FL-001, V2-FL-002, V2-FL-003, V2-FL-EVAL-001, V2-FL-004. FedProx transfer is mixed and not generally promoted. V2-FL-005 is an engineering demo only, excluded from efficacy metrics. SecAgg evidence supports PROTECTED_AGGREGATION_INTERFACE_ONLY in a controlled Flower shadow round; authoritative product aggregation is PLAIN. It does not establish DP, anonymity, hospital privacy, TLS, or production security.

## Local verification and scope

- CAPG8 adjudication: 145/145 prospective criteria PASS (`capg8_criteria.json`). 18 in-memory/static mutation probes passed, alongside named ownership, failed-session, context-withholding, and preview behavioral tests.
- Backend targeted: 25 passed; lifecycle: 21 passed; monitoring regression: 14 passed. Final full Python policy run: 2,958 passed, one inherited post-exposure skip, one documented CAP-003 race deselected. That exact frozen race was independently probed 12 times: five passes, seven only the known `journal.closed` timing signature. Earlier failed full runs are disclosed in `test_report.json`; frozen monitoring code was not modified.
- Frontend: `npm ci` passed, 193 Vitest tests passed (three existing integration skips), svelte-check zero errors (112 inherited warnings), build passed. Ruff and pip check passed. `npm ci` reported seven pre-existing package advisories; no dependency was added or automatically upgraded.
- Scientific, released-runtime, CAP-006, CAP-007, CAP-008 federation, V1_2 API, prior UI locks, held-out evidence and one-shot guards have zero drift. No user-session data flows to FL or personalization. No candidate inference/deployment, hardware, CAP-010, or CI operation occurred.

## Preserved CAP-008 disclosures

- eight federation clients are logical clients on one laptop;
- they are not hospitals or institutions;
- CAP-007 one-active-run policy is not a distributed-lock guarantee;
- SecAgg is round-1 shadow only;
- authoritative aggregation remains PLAIN;
- SecAgg claim is PROTECTED_AGGREGATION_INTERFACE_ONLY;
- no DP guarantee;
- no anonymity guarantee;
- candidate sandbox has no inference runtime;
- Clerk WebSocket path remains unverified with a real Clerk account;
- no physical wearable evidence exists;
- CAP-008 amendment commit 85fe0b3 included unrelated result evidence by mistake.

CAP-009 does not reopen any CAP-008 result. All eight CAP-009 post-freeze amendment commits are pure.
