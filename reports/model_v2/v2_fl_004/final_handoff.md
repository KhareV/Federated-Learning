# V2-FL-004 handoff (gate V2FLG3: PASS)

Flower 1.39.0 SecAgg+ on reconstructed MODEL_V2 FedAvg IID round 1 (8 CLIENTS_IID_V1 clients,
TRAIN only; plain reconstruction sha fb178f1a... exact). Historical T028 parameters unchanged.

- Correctness: known-vector max abs 5.8e-9; MODEL_V2-shaped max abs 7.2e-6, relative L2 1.6e-5.
- Visibility: plain control 8 clear updates; protected 0 (aggregate available; 8 masked vectors,
  24 key/share metadata objects, client IDs visible and reported).
- Overhead (aggregation only, N=10 +1 warm-up): plain median 8.9 ms, protected 212 ms (+203 ms,
  23.8x); application payload 2,208,113 -> 5,844,328 bytes (2.65x; not network bytes). 10/10 completed.
- V1->V2: parameters 13,185 -> 57,553; runtime comparison is non-matched descriptive context.
- Claim: narrow only (see docs/MODEL_V2_SECAGG_THREAT_MODEL_V1.md); no DP, no production claim.
- Regression: 2277 nodes, 29 chunks PASS (attempt 1 failed on two registry row-count tests that
  hard-coded 18 gates; relaxed to append-only, attempt recorded). ruff and pip check PASS.
- CI never queried or triggered. V2-FL-005, V2-014, T036 not started.
