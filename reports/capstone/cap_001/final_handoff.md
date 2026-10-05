# CAP-001 final handoff (FL-first product architecture / contract freeze)

CAP-001: **PASS** - CAPG0: **PASS** - CAP-002 remains NOT_STARTED (allowed next).

Entry SHA `8bbc0e1e17e314748ad7127544e46d8305efeb0c` (== origin/main, clean, no intervening commits).
Entry-evidence commit `50c279b`; **method/contract freeze commit `eba23a6`**; result commit = the commit adding this file.
Protocol lock: `artifacts/capstone/CAPSTONE_PRODUCT_PROTOCOL_V1.lock.json`.

## Frozen components
| component | status | path | sha256 |
|---|---|---|---|
| CAPSTONE_AUTH_POLICY_V1 | FROZEN_PRODUCT_POLICY | `contracts/capstone/auth_policy_v1.json` | `3ac629a35431404b3d6e19ba8486218b77a318a902381ac3b0f2be2e9f00d5b6` |
| CAPSTONE_DEMO_SCENARIOS_V1 | FROZEN_DEMO_CONTRACT | `contracts/capstone/demo_scenarios_v1.json` | `3498194003de926a90e37b4a293100aef0d59e54c41b28de200686b0221ee296` |
| CAPSTONE_FEDERATION_CONTRACT_V1 | FROZEN_INTERFACE_CONTRACT | `contracts/capstone/federation_v1.json` | `e0bf46f8678703e8b51dfc292fbb064a16dfd6f345c32645935d8e30dd556359` |
| CAPSTONE_FL_CLIENT_CONTRACT_V1 | FROZEN_INTERFACE_CONTRACT | `contracts/capstone/fl_client_v1.json` | `c25216aa25505235d3a3937e6ced084a7e9e8edffcd9f5d9c3e46b30bef1eec0` |
| CAPSTONE_FL_RUN_CONTRACT_V1 | FROZEN_INTERFACE_CONTRACT | `contracts/capstone/fl_run_v1.json` | `82e591f6aad3a3ba4d25b8b2ab5324a641bf0e8dcc5a29ca4c7832e3aac6af28` |
| CAPSTONE_MODEL_GOVERNANCE_V1 | FROZEN_PRODUCT_POLICY | `contracts/capstone/model_governance_v1.json` | `74e768135ce478e5c6fc7f67f3b74b395983711b6505d2354e486e58fd4f1a98` |
| CAPSTONE_MODEL_REGISTRY_CONTRACT_V1 | FROZEN_INTERFACE_CONTRACT | `contracts/capstone/model_registry_v1.json` | `fdd4d7947b6642cd1c79d6e05f78eadb4141bf8d33365caee621b263c6121a18` |
| CAPSTONE_PRODUCT_PROTOCOL_V1 | FROZEN_PRE_IMPLEMENTATION_PROTOCOL | `configs/capstone/capstone_product_protocol_v1.json` | `623cef6e91713df83217578cb665ed06ca330c3a2a5ee9beeeac1d6f1f198b11` |
| CAPSTONE_SESSION_CONTRACT_V1 | FROZEN_INTERFACE_CONTRACT | `contracts/capstone/session_v1.json` | `c758fe1d204f7fe075c19784a08390306b0d3a2ee3ebbc08f3b819e3f5fa1fec` |
| CAPSTONE_STORAGE_POLICY_V1 | FROZEN_PRODUCT_POLICY | `contracts/capstone/storage_policy_v1.json` | `c929bb0eaa83cd43aec53709bde5b1f574a0c2784a84969fa29a039671a29b22` |
| DEVICE_SOURCE_CONTRACT_V1 | FROZEN_INTERFACE_CONTRACT | `contracts/capstone/device_source_v1.json` | `dbc2c9dade04d122c2dd8acb59d45d555f9e3435973eba9bbd0589113015111e` |
| EDGE_NODE_CONTRACT_V1 | FROZEN_INTERFACE_CONTRACT | `contracts/capstone/edge_node_v1.json` | `ef7a39ef204442a75c9ab54aa6d6a1897e737d8832e36f974b5363ad6ef6b169` |
| LOCAL_TRAINING_BUFFER_CONTRACT_V1 | FROZEN_INTERFACE_CONTRACT | `contracts/capstone/local_training_buffer_v1.json` | `4baa7eaa82587906e311061d3798d4d67c864145bbd8b0188d05de5c8bcc4cc2` |
| PRODUCT_API_CONTRACT_V1 | FROZEN_INTERFACE_CONTRACT | `contracts/capstone/product_api_v1.json` | `b9699371047262c7911f51a3159278098e487d863785f5131e2b68be8db3c8e1` |
| PRODUCT_LIVE_EVENT_V1 | FROZEN_INTERFACE_CONTRACT | `contracts/capstone/live_event_v1.json` | `04fa85aafa2dd522fcf244f8a6b40e184b85bcf2affc648ab773920ad298c54c` |
| REAL_HARDWARE_REPLACEMENT_BOUNDARY_V1 | FROZEN_PRE_IMPLEMENTATION_PROTOCOL | `contracts/capstone/real_hardware_replacement_v1.json` | `176e279c56efba8cef9cc2a9c5d543e553ea64e87e1ceef9e66706a31062af01` |

Full report sections (upstream protection, frontend, FL-first architecture, device/edge, SimulationTruth,
local training, federation, governance, API, auth/storage, demo, hardware, control plane, tests, git,
final decision) are returned in the session handoff; machine evidence is in this directory:
`upstream_protection_entry.json`/`_final.json` (zero drift over 3094 files + 58 named components),
`capg0_criteria.json` (50/50), the per-contract `*_audit.json`, `connection_table.json`, `architecture_graph.md`,
`frontend_reuse_audit.json`, `fl_reuse_audit.json`, `test_report.json`, `logs/`.

## Disclosures
- The earlier entry commit `50c279b` carries a superseded CAP-002..009 roadmap; the freeze commit replaced it with CAP-002..011 per the FL-first brief.
- The pasted Clerk CLI setup instructions were NOT executed (CAP-001 forbids Clerk integration and frontend changes; Clerk integration is deferred to CAP-004/CAP-005 behind `AuthProvider`).
- `UpdateSubmission` field names differ from the V2-FL-005 envelope (`update_sha256`, `base_global_state_sha256`); the contract freezes an explicit mapping.
- Hardware facts are VERIFICATION_REQUIRED; no candidate/FL run/product runtime exists; no later phase started.
- CI neither queried nor triggered.
