# CAP-003 final handoff

CAP-003: **PASS** - CAPG2: **PASS** (74/74 criteria, `capg2_criteria.json`) - CAP-004 NOT_STARTED (allowed next).

Entry `9f49b0c52fd93f7a28aff9ef67407fa9c56976df`; entry commit `f3f400d`; method/protocol freeze `9719941`;
pre-evaluation amendment `2a49f20` (evaluator lookup only); result commit = the commit adding this file.

Canonical E2E (MIXED_MONITORING_SESSION, ACCELERATED), two fresh runs, each with a fresh REAL released inference process
(`python -m scripts.run_nhm_default`, SOFTWARE_SYSTEM_V2 / MODEL_V2_FINAL): semantic digest `e180e8241ab39a40e0819411b2e20daf2585367282b641b9792c7e8c6b428325` in both;
3157 events; HTTP {'200': 86, '422': 7}; windows 93; waveform chunks 2880 with UI None interval [[118800, 124199]];
terminal `COMPLETED`; `context_values_withheld` = 8.
Systems/product integration evidence only; no model-efficacy or clinical claim.

Disclosures: (1) amendment 1 (evaluator looked in the wrong lock map for the binding config); (2) contract clarification: the released system can
report `context_available=false` with a pulse rate present, which the frozen `context.snapshot` validator forbids - the three PPG values are withheld
(counted, never invented; CAP-001 untouched); (3) the multiplexer is rigorous for ACCELERATED and bounded-settle + fail-loud for LIVE_SPEED (the frozen
DeviceSource has no watermark); (4) manual stop mid-outage leaves the simulated device in its link state (source timeline can run ahead in ACCELERATED);
(5) the product app runs in-process in the E2E (no production auth in CAP-003); (6) a development smoke of the canonical path ran before the freeze;
(7) preserved CAP-001/CAP-002 disclosures untouched; (8) CI neither queried nor triggered.
