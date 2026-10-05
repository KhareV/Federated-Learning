# SYSTEM_V2_RELEASE_POLICY_V1 (V2-REL-001, gate V2RELG0)

Machine-readable policy: `configs/model_v2/system_v2_release_policy_v1.yaml`. Evaluator:
`scripts/evaluate_system_v2_release.py`.

## What this is
A prospective **system-level research-software** governance decision about which already-frozen,
already-evaluated lineage should be the default **research runtime**. Release level:
`RESEARCH_SOFTWARE_OPERATIONAL_DEFAULT`. It is not a clinical, medical-device, hospital, hardware or
wearable-validation release and not a federated-checkpoint deployment.

## Evidence-timing disclosure
The policy is created **after** the scientific and engineering evidence exists. It is not a
preregistered scientific hypothesis test and not a prospective validation-performance gate; no new
p-value or performance threshold is invented. The frozen evidence may legitimately inform a software
governance decision made before the operational default changes.

## Decision rule
ACCEPT iff all hard blockers H01..H24 pass and no unresolved integrity defect exists; otherwise REJECT
and no default change occurs. Computed mechanically from frozen evidence; manual override is forbidden.
The historical `MODEL_V2_NOT_PROMOTED_RELEASE_CI` disposition is never rewritten: both it and, if
accepted, `SYSTEM_V2_RESEARCH_DEFAULT_ACCEPTED` are simultaneously true.

## Default target
`MODEL_V2_FINAL -> GATEWAY_ARTIFACT_V2 -> CAL_V2 -> ALERT_POLICY_V1_MODEL_V2_BINDING -> API_SCHEMA_V1`.
The default is the CENTRALLY trained MODEL_V2_FINAL, not any federated checkpoint and not the
disposable V2-FL-005 state. API_SCHEMA_V1 and `POST /v1/infer-window` are unchanged; no public model
selector exists. V1 stays available as an explicit operator-only rollback launch profile.

## Known limitations (disclosed, non-blocking)
L01 release-seed paired CI crossed zero (permanent); L02 six eligible INTERNAL_TEST groups; L03 V2-010
evidence is post-freeze second look; L04 INCART FL evaluation is project-exposed; L05 QUALITY_V1
stuck-nonzero limitation (not repaired); L06 CAL_V2 is MIT-BIH source-domain only; L07 no physical
wearable validation; L08 SecAgg is a narrow aggregation-interface result; L09 CLEAN_CLONE_GATING_V1
data-gated tests.

## Chronology
policy -> decision evaluation -> release decision commit (ACCEPT only) -> cutover -> cutover result ->
fresh-clone release smoke -> final evidence commit.
