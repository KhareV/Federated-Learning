# CAP-002 final handoff

CAP-002: **PASS** - CAPG1: **PASS** (53/53 criteria, `capg1_criteria.json`) - CAP-003 NOT_STARTED (allowed next).

Entry `44939378e7aee3baa2e92fefdd42fa9d75640a8a`; entry commit `0d7def2`; method/protocol freeze `51cab3c`;
pre-evaluation amendments `9b12318`, `142d9c8`, `6aa118b` (criteria text unchanged); result commit = the commit adding this file.

| scenario | seed | records | events | windows | semantic digest (identical in 2 fresh processes) |
|---|---|---|---|---|---|
| NORMAL_MONITORING | 20261001 | 43200 | 6 | 21 | `acfc7b4d6db153fb6bce714ec048a6b426e3fa02d2da3de18295a37d3ce2097a` |
| CONTEXT_LOSS | 20261002 | 64800 | 6 | 33 | `15d2cf11e293edfc5ef545df9d7bc11a1bbdf98820e223c0d44ccd15903f7439` |
| POOR_SIGNAL | 20261003 | 64800 | 6 | 33 | `76e491c1a2727be73e9d472720d0bb7a5425533909eab3cc0030abc8a6e07c30` |
| DISCONNECT_RECONNECT | 20261004 | 59400 | 10 | 33 | `6829e84f000c9e0673f2f28ac18f7d5a53f9092feeb25d2f41b752ef99ade638` |
| MIXED_MONITORING_SESSION | 20261005 | 167400 | 10 | 93 | `077a892641c02673e030c4b7729a5c82aef9f0d66d9ca42976c648a55ca3db9b` |

Disclosures: (1) three amendments to the frozen mutation-control script/evaluator (an equivalent mutant; evaluator self-matching
regex hits; a loose substring) are recorded in `artifacts/capstone/CAPSTONE_DEVICE_EDGE_PROTOCOL_V1.amendment_*.json`;
(2) CAP-002 code was drafted before the entry commit but committed after it; (3) the inherited CAP-001 "33 vs 50 criteria"
wording in the CAPG0 gate row is recorded, not repaired; (4) CAP-002 components live in `component_registry_cap_002_v1.csv`
because the CAP-001 lock binds `component_registry_v1.csv`; (5) CI neither queried nor triggered.
