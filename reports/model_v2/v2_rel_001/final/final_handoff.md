# V2-REL-001 handoff (gate V2RELG0: PASS) -- research-software release decision

Chronology: entry f3d3d9f -> policy 5560c55 (SYSTEM_V2_RELEASE_POLICY_V1, V2RELG0 NOT_STARTED, created AFTER the
evidence; no preregistration claim) -> decision 211c397 (ACCEPT, 25/25 criteria, derived, no override) ->
default-binding audit 1c0ec0e -> cutover f8373b2 -> cutover result 8f9ef99 -> fresh-clone release smoke
(PASS) -> this evidence commit. Default = MODEL_V2_FINAL / GATEWAY_ARTIFACT_V2 / CAL_V2 /
ALERT_POLICY_V1_MODEL_V2_BINDING / API_SCHEMA_V1 via `python -m scripts.run_nhm_default`; rollback =
`--profile rollback-v1` (V1 stack). MODEL_V2_NOT_PROMOTED_RELEASE_CI unchanged. Non-diagnostic research
prototype; no hardware, clinical or physical-wearable validation; no federated checkpoint deployed.
